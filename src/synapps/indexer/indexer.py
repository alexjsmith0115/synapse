from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from synapps.graph.connection import GraphConnection
from synapps.graph.edges import (
    delete_outgoing_edges_for_file,
    upsert_calls, upsert_contains_symbol, upsert_dir_contains, upsert_file_contains_symbol,
    upsert_imports, upsert_module_calls, upsert_symbol_imports, upsert_inherits, upsert_interface_inherits, upsert_implements,
    upsert_repo_contains_dir,
)
from synapps.graph.nodes import (
    upsert_class, upsert_directory, upsert_field, upsert_file,
    upsert_interface, upsert_method, upsert_package, upsert_property,
    upsert_repository, delete_file_nodes,
    collect_summaries, restore_summaries,
    get_file_symbol_names, delete_orphaned_symbols,
    set_attributes, set_metadata_flags,
)
from synapps.indexer.csharp.csharp_base_type_extractor import CSharpBaseTypeExtractor
from synapps.indexer.method_implements_indexer import MethodImplementsIndexer
from synapps.indexer.overrides_indexer import OverridesIndexer
from synapps.indexer.symbol_resolver import SymbolResolver
from synapps.lsp.interface import IndexSymbol, LSPAdapter, LSPResolverBackend, SymbolKind

from synapps.indexer.tree_sitter_util import node_text

if TYPE_CHECKING:
    from tree_sitter import Tree
    from synapps.indexer.tree_sitter_util import ParsedFile
    from synapps.plugin import LanguagePlugin

log = logging.getLogger(__name__)

_MINIFIED_LINE_THRESHOLD = 500


def _parse_csharp_source(source: str):
    """Parse C# source into a tree-sitter Tree (used by legacy indexer path)."""
    import tree_sitter_c_sharp
    from tree_sitter import Language, Parser
    lang = Language(tree_sitter_c_sharp.language())
    parser = Parser(lang)
    return parser.parse(bytes(source, "utf-8"))


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


def _is_minified_source(source: str) -> bool:
    """Return True if the source's first non-empty line exceeds the minified threshold."""
    newline = source.find('\n')
    first_line = source[:newline] if newline != -1 else source
    stripped = first_line.strip()
    return len(stripped) > _MINIFIED_LINE_THRESHOLD if stripped else False


def _extract_java_package(tree: Tree) -> str | None:
    """Extract the package name from a Java file's tree-sitter AST.

    Returns the fully qualified package name (e.g. 'com.synappstest') or None
    if no package declaration is found.
    """
    for child in tree.root_node.children:
        if child.type == "package_declaration":
            for sub in child.children:
                if sub.type in ("scoped_identifier", "identifier"):
                    return node_text(sub)
    return None


