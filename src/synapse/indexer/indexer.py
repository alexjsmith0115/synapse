from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import TYPE_CHECKING

from synapse.graph.connection import GraphConnection
from synapse.graph.edges import (
    upsert_calls, upsert_contains_symbol, upsert_dir_contains, upsert_file_contains_symbol,
    upsert_imports, upsert_module_calls, upsert_symbol_imports, upsert_inherits, upsert_interface_inherits, upsert_implements,
    upsert_repo_contains_dir,
)
from synapse.graph.nodes import (
    upsert_class, upsert_directory, upsert_field, upsert_file,
    upsert_interface, upsert_method, upsert_package, upsert_property,
    upsert_repository, delete_file_nodes,
    collect_summaries, restore_summaries,
    set_attributes, set_metadata_flags,
)
from synapse.indexer.csharp.csharp_base_type_extractor import CSharpBaseTypeExtractor
from synapse.indexer.call_indexer import CallIndexer
from synapse.indexer.method_implements_indexer import MethodImplementsIndexer
from synapse.indexer.overrides_indexer import OverridesIndexer
from synapse.indexer.symbol_resolver import SymbolResolver
from synapse.lsp.interface import IndexSymbol, LSPAdapter, SymbolKind

if TYPE_CHECKING:
    from synapse.plugin import LanguagePlugin

log = logging.getLogger(__name__)

_MINIFIED_LINE_THRESHOLD = 500