class Indexer:
    def __init__(self, conn: GraphConnection, lsp: LSPAdapter, plugin: LanguagePlugin | None = None) -> None:
        self._conn = conn
        self._lsp = lsp
        self._root_path: str = ""
        if plugin is not None:
            self._plugin = plugin
            self._import_extractor = plugin.create_import_extractor()
            self._base_type_extractor = plugin.create_base_type_extractor()
            self._attribute_extractor_factory = plugin.create_attribute_extractor
            self._call_extractor_factory = plugin.create_call_extractor
            self._type_ref_extractor_factory = plugin.create_type_ref_extractor
            self._assignment_extractor_factory = getattr(plugin, 'create_assignment_extractor', None)
            self._http_extractor_factory = getattr(plugin, 'create_http_extractor', None)
            self._file_extensions = plugin.file_extensions
            self._language = plugin.name
            self._http_extraction_results: list = []
        else:
            from synapps.plugin.csharp import CSharpPlugin
            from synapps.indexer.csharp.csharp_import_extractor import CSharpImportExtractor
            self._plugin = CSharpPlugin()
            self._import_extractor = CSharpImportExtractor()
            self._base_type_extractor = CSharpBaseTypeExtractor()
            self._attribute_extractor_factory = None
            self._call_extractor_factory = None
            self._type_ref_extractor_factory = None
            self._assignment_extractor_factory = None
            self._http_extractor_factory = None
            self._file_extensions = frozenset({".cs"})
            self._language = "csharp"
            self._http_extraction_results: list = []

    def index_project(
        self,
        root_path: str,
        language: str,
        keep_lsp_running: bool = False,
        on_progress: Callable[[str], None] | None = None,
        files: list[str] | None = None,
    ) -> None:
        root_path = root_path.rstrip("/")
        self._root_path = root_path

        if files is None:
            files = self._lsp.get_workspace_files(root_path)

        # Build parsed_cache: read each file once, check minification, parse tree
        parsed_cache: dict[str, ParsedFile] = {}
        for file_path in files:
            try:
                with open(file_path, encoding="utf-8") as f:
                    source = f.read()
            except OSError:
                continue
            if _is_minified_source(source):
                log.debug("Skipping minified file: %s", file_path)
                continue
            try:
                parsed_cache[file_path] = self._plugin.parse_file(file_path, source)
            except Exception:
                log.warning("tree-sitter failed to parse %s", file_path)
                continue

        # Pre-scan: detect ABC/Protocol classes so they can be promoted to :Interface
        # during the structural pass. Cache results for reuse in the attribute phase.
        interface_classes: set[tuple[str, str]] = set()  # (file_path, class_name)
        cached_attr_results: dict[str, list[tuple[str, list[str]]]] = {}
        if self._language == "python" and self._attribute_extractor_factory is not None:
            pre_attr_ext = self._attribute_extractor_factory()
            if pre_attr_ext is not None:
                for file_path, pf in parsed_cache.items():
                    try:
                        results = pre_attr_ext.extract(file_path, pf.tree)
                        if results:
                            cached_attr_results[file_path] = results
                            for name, markers in results:
                                if _INTERFACE_MARKERS & set(markers):
                                    interface_classes.add((file_path, name))
                    except Exception:
                        pass

        if on_progress:
            on_progress(f"Indexing {len(files)} files...")

        # Structural pass
        symbols_by_file: dict[str, list[IndexSymbol]] = {}
        total_symbols = 0
        timed_out_files: list[str] = []
        t_structural = time.monotonic()
        for file_path, pf in parsed_cache.items():
            try:
                symbols = self._lsp.get_document_symbols(file_path)
            except TimeoutError:
                timed_out_files.append(file_path)
                log.warning("Language server timed out on %s -- skipping", file_path)
                continue
            # Promote ABC/Protocol classes to INTERFACE kind
            for sym in symbols:
                if sym.kind == SymbolKind.CLASS and (file_path, sym.name) in interface_classes:
                    sym.kind = SymbolKind.INTERFACE
            symbols_by_file[file_path] = symbols
            total_symbols += len(symbols)
            self._index_file_structure(file_path, root_path, symbols, pf)
        log.info(
            "Structural pass: %d files, %d symbols in %.1fs",
            len(parsed_cache), total_symbols, time.monotonic() - t_structural,
        )
        if timed_out_files:
            names = ", ".join(timed_out_files[:3])
            more = f" and {len(timed_out_files) - 3} more" if len(timed_out_files) > 3 else ""
            log.warning(
                "Language server timed out on %d file(s): %s%s. "
                "Re-run with --verbose for details.",
                len(timed_out_files), names, more,
            )

        upsert_repository(self._conn, root_path, language)
        upsert_repo_contains_dir(self._conn, root_path, root_path)

        # Build lookup tables for the base type resolution pass
        name_to_full_names: dict[str, list[str]] = {}
        kind_map: dict[str, SymbolKind] = {}
        for syms in symbols_by_file.values():
            for sym in syms:
                name_to_full_names.setdefault(sym.name, []).append(sym.full_name)
                kind_map[sym.full_name] = sym.kind

        _TYPE_KINDS = {SymbolKind.CLASS, SymbolKind.INTERFACE, SymbolKind.ABSTRACT_CLASS, SymbolKind.ENUM, SymbolKind.RECORD}
        base_type_symbol_map: dict[tuple[str, int], str] = {}
        for syms in symbols_by_file.values():
            for sym in syms:
                if sym.kind in _TYPE_KINDS:
                    base_type_symbol_map[(sym.file_path, sym.line)] = sym.full_name

        if on_progress:
            on_progress("Resolving base types...")

        # Base type pass
        t_base = time.monotonic()
        for file_path, pf in parsed_cache.items():
            self._index_base_types(
                file_path, pf.tree, base_type_symbol_map, kind_map,
                self._lsp.language_server, root_path, name_to_full_names,
            )
        log.info("Base type resolution: %.1fs", time.monotonic() - t_base)

        if on_progress:
            on_progress("Extracting attributes...")

        # Attribute pass
        t_attr = time.monotonic()
        if self._attribute_extractor_factory is not None:
            attr_extractor = self._attribute_extractor_factory()
        else:
            from synapps.indexer.csharp.csharp_attribute_extractor import CSharpAttributeExtractor
            attr_extractor = CSharpAttributeExtractor()
        for file_path, pf in parsed_cache.items():
            try:
                file_symbols = symbols_by_file.get(file_path, [])
                if file_path in cached_attr_results:
                    # Reuse pre-scan results
                    self._index_attributes_from_results(
                        file_path, cached_attr_results[file_path], file_symbols,
                    )
                else:
                    self._index_attributes(file_path, pf.tree, file_symbols, attr_extractor)
            except Exception:
                log.warning("Could not process %s for attribute extraction", file_path)
        log.info("Attribute extraction: %.1fs", time.monotonic() - t_attr)

        # Phase 4: HTTP endpoint extraction
        # Extraction only — matching and graph writes happen at the project
        # level in SynappsService after all languages have been extracted.
        if self._http_extractor_factory is not None:
            from synapps.indexer.http.interface import HttpExtractionResult
            http_extractor = self._http_extractor_factory()
            for fp, pf in parsed_cache.items():
                try:
                    file_symbols = symbols_by_file.get(fp, [])
                    self._http_extraction_results.append(
                        http_extractor.extract(fp, pf.tree, file_symbols),
                    )
                except Exception:
                    log.warning("Could not extract HTTP endpoints from %s", fp)

        # Phase 1.5: method-level IMPLEMENTS edges (requires all class-level IMPLEMENTS to exist)
        MethodImplementsIndexer(self._conn).index()

        # Phase 1.6: callback CALLS edges — connect parent methods to their callback children.
        # TS LSP names callback symbols like "foo.useEffect() callback"; create a CALLS edge
        # from the parent method to the callback so traversal tools can walk through them.
        self._index_callback_edges(symbols_by_file)

        if on_progress:
            on_progress("Resolving call edges...")

        all_symbols = [sym for syms in symbols_by_file.values() for sym in syms]
        self._resolve_calls_and_refs(
            root_path, all_symbols, files, name_to_full_names,
            parsed_cache=parsed_cache,
        )

        if not keep_lsp_running:
            self._lsp.shutdown()

    def reindex_file(self, file_path: str, root_path: str) -> None:
        self._root_path = root_path

        # Read file once and build ParsedFile for reuse across all phases
        try:
            with open(file_path, encoding="utf-8") as f:
                source = f.read()
            pf = self._plugin.parse_file(file_path, source)
        except OSError:
            log.warning("Could not read %s for reindexing", file_path)
            return

        # D-12: capture existing symbols BEFORE upsert for orphan detection
        old_symbol_names = get_file_symbol_names(self._conn, file_path)

        symbols = self._lsp.get_document_symbols(file_path)

        # Pre-scan: promote ABC/Protocol classes to :Interface before structural pass
        cached_attr_results: list[tuple[str, list[str]]] | None = None
        if self._language == "python" and self._attribute_extractor_factory is not None:
            pre_attr_ext = self._attribute_extractor_factory()
            if pre_attr_ext is not None:
                try:
                    results = pre_attr_ext.extract(file_path, pf.tree)
                    if results:
                        cached_attr_results = results
                        interface_names = {
                            name for name, markers in results
                            if _INTERFACE_MARKERS & set(markers)
                        }
                        for sym in symbols:
                            if sym.kind == SymbolKind.CLASS and sym.name in interface_names:
                                sym.kind = SymbolKind.INTERFACE
                except Exception:
                    pass

        # D-12: upsert structure (MERGE updates in place, preserves summaries)
        self._index_file_structure(file_path, root_path, symbols, pf)

        # D-12: delete orphaned symbols (removed from source but still in graph)
        new_symbol_names = {sym.full_name for sym in symbols}
        delete_orphaned_symbols(self._conn, file_path, new_symbol_names)

        name_to_full_names: dict[str, list[str]] = {}
        kind_map: dict[str, SymbolKind] = {}
        for sym in symbols:
            name_to_full_names.setdefault(sym.name, []).append(sym.full_name)
            kind_map[sym.full_name] = sym.kind

        _TYPE_KINDS = {SymbolKind.CLASS, SymbolKind.INTERFACE, SymbolKind.ABSTRACT_CLASS, SymbolKind.ENUM, SymbolKind.RECORD}

        # Delete outgoing resolution edges BEFORE re-resolving so that
        # newly created IMPLEMENTS/INHERITS edges aren't immediately removed.
        delete_outgoing_edges_for_file(self._conn, file_path)

        # Build cross-file symbol maps from the graph so that LSP-resolved
        # definitions in OTHER files can be matched.  Overlay the current
        # file's fresh symbols so the map reflects the latest on-disk state.
        base_type_symbol_map = self._build_graph_symbol_map(
            "Class", "Interface", extra_labels=("Enum",),
        )
        for sym in symbols:
            if sym.kind in _TYPE_KINDS:
                base_type_symbol_map[(sym.file_path, sym.line)] = sym.full_name

        self._index_base_types(
            file_path, pf.tree, base_type_symbol_map, kind_map,
            self._lsp.language_server, root_path, name_to_full_names,
        )
        if cached_attr_results is not None:
            self._index_attributes_from_results(file_path, cached_attr_results, symbols)
        else:
            if self._attribute_extractor_factory is not None:
                attr_extractor = self._attribute_extractor_factory()
            else:
                from synapps.indexer.csharp.csharp_attribute_extractor import CSharpAttributeExtractor
                attr_extractor = CSharpAttributeExtractor()
            self._index_attributes(file_path, pf.tree, symbols, attr_extractor)

        # Build a cross-file method symbol_map from the graph, overlaying
        # fresh symbols from the current file so CALLS resolution can match
        # callee definitions in any file.
        all_symbols_for_resolver = self._build_all_symbols_for_resolver(symbols)

        parsed_cache = {file_path: pf}
        self._resolve_calls_and_refs(
            root_path, all_symbols_for_resolver, [file_path], name_to_full_names,
            single_file=file_path,
            parsed_cache=parsed_cache,
        )

        # Recreate DISPATCHES_TO edges (graph-only, no LSP needed).
        MethodImplementsIndexer(self._conn).index()

    def _resolve_calls_and_refs(
        self,
        root_path: str,
        all_symbols: list[IndexSymbol],
        files: list[str],
        name_to_full_names: dict[str, list[str]],
        *,
        single_file: str | None = None,
        parsed_cache: dict[str, ParsedFile] | None = None,
    ) -> None:
        """Build resolution context and run SymbolResolver for CALLS + REFERENCES edges.

        When ``single_file`` is provided, only that file is resolved (used by reindex_file).
        ``parsed_cache`` provides pre-parsed trees so files don't need to be re-read.
        """
        _CLASS_KINDS = {SymbolKind.CLASS, SymbolKind.ABSTRACT_CLASS, SymbolKind.INTERFACE}
        symbol_map = {
            (sym.file_path, sym.line): sym.full_name
            for sym in all_symbols
            if sym.kind == SymbolKind.METHOD
        }
        class_symbol_map = {
            (sym.file_path, sym.line): sym.full_name
            for sym in all_symbols
            if sym.kind in _CLASS_KINDS
        }

        call_ext = self._call_extractor_factory() if self._call_extractor_factory else None
        type_ref_ext = self._type_ref_extractor_factory() if self._type_ref_extractor_factory else None

        # Build module_full_names set and wire module_name_resolver for Python/TypeScript
        module_full_names: set[str] = set()
        module_map: dict[str, str] = {}
        if self._language in ("python", "typescript"):
            for sym in all_symbols:
                if sym.signature == "module" and sym.kind == SymbolKind.CLASS:
                    module_full_names.add(sym.full_name)
                    module_map[sym.file_path] = sym.full_name
            if call_ext is not None and hasattr(call_ext, "_module_name_resolver"):
                call_ext._module_name_resolver = lambda fp, _m=module_map: _m.get(fp)

        # Build assignment maps if plugin supports it
        from synapps.indexer.assignment_ref import AssignmentRef
        assignment_position_map: dict[tuple[str, int], AssignmentRef] = {}
        if self._assignment_extractor_factory is not None:
            assign_ext = self._assignment_extractor_factory()
            if assign_ext is not None:
                _CLASS_KINDS_for_lines = {SymbolKind.CLASS, SymbolKind.ABSTRACT_CLASS}
                class_lines_per_file: dict[str, list[tuple[int, str]]] = {}
                for sym in all_symbols:
                    if sym.kind in _CLASS_KINDS_for_lines:
                        class_lines_per_file.setdefault(sym.file_path, []).append(
                            (sym.line, sym.full_name)
                        )
                for cls_lines in class_lines_per_file.values():
                    cls_lines.sort()

                semantic_map: dict[tuple[str, str], AssignmentRef] = {}
                _pc = parsed_cache or {}
                for file_path in files:
                    if file_path in _pc:
                        tree = _pc[file_path].tree
                    else:
                        # Fallback for reindex_file path where parsed_cache may not cover this file
                        try:
                            with open(file_path, encoding="utf-8", errors="ignore") as f:
                                source = f.read()
                            tree = self._plugin.parse_file(file_path, source).tree
                        except OSError:
                            continue
                    try:
                        refs = assign_ext.extract(
                            file_path, tree, symbol_map,
                            class_lines=class_lines_per_file.get(file_path),
                            module_name_resolver=module_map.get if module_map else None,
                        )
                        for ref in refs:
                            semantic_map[(ref.class_full_name, ref.field_name)] = ref
                    except Exception:
                        pass

                for ref in semantic_map.values():
                    assignment_position_map[(ref.source_file, ref.source_line)] = ref

                if semantic_map:
                    log.info(
                        "Built assignment maps: %d semantic entries, %d position entries",
                        len(semantic_map), len(assignment_position_map),
                    )

        # Build import map for TypeScript import-based call fallback
        import_map: dict[str, dict[str, str]] | None = None
        if self._language == "typescript" and self._import_extractor is not None and parsed_cache:
            from synapps.indexer.typescript.typescript_import_extractor import build_import_map as _build_import_map
            file_trees = {fp: pf.tree for fp, pf in parsed_cache.items()}
            import_map = _build_import_map(self._import_extractor, file_trees)
            if import_map:
                log.info("Built import map: %d files with named imports", len(import_map))

        # Pre-build class_lines_per_file for the resolver so it doesn't have to
        # recompute from class_symbol_map on each call.
        resolver_class_lines: dict[str, list[tuple[int, str]]] = {}
        for (fp, line), full_name in class_symbol_map.items():
            resolver_class_lines.setdefault(fp, []).append((line, full_name))
        for entries in resolver_class_lines.values():
            entries.sort()

        resolver = SymbolResolver(
            self._conn,
            self._lsp.language_server,
            call_extractor=call_ext,
            type_ref_extractor=type_ref_ext,
            name_to_full_names=name_to_full_names,
            file_extensions=self._file_extensions,
            module_full_names=module_full_names,
            assignment_position_map=assignment_position_map,
            parsed_cache=parsed_cache,
            class_lines_per_file=resolver_class_lines,
            import_map=import_map,
        )
        if single_file:
            resolver.resolve_single_file(single_file, symbol_map, class_symbol_map=class_symbol_map)
        else:
            resolver.resolve(root_path, symbol_map, class_symbol_map=class_symbol_map)

        # Per-site DEBUG logging for unresolved call sites
        if self._language in ("python", "typescript", "java") and hasattr(resolver, "_unresolved_sites"):
            for site_msg in resolver._unresolved_sites:
                log.debug(site_msg)

        # Resolution summary
        if self._language in ("python", "typescript", "java") and call_ext is not None:
            total = getattr(call_ext, "_sites_seen", 0)
            if isinstance(total, int) and total > 0:
                calls_count_rows = self._conn.query(
                    "MATCH ()-[r:CALLS]->() WHERE r.call_sites IS NOT NULL RETURN count(r)"
                )
                resolved = calls_count_rows[0][0] if calls_count_rows else 0
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

        # OVERRIDES detection (pure Cypher, no LSP needed)
        if self._language in ("python", "typescript", "java", "csharp"):
            OverridesIndexer(self._conn).index()

    def _build_graph_symbol_map(
        self, *labels: str, extra_labels: tuple[str, ...] = (),
    ) -> dict[tuple[str, int], str]:
        """Query the graph for all nodes of the given labels and return a symbol map.

        Returns a dict of ``{(file_path, line): full_name}`` for use as a
        cross-file lookup when reindexing a single file.
        """
        all_labels = list(labels) + list(extra_labels)
        label_clause = " OR ".join(f"n:{lbl}" for lbl in all_labels)
        rows = self._conn.query(
            f"MATCH (n) WHERE ({label_clause}) AND n.file_path IS NOT NULL "
            f"RETURN n.file_path, n.line, n.full_name",
        )
        return {(r[0], r[1]): r[2] for r in rows if r[0] is not None and r[1] is not None}

    def _build_all_symbols_for_resolver(
        self, local_symbols: list[IndexSymbol],
    ) -> list[IndexSymbol]:
        """Build a symbol list for SymbolResolver that includes all Method nodes
        from the graph plus fresh local symbols.

        This ensures the ``symbol_map`` inside ``_resolve_calls_and_refs`` can
        resolve callee definitions in ANY file, not just the file being reindexed.
        """
        rows = self._conn.query(
            "MATCH (m:Method) WHERE m.file_path IS NOT NULL "
            "RETURN m.file_path, m.line, m.full_name"
        )
        # Start with graph data, overlay local symbols (which may be fresher)
        local_keys = {(sym.file_path, sym.line) for sym in local_symbols if sym.kind == SymbolKind.METHOD}
        result = list(local_symbols)
        for file_path, line, full_name in rows:
            if file_path is not None and line is not None and (file_path, line) not in local_keys:
                result.append(IndexSymbol(
                    name=full_name.rsplit(".", 1)[-1],
                    full_name=full_name,
                    kind=SymbolKind.METHOD,
                    file_path=file_path,
                    line=line,
                ))
        return result

    def delete_file(self, file_path: str) -> None:
        delete_file_nodes(self._conn, file_path)

    def _index_file_structure(
        self,
        file_path: str,
        root_path: str,
        symbols: list[IndexSymbol],
        parsed_file: ParsedFile | None = None,
    ) -> None:
        upsert_file(self._conn, file_path, os.path.basename(file_path), self._language)
        self._upsert_directory_chain(file_path, root_path)
        if parsed_file is not None:
            self._index_file_imports(file_path, parsed_file.tree)
        else:
            self._index_file_imports(file_path)

        for symbol in symbols:
            self._upsert_symbol(symbol)
            if symbol.parent_full_name is None:
                upsert_file_contains_symbol(self._conn, file_path, symbol.full_name)
            else:
                upsert_contains_symbol(self._conn, symbol.parent_full_name, symbol.full_name)

        # Java field type post-pass: patch Field nodes with type_name after initial upsert
        if self._language == "java" and parsed_file is not None:
            from synapps.indexer.java.java_field_type_extractor import JavaFieldTypeExtractor
            name_to_type = dict(JavaFieldTypeExtractor().extract(file_path, parsed_file.tree))
            for symbol in symbols:
                if symbol.kind == SymbolKind.FIELD:
                    symbol.type_name = name_to_type.get(symbol.name, "")
                    upsert_field(
                        self._conn, symbol.full_name, symbol.name, symbol.type_name,
                        file_path=symbol.file_path, line=symbol.line,
                        end_line=symbol.end_line, language=self._language,
                    )

        # Wire Java Package -> Class/Interface CONTAINS edges (per D-05, D-06)
        if self._language == "java" and parsed_file is not None:
            pkg_name = _extract_java_package(parsed_file.tree)
            if pkg_name:
                pkg_simple = pkg_name.rsplit(".", 1)[-1]
                upsert_package(self._conn, pkg_name, pkg_simple)
                for symbol in symbols:
                    if symbol.parent_full_name is None and symbol.kind in (
                        SymbolKind.CLASS, SymbolKind.INTERFACE, SymbolKind.ABSTRACT_CLASS,
                        SymbolKind.ENUM, SymbolKind.RECORD,
                    ):
                        upsert_contains_symbol(self._conn, pkg_name, symbol.full_name)

    def _index_file_imports(self, file_path: str, tree: Tree | None = None) -> None:
        if tree is None:
            # Fallback: read file from disk (used by reindex_file path)
            try:
                with open(file_path, encoding="utf-8") as f:
                    source = f.read()
            except OSError:
                log.warning("Could not read %s for import extraction", file_path)
                return
            if self._language == "csharp":
                tree = _parse_csharp_source(source)
            else:
                tree = self._plugin.parse_file(file_path, source).tree

        # Lazily wire source_root into the extractor on first file processed.
        # Python uses detect_source_root to find the package boundary;
        # TypeScript uses the repository root directly.
        # Java uses per-file source root detection (JI-04) — run every time.
        if hasattr(self._import_extractor, "_source_root") and not self._import_extractor._source_root:
            if self._language == "python":
                from synapps.lsp.python import detect_source_root
                self._import_extractor._source_root = detect_source_root(
                    file_path, self._root_path or ""
                )
            elif self._language == "typescript":
                self._import_extractor._source_root = self._root_path or ""
        if self._language == "java":
            from synapps.lsp.java import _detect_java_source_root
            self._import_extractor._source_root = _detect_java_source_root(
                file_path, self._root_path or ""
            )

        results = self._import_extractor.extract(file_path, tree)
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
            elif self._language == "java":
                if item.endswith(".*"):
                    # Wildcard import: strip .* and match Package node (JI-02)
                    upsert_imports(self._conn, file_path, item[:-2])
                else:
                    # Class import: match any node by full_name (JI-01)
                    upsert_symbol_imports(self._conn, file_path, item)
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
        elif self._language == "java":
            # Promote constructors: in Java, constructors share the class name
            if symbol.kind == SymbolKind.METHOD and symbol.parent_full_name:
                parent_simple = symbol.parent_full_name.rsplit(".", 1)[-1]
                if symbol.name == parent_simple:
                    kind_str = "constructor"

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
                upsert_field(self._conn, symbol.full_name, symbol.name, symbol.type_name, file_path=symbol.file_path, line=symbol.line, end_line=symbol.end_line, language=self._language)
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
        tree: Tree,
        symbols: list[IndexSymbol],
        extractor,
    ) -> None:
        if extractor is None:
            return
        results = extractor.extract(file_path, tree)
        if not results:
            return

        # Build name -> full_name lookup scoped to this file
        name_to_full: dict[str, list[str]] = {}
        # Also build "ParentSimple.MethodSimple" -> [full_names] for disambiguation
        qualified_to_full: dict[str, list[str]] = {}
        for sym in symbols:
            name_to_full.setdefault(sym.name, []).append(sym.full_name)
            # Java LSP includes param signatures in method names (e.g. "legacyMethod()")
            # but tree-sitter extractors return bare identifiers ("legacyMethod").
            # Index the base name (without parens) as a fallback key.
            if "(" in sym.name:
                base_name = sym.name[:sym.name.index("(")]
                name_to_full.setdefault(base_name, []).append(sym.full_name)
            if sym.parent_full_name:
                parent_simple = sym.parent_full_name.rsplit(".", 1)[-1]
                qual_key = f"{parent_simple}.{sym.name}"
                qualified_to_full.setdefault(qual_key, []).append(sym.full_name)
                if "(" in sym.name:
                    base_qual = f"{parent_simple}.{sym.name[:sym.name.index('(')]}"
                    qualified_to_full.setdefault(base_qual, []).append(sym.full_name)

        resolved = 0
        for result_name, attrs in results:
            # Try qualified lookup first (e.g., "IAnimal.speak"), fall back to simple
            full_names = qualified_to_full.get(result_name) or name_to_full.get(result_name, [])
            if not full_names:
                log.debug(
                    "Attribute name '%s' not found in %d file symbols for %s",
                    result_name, len(symbols), file_path,
                )
            for fn in full_names:
                set_attributes(self._conn, fn, attrs)
                if self._language in ("python", "typescript", "java", "csharp"):
                    set_metadata_flags(self._conn, fn, _attrs_to_flags(attrs))
                resolved += 1
        log.debug(
            "Attribute extraction: %d extractor results, %d graph writes for %s",
            len(results), resolved, file_path,
        )

    def _index_attributes_from_results(
        self,
        file_path: str,
        results: list[tuple[str, list[str]]],
        symbols: list[IndexSymbol],
    ) -> None:
        """Apply pre-computed attribute results to graph nodes."""
        name_to_full: dict[str, list[str]] = {}
        qualified_to_full: dict[str, list[str]] = {}
        for sym in symbols:
            name_to_full.setdefault(sym.name, []).append(sym.full_name)
            if "(" in sym.name:
                base_name = sym.name[:sym.name.index("(")]
                name_to_full.setdefault(base_name, []).append(sym.full_name)
            if sym.parent_full_name:
                parent_simple = sym.parent_full_name.rsplit(".", 1)[-1]
                qual_key = f"{parent_simple}.{sym.name}"
                qualified_to_full.setdefault(qual_key, []).append(sym.full_name)
                if "(" in sym.name:
                    base_qual = f"{parent_simple}.{sym.name[:sym.name.index('(')]}"
                    qualified_to_full.setdefault(base_qual, []).append(sym.full_name)

        resolved = 0
        for result_name, attrs in results:
            full_names = qualified_to_full.get(result_name) or name_to_full.get(result_name, [])
            if not full_names:
                log.debug(
                    "Attribute name '%s' not found in %d file symbols for %s",
                    result_name, len(symbols), file_path,
                )
            for fn in full_names:
                set_attributes(self._conn, fn, attrs)
                if self._language in ("python", "typescript", "java", "csharp"):
                    set_metadata_flags(self._conn, fn, _attrs_to_flags(attrs))
                resolved += 1
        log.debug(
            "Attribute extraction: %d extractor results, %d graph writes for %s",
            len(results), resolved, file_path,
        )

    def _index_base_types(
        self,
        file_path: str,
        tree: Tree,
        symbol_map: dict[tuple[str, int], str],
        kind_map: dict[str, SymbolKind],
        ls: LSPResolverBackend,
        root_path: str,
        name_to_full_names: dict[str, list[str]],
    ) -> None:
        triples = self._base_type_extractor.extract(file_path, tree)
        log.debug("Base type extractor found %d triples for %s", len(triples), file_path)
        if not triples:
            return

        # Build file-scoped lookup: simple_name -> [full_name] for types in THIS file only.
        # Using the global name_to_full_names would match identically-named types across
        # namespaces (e.g. 3 "Cache" classes in different projects).
        file_type_names: dict[str, list[str]] = {}
        for (sm_path, _), full_name in symbol_map.items():
            if sm_path == file_path:
                simple = full_name.rsplit(".", 1)[-1]
                file_type_names.setdefault(simple, []).append(full_name)

        log.debug("file_type_names for %s: %s", file_path, dict(file_type_names))

        rel_path = os.path.relpath(file_path, root_path)
        try:
            with ls.open_file(rel_path):
                for type_simple, base_simple, is_first, line, col in triples:
                    try:
                        definitions = ls.request_definition(rel_path, line, col)
                    except Exception:
                        log.debug("LSP request_definition failed for %s:%d:%d", rel_path, line, col)
                        continue
                    log.debug(
                        "request_definition for '%s' at %s:%d:%d returned %d definitions",
                        base_simple, rel_path, line, col, len(definitions) if definitions else 0,
                    )
                    if not definitions:
                        log.debug("No definition for base type '%s' at %s:%d:%d", base_simple, rel_path, line, col)
                        continue
                    base_full: str | None = None
                    for defn in definitions:
                        abs_path = defn.get("absolutePath")
                        def_line = defn.get("range", {}).get("start", {}).get("line")
                        if abs_path is not None and def_line is not None:
                            base_full = symbol_map.get((abs_path, def_line))
                            if base_full is not None:
                                log.debug("Resolved base type '%s' -> '%s'", base_simple, base_full)
                                break
                    if base_full is None:
                        log.debug("Definition for '%s' not in symbol_map (external type)", base_simple)
                        continue
                    for type_full in file_type_names.get(type_simple, []):
                        log.debug(
                            "Declaring type '%s' resolved to %s",
                            type_simple, file_type_names.get(type_simple, []),
                        )
                        type_kind = kind_map.get(type_full)
                        if self._language in ("python", "java"):
                            base_kind = kind_map.get(base_full)
                            if type_kind == SymbolKind.INTERFACE:
                                upsert_interface_inherits(self._conn, type_full, base_full)
                            elif base_kind == SymbolKind.INTERFACE:
                                upsert_implements(self._conn, type_full, base_full)
                            else:
                                upsert_inherits(self._conn, type_full, base_full)
                        elif type_kind == SymbolKind.INTERFACE:
                            upsert_interface_inherits(self._conn, type_full, base_full)
                        elif is_first:
                            # C# rule: first base of a class is the base class (INHERITS) if it's a
                            # class, or an interface (IMPLEMENTS) if it's an interface. Attempt both;
                            # typed MATCH labels ensure only the semantically correct edge writes.
                            upsert_inherits(self._conn, type_full, base_full)
                            upsert_implements(self._conn, type_full, base_full)
                        else:
                            upsert_implements(self._conn, type_full, base_full)
        except Exception:
            log.warning("LSP open_file failed for %s, skipping base type resolution", rel_path)


_INTERFACE_MARKERS: frozenset[str] = frozenset({"ABC", "Protocol"})

_ATTR_TO_FLAG: dict[str, str] = {
    "abstractmethod": "is_abstract",
    "staticmethod": "is_static",
    "classmethod": "is_classmethod",
    "async": "is_async",
    "ABC": "is_abstract",
    "Protocol": "is_abstract",
    # Bare keyword modifiers shared by TypeScript, C#, and Java
    "abstract": "is_abstract",
    "static": "is_static",
    # Java markers (annotations and modifiers)
    "synchronized": "is_synchronized",
    "final": "is_final",
    "Override": "is_override",
    "Deprecated": "is_deprecated",
    "native": "is_native",
}


def _attrs_to_flags(attrs: list[str]) -> dict:
    """Convert Python attribute markers (from PythonAttributeExtractor) to boolean flag dict."""
    flags: dict[str, bool] = {}
    for attr in attrs:
        flag_key = _ATTR_TO_FLAG.get(attr)
        if flag_key:
            flags[flag_key] = True
    return flags