def _is_minified(file_path: str) -> bool:
    """Return True if the file's first non-empty line exceeds the minified threshold."""
    try:
        with open(file_path, encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped:
                    return len(stripped) > _MINIFIED_LINE_THRESHOLD
        return False
    except OSError:
        return False


class Indexer:
    def __init__(self, conn: GraphConnection, lsp: LSPAdapter, plugin: LanguagePlugin | None = None) -> None:
        self._conn = conn
        self._lsp = lsp
        self._root_path: str = ""
        if plugin is not None:
            self._import_extractor = plugin.create_import_extractor()
            self._base_type_extractor = plugin.create_base_type_extractor()
            self._attribute_extractor_factory = plugin.create_attribute_extractor
            self._call_extractor_factory = plugin.create_call_extractor
            self._type_ref_extractor_factory = plugin.create_type_ref_extractor
            self._assignment_extractor_factory = getattr(plugin, 'create_assignment_extractor', None)
            self._file_extensions = plugin.file_extensions
            self._language = plugin.name
        else:
            from synapse.indexer.csharp.csharp_import_extractor import CSharpImportExtractor
            self._import_extractor = CSharpImportExtractor()
            self._base_type_extractor = CSharpBaseTypeExtractor()
            self._attribute_extractor_factory = None
            self._call_extractor_factory = None
            self._type_ref_extractor_factory = None
            self._assignment_extractor_factory = None
            self._file_extensions = frozenset({".cs"})
            self._language = "csharp"

    def index_project(
        self,
        root_path: str,
        language: str,
        keep_lsp_running: bool = False,
        on_progress: Callable[[str], None] | None = None,
    ) -> None:
        root_path = root_path.rstrip("/")
        self._root_path = root_path
        files = self._lsp.get_workspace_files(root_path)
        symbols_by_file: dict[str, list[IndexSymbol]] = {}

        if on_progress:
            on_progress(f"Indexing {len(files)} files...")

        for file_path in files:
            if _is_minified(file_path):
                log.debug("Skipping minified file: %s", file_path)
                continue
            symbols = self._lsp.get_document_symbols(file_path)
            symbols_by_file[file_path] = symbols
            self._index_file_structure(file_path, root_path, symbols)

        upsert_repository(self._conn, root_path, language)
        upsert_repo_contains_dir(self._conn, root_path, root_path)

        # Build lookup tables for the base type resolution pass
        name_to_full_names: dict[str, list[str]] = {}
        kind_map: dict[str, SymbolKind] = {}
        for syms in symbols_by_file.values():
            for sym in syms:
                name_to_full_names.setdefault(sym.name, []).append(sym.full_name)
                kind_map[sym.full_name] = sym.kind

        if on_progress:
            on_progress("Resolving base types...")

        for file_path in files:
            try:
                with open(file_path, encoding="utf-8") as f:
                    source = f.read()
                self._index_base_types(file_path, source, name_to_full_names, kind_map)
            except OSError:
                log.warning("Could not read %s for base type extraction", file_path)

        if on_progress:
            on_progress("Extracting attributes...")

        if self._attribute_extractor_factory is not None:
            attr_extractor = self._attribute_extractor_factory()
        else:
            from synapse.indexer.csharp.csharp_attribute_extractor import CSharpAttributeExtractor
            attr_extractor = CSharpAttributeExtractor()
        for file_path in files:
            try:
                with open(file_path, encoding="utf-8") as f:
                    source = f.read()
                file_symbols = symbols_by_file.get(file_path, [])
                self._index_attributes(file_path, source, file_symbols, attr_extractor)
            except OSError:
                log.warning("Could not read %s for attribute extraction", file_path)

        # Phase 1.5: method-level IMPLEMENTS edges (requires all class-level IMPLEMENTS to exist)
        MethodImplementsIndexer(self._conn).index()

        # Phase 1.6: callback CALLS edges — connect parent methods to their callback children.
        # TS LSP names callback symbols like "foo.useEffect() callback"; create a CALLS edge
        # from the parent method to the callback so traversal tools can walk through them.
        self._index_callback_edges(symbols_by_file)

        # CALLS and REFERENCES resolution requires all nodes to be present; must run after structural pass
        _CLASS_KINDS = {SymbolKind.CLASS, SymbolKind.ABSTRACT_CLASS, SymbolKind.INTERFACE}
        symbol_map = {
            (sym.file_path, sym.line): sym.full_name
            for syms in symbols_by_file.values()
            for sym in syms
            if sym.kind == SymbolKind.METHOD
        }
        class_symbol_map = {
            (sym.file_path, sym.line): sym.full_name
            for syms in symbols_by_file.values()
            for sym in syms
            if sym.kind in _CLASS_KINDS
        }

        if on_progress:
            on_progress("Resolving call edges...")

        call_ext = self._call_extractor_factory() if self._call_extractor_factory else None
        type_ref_ext = self._type_ref_extractor_factory() if self._type_ref_extractor_factory else None

        # Build module_full_names set and wire module_name_resolver for Python and TypeScript
        module_full_names: set[str] = set()
        if self._language in ("python", "typescript"):
            module_map: dict[str, str] = {}
            for fp, syms in symbols_by_file.items():
                for sym in syms:
                    if sym.signature == "module" and sym.kind == SymbolKind.CLASS:
                        module_full_names.add(sym.full_name)
                        module_map[fp] = sym.full_name
                        break
            if call_ext is not None and hasattr(call_ext, "_module_name_resolver"):
                call_ext._module_name_resolver = lambda fp, _m=module_map: _m.get(fp)

        # Build assignment maps if plugin supports it
        from synapse.indexer.assignment_ref import AssignmentRef
        assignment_semantic_map: dict[tuple[str, str], AssignmentRef] = {}
        assignment_position_map: dict[tuple[str, int], AssignmentRef] = {}
        if self._assignment_extractor_factory is not None:
            assign_ext = self._assignment_extractor_factory()
            if assign_ext is not None:
                _CLASS_KINDS_for_lines = {SymbolKind.CLASS, SymbolKind.ABSTRACT_CLASS}
                class_lines_per_file: dict[str, list[tuple[int, str]]] = {}
                for fp, syms in symbols_by_file.items():
                    file_class_lines = [
                        (sym.line, sym.full_name) for sym in syms
                        if sym.kind in _CLASS_KINDS_for_lines
                    ]
                    if file_class_lines:
                        file_class_lines.sort()
                        class_lines_per_file[fp] = file_class_lines

                for file_path in files:
                    try:
                        with open(file_path, encoding="utf-8", errors="ignore") as f:
                            source = f.read()
                        refs = assign_ext.extract(
                            file_path, source, symbol_map,
                            class_lines=class_lines_per_file.get(file_path),
                            module_name_resolver=module_map.get if self._language in ("python", "typescript") else None,
                        )
                        for ref in refs:
                            assignment_semantic_map[(ref.class_full_name, ref.field_name)] = ref
                    except OSError:
                        pass

                # Derive position map from semantic map for SymbolResolver fast lookup
                for ref in assignment_semantic_map.values():
                    assignment_position_map[(ref.source_file, ref.source_line)] = ref

                if assignment_semantic_map:
                    log.info(
                        "Built assignment maps: %d semantic entries, %d position entries",
                        len(assignment_semantic_map), len(assignment_position_map),
                    )

        resolver = SymbolResolver(
            self._conn,
            self._lsp.language_server,
            call_extractor=call_ext,
            type_ref_extractor=type_ref_ext,
            name_to_full_names=name_to_full_names,
            file_extensions=self._file_extensions,
            module_full_names=module_full_names,
            assignment_position_map=assignment_position_map,
        )
        resolver.resolve(root_path, symbol_map, class_symbol_map=class_symbol_map)

        # Per-site DEBUG logging for unresolved call sites (per user decision)
        if self._language == "python" and hasattr(resolver, "_unresolved_sites"):
            for site_msg in resolver._unresolved_sites:
                log.debug(site_msg)

        # Resolution summary for Python
        if self._language == "python" and call_ext is not None:
            calls_count_rows = self._conn.query(
                "MATCH ()-[r:CALLS]->() WHERE r.call_sites IS NOT NULL RETURN count(r)"
            )
            resolved = calls_count_rows[0][0] if calls_count_rows else 0
            total = getattr(call_ext, "_sites_seen", 0)
            if total > 0:
                pct = resolved / total * 100
                unresolved = total - resolved
                log.info(
                    "Call resolution: %d/%d resolved (%.1f%%), %d unresolved",
                    resolved, total, pct, unresolved,
                )
                if resolved == 0:
                    log.warning(
                        "Call resolution produced zero CALLS edges (%d sites attempted) — "
                        "check that LSP is running and fixture uses typed code",
                        total,
                    )

        # OVERRIDES detection for Python (pure Cypher, no LSP needed)
        if self._language == "python":
            OverridesIndexer(self._conn).index()

        if not keep_lsp_running:
            self._lsp.shutdown()

    def reindex_file(self, file_path: str, root_path: str) -> None:
        self._root_path = root_path
        saved_summaries = collect_summaries(self._conn, file_path)
        delete_file_nodes(self._conn, file_path)
        symbols = self._lsp.get_document_symbols(file_path)
        self._index_file_structure(file_path, root_path, symbols)
        restore_summaries(self._conn, saved_summaries)

        name_to_full_names: dict[str, list[str]] = {}
        kind_map: dict[str, SymbolKind] = {}
        for sym in symbols:
            name_to_full_names.setdefault(sym.name, []).append(sym.full_name)
            kind_map[sym.full_name] = sym.kind

        try:
            with open(file_path, encoding="utf-8") as f:
                source = f.read()
            self._index_base_types(file_path, source, name_to_full_names, kind_map)
            if self._attribute_extractor_factory is not None:
                attr_extractor = self._attribute_extractor_factory()
            else:
                from synapse.indexer.csharp.csharp_attribute_extractor import CSharpAttributeExtractor
                attr_extractor = CSharpAttributeExtractor()
            self._index_attributes(file_path, source, symbols, attr_extractor)
        except OSError:
            log.warning("Could not read %s for base type extraction", file_path)

        _CLASS_KINDS = {SymbolKind.CLASS, SymbolKind.ABSTRACT_CLASS, SymbolKind.INTERFACE}
        symbol_map = {
            (sym.file_path, sym.line): sym.full_name
            for sym in symbols
            if sym.kind == SymbolKind.METHOD
        }
        class_symbol_map = {
            (sym.file_path, sym.line): sym.full_name
            for sym in symbols
            if sym.kind in _CLASS_KINDS
        }
        call_ext = self._call_extractor_factory() if self._call_extractor_factory else None
        type_ref_ext = self._type_ref_extractor_factory() if self._type_ref_extractor_factory else None

        module_full_names: set[str] = set()
        if self._language in ("python", "typescript"):
            module_map: dict[str, str] = {}
            for sym in symbols:
                if sym.signature == "module" and sym.kind == SymbolKind.CLASS:
                    module_full_names.add(sym.full_name)
                    module_map[sym.file_path] = sym.full_name
            if call_ext is not None and hasattr(call_ext, "_module_name_resolver"):
                call_ext._module_name_resolver = lambda fp, _m=module_map: _m.get(fp)

        # Build assignment maps if plugin supports it
        from synapse.indexer.assignment_ref import AssignmentRef
        assignment_semantic_map: dict[tuple[str, str], AssignmentRef] = {}
        assignment_position_map: dict[tuple[str, int], AssignmentRef] = {}
        if self._assignment_extractor_factory is not None:
            assign_ext = self._assignment_extractor_factory()
            if assign_ext is not None:
                _CLASS_KINDS_for_lines = {SymbolKind.CLASS, SymbolKind.ABSTRACT_CLASS}
                class_lines_for_file = sorted(
                    (sym.line, sym.full_name) for sym in symbols
                    if sym.kind in _CLASS_KINDS_for_lines
                )
                try:
                    with open(file_path, encoding="utf-8", errors="ignore") as f:
                        source = f.read()
                    refs = assign_ext.extract(
                        file_path, source, symbol_map,
                        class_lines=class_lines_for_file or None,
                        module_name_resolver=module_map.get if self._language in ("python", "typescript") else None,
                    )
                    for ref in refs:
                        assignment_semantic_map[(ref.class_full_name, ref.field_name)] = ref
                except OSError:
                    pass

                # Derive position map from semantic map
                for ref in assignment_semantic_map.values():
                    assignment_position_map[(ref.source_file, ref.source_line)] = ref

        SymbolResolver(
            self._conn,
            self._lsp.language_server,
            call_extractor=call_ext,
            type_ref_extractor=type_ref_ext,
            name_to_full_names=name_to_full_names,
            file_extensions=self._file_extensions,
            module_full_names=module_full_names,
            assignment_position_map=assignment_position_map,
        ).resolve_single_file(file_path, symbol_map, class_symbol_map=class_symbol_map)

        if self._language == "python":
            OverridesIndexer(self._conn).index()

    def delete_file(self, file_path: str) -> None:
        delete_file_nodes(self._conn, file_path)

    def _index_file_structure(self, file_path: str, root_path: str, symbols: list[IndexSymbol]) -> None:
        upsert_file(self._conn, file_path, os.path.basename(file_path), self._language)
        self._upsert_directory_chain(file_path, root_path)
        self._index_file_imports(file_path)

        for symbol in symbols:
            self._upsert_symbol(symbol)
            if symbol.parent_full_name is None:
                upsert_file_contains_symbol(self._conn, file_path, symbol.full_name)
            else:
                upsert_contains_symbol(self._conn, symbol.parent_full_name, symbol.full_name)

    def _index_file_imports(self, file_path: str) -> None:
        try:
            with open(file_path, encoding="utf-8") as f:
                source = f.read()
        except OSError:
            log.warning("Could not read %s for import extraction", file_path)
            return

        # Lazily wire source_root into the extractor on first file processed.
        # Python uses detect_source_root to find the package boundary;
        # TypeScript uses the repository root directly.
        if hasattr(self._import_extractor, "_source_root") and not self._import_extractor._source_root:
            if self._language == "python":
                from synapse.lsp.python import detect_source_root
                self._import_extractor._source_root = detect_source_root(
                    file_path, self._root_path or ""
                )
            elif self._language == "typescript":
                self._import_extractor._source_root = self._root_path or ""

        results = self._import_extractor.extract(file_path, source)
        if not results:
            return

        for item in results:
            if isinstance(item, tuple):
                # Python: (module_path, imported_symbol_or_None)
                module_path, imported_name = item
                if imported_name:
                    # from X import Y -> edge to Y's full_name
                    upsert_symbol_imports(self._conn, file_path, f"{module_path}.{imported_name}")
                else:
                    # import X -> edge to module node
                    upsert_symbol_imports(self._conn, file_path, module_path)
            else:
                # C#: plain string package name
                # IMPORTS edges only write when the Package node exists; external namespaces
                # (e.g. System) are not indexed, so their using directives produce no graph edge.
                upsert_imports(self._conn, file_path, item)

    def _upsert_directory_chain(self, file_path: str, root_path: str) -> None:
        dirs: list[str] = []
        current = os.path.dirname(file_path)
        while True:
            dirs.append(current)
            if current == root_path or current == os.path.dirname(current):
                break
            current = os.path.dirname(current)

        dirs.reverse()  # root-first

        for dir_path in dirs:
            upsert_directory(self._conn, dir_path, os.path.basename(dir_path) or dir_path)

        for i in range(len(dirs) - 1):
            upsert_dir_contains(self._conn, dirs[i], dirs[i + 1])

        upsert_dir_contains(self._conn, dirs[-1], file_path)

    def _upsert_symbol(self, symbol: IndexSymbol) -> None:
        kind_str = symbol.kind.value
        # Python-specific kind overrides (C# kind_str stays as symbol.kind.value)
        if self._language == "python":
            if symbol.name == "__init__" and symbol.kind == SymbolKind.METHOD:
                kind_str = "constructor"
            elif symbol.kind == SymbolKind.METHOD and symbol.parent_full_name is None:
                # Top-level function (no parent = not inside a class)
                kind_str = "function"
            elif symbol.signature == "module" and symbol.kind == SymbolKind.CLASS:
                # LSP kind 2 (Module) -> :Class with kind='module' (per user decision)
                kind_str = "module"
        elif self._language == "typescript":
            if symbol.name == "constructor" and symbol.kind == SymbolKind.METHOD:
                kind_str = "constructor"
            elif symbol.kind == SymbolKind.METHOD and symbol.parent_full_name is None:
                # Module-scope function — same treatment as Python top-level function
                kind_str = "function"
            elif symbol.signature == "const_object" and symbol.kind == SymbolKind.CLASS:
                kind_str = "const_object"

        match symbol.kind:
            case SymbolKind.NAMESPACE:
                upsert_package(self._conn, symbol.full_name, symbol.name)
            case SymbolKind.INTERFACE:
                upsert_interface(self._conn, symbol.full_name, symbol.name, file_path=symbol.file_path, line=symbol.line, end_line=symbol.end_line, language=self._language)
            case SymbolKind.CLASS | SymbolKind.ABSTRACT_CLASS | SymbolKind.ENUM | SymbolKind.RECORD:
                upsert_class(self._conn, symbol.full_name, symbol.name, kind_str, file_path=symbol.file_path, line=symbol.line, end_line=symbol.end_line, language=self._language)
            case SymbolKind.METHOD:
                upsert_method(self._conn, symbol.full_name, symbol.name, symbol.signature, symbol.is_abstract, symbol.is_static, file_path=symbol.file_path, line=symbol.line, end_line=symbol.end_line, language=self._language, is_classmethod=symbol.is_classmethod, is_async=symbol.is_async)
            case SymbolKind.PROPERTY:
                upsert_property(self._conn, symbol.full_name, symbol.name, "", file_path=symbol.file_path, line=symbol.line, end_line=symbol.end_line, language=self._language)
            case SymbolKind.FIELD:
                upsert_field(self._conn, symbol.full_name, symbol.name, "", file_path=symbol.file_path, line=symbol.line, end_line=symbol.end_line, language=self._language)
            case _:
                log.debug("Skipping symbol of unhandled kind: %s", symbol.kind)

    def _index_callback_edges(
        self,
        symbols_by_file: dict[str, list[IndexSymbol]],
    ) -> None:
        """Create CALLS edges from parent methods to callback children.

        The TS LSP emits symbols like "foo.useEffect() callback" as children
        of "foo". Creating a CALLS edge connects these disconnected islands
        so trace_call_chain and find_entry_points can walk through them.
        """
        count = 0
        for syms in symbols_by_file.values():
            for sym in syms:
                if (
                    sym.kind == SymbolKind.METHOD
                    and sym.name.endswith("callback")
                    and sym.parent_full_name
                ):
                    upsert_calls(self._conn, sym.parent_full_name, sym.full_name)
                    count += 1
        if count:
            log.info("Created %d callback CALLS edges", count)

    def _index_attributes(
        self,
        file_path: str,
        source: str,
        symbols: list[IndexSymbol],
        extractor,
    ) -> None:
        if extractor is None:
            return
        results = extractor.extract(file_path, source)
        if not results:
            return

        # Build name -> full_name lookup scoped to this file
        name_to_full: dict[str, list[str]] = {}
        for sym in symbols:
            name_to_full.setdefault(sym.name, []).append(sym.full_name)

        for simple_name, attrs in results:
            full_names = name_to_full.get(simple_name, [])
            if len(full_names) == 1:
                set_attributes(self._conn, full_names[0], attrs)
                if self._language in ("python", "typescript"):
                    set_metadata_flags(self._conn, full_names[0], _attrs_to_flags(attrs))
            else:
                # Multiple symbols with same simple name in this file — set on all matches
                for fn in full_names:
                    set_attributes(self._conn, fn, attrs)
                    if self._language in ("python", "typescript"):
                        set_metadata_flags(self._conn, fn, _attrs_to_flags(attrs))

    def _index_base_types(
        self,
        file_path: str,
        source: str,
        name_to_full_names: dict[str, list[str]],
        kind_map: dict[str, SymbolKind],
    ) -> None:
        triples = self._base_type_extractor.extract(file_path, source)
        for type_simple, base_simple, is_first in triples:
            type_candidates = name_to_full_names.get(type_simple, [])
            base_candidates = name_to_full_names.get(base_simple, [])
            for type_full in type_candidates:
                type_kind = kind_map.get(type_full)
                for base_full in base_candidates:
                    if self._language == "python":
                        # Python has no interface distinction; all bases produce INHERITS edges
                        upsert_inherits(self._conn, type_full, base_full)
                    elif type_kind == SymbolKind.INTERFACE:
                        # Interfaces only extend other interfaces
                        upsert_interface_inherits(self._conn, type_full, base_full)
                    elif is_first:
                        # C# rule: first base of a class is the base class (INHERITS) if it's a
                        # class, or an interface (IMPLEMENTS) if it's an interface. Attempt both;
                        # typed MATCH labels ensure only the semantically correct edge writes.
                        upsert_inherits(self._conn, type_full, base_full)
                        upsert_implements(self._conn, type_full, base_full)
                    else:
                        # Non-first entries in a class base list are always interfaces
                        upsert_implements(self._conn, type_full, base_full)


_ATTR_TO_FLAG: dict[str, str] = {
    "abstractmethod": "is_abstract",
    "staticmethod": "is_static",
    "classmethod": "is_classmethod",
    "async": "is_async",
    "ABC": "is_abstract",
    # TypeScript markers (bare keyword names, no collision with Python decorated names)
    "abstract": "is_abstract",
    "static": "is_static",
}


def _attrs_to_flags(attrs: list[str]) -> dict:
    """Convert Python attribute markers (from PythonAttributeExtractor) to boolean flag dict."""
    flags: dict[str, bool] = {}
    for attr in attrs:
        flag_key = _ATTR_TO_FLAG.get(attr)
        if flag_key:
            flags[flag_key] = True
    return flags
