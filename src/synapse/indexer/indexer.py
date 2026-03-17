from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import TYPE_CHECKING

from synapse.graph.connection import GraphConnection
from synapse.graph.edges import (
    upsert_contains_symbol, upsert_dir_contains, upsert_file_contains_symbol,
    upsert_imports, upsert_inherits, upsert_interface_inherits, upsert_implements,
    upsert_repo_contains_dir,
)
from synapse.graph.nodes import (
    upsert_class, upsert_directory, upsert_field, upsert_file,
    upsert_interface, upsert_method, upsert_package, upsert_property,
    upsert_repository, delete_file_nodes,
    collect_summaries, restore_summaries,
    set_attributes,
)
from synapse.indexer.base_type_extractor import CSharpBaseTypeExtractor
from synapse.indexer.call_indexer import CallIndexer
from synapse.indexer.method_implements_indexer import MethodImplementsIndexer
from synapse.indexer.symbol_resolver import SymbolResolver
from synapse.lsp.interface import IndexSymbol, LSPAdapter, SymbolKind

if TYPE_CHECKING:
    from synapse.plugin import LanguagePlugin

log = logging.getLogger(__name__)


class Indexer:
    def __init__(self, conn: GraphConnection, lsp: LSPAdapter, plugin: LanguagePlugin | None = None) -> None:
        self._conn = conn
        self._lsp = lsp
        if plugin is not None:
            self._import_extractor = plugin.create_import_extractor()
            self._base_type_extractor = plugin.create_base_type_extractor()
            self._attribute_extractor_factory = plugin.create_attribute_extractor
            self._call_extractor_factory = plugin.create_call_extractor
            self._type_ref_extractor_factory = plugin.create_type_ref_extractor
            self._file_extensions = plugin.file_extensions
            self._language = plugin.name
        else:
            from synapse.indexer.import_extractor import CSharpImportExtractor
            self._import_extractor = CSharpImportExtractor()
            self._base_type_extractor = CSharpBaseTypeExtractor()
            self._attribute_extractor_factory = None
            self._call_extractor_factory = None
            self._type_ref_extractor_factory = None
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
        files = self._lsp.get_workspace_files(root_path)
        symbols_by_file: dict[str, list[IndexSymbol]] = {}

        if on_progress:
            on_progress(f"Indexing {len(files)} files...")

        for file_path in files:
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
            from synapse.indexer.attribute_extractor import CSharpAttributeExtractor
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
        SymbolResolver(
            self._conn,
            self._lsp.language_server,
            call_extractor=call_ext,
            type_ref_extractor=type_ref_ext,
            name_to_full_names=name_to_full_names,
            file_extensions=self._file_extensions,
        ).resolve(root_path, symbol_map, class_symbol_map=class_symbol_map)

        if not keep_lsp_running:
            self._lsp.shutdown()

    def reindex_file(self, file_path: str, root_path: str) -> None:
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
                from synapse.indexer.attribute_extractor import CSharpAttributeExtractor
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
        SymbolResolver(
            self._conn,
            self._lsp.language_server,
            call_extractor=call_ext,
            type_ref_extractor=type_ref_ext,
            name_to_full_names=name_to_full_names,
            file_extensions=self._file_extensions,
        ).resolve_single_file(file_path, symbol_map, class_symbol_map=class_symbol_map)

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
        # IMPORTS edges only write when the Package node exists; external namespaces (e.g. System)
        # are not indexed, so their using directives are tracked but produce no graph edge.
        for pkg_name in self._import_extractor.extract(file_path, source):
            upsert_imports(self._conn, file_path, pkg_name)

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
        match symbol.kind:
            case SymbolKind.NAMESPACE:
                upsert_package(self._conn, symbol.full_name, symbol.name)
            case SymbolKind.INTERFACE:
                upsert_interface(self._conn, symbol.full_name, symbol.name, file_path=symbol.file_path, line=symbol.line, end_line=symbol.end_line)
            case SymbolKind.CLASS | SymbolKind.ABSTRACT_CLASS | SymbolKind.ENUM | SymbolKind.RECORD:
                upsert_class(self._conn, symbol.full_name, symbol.name, symbol.kind.value, file_path=symbol.file_path, line=symbol.line, end_line=symbol.end_line)
            case SymbolKind.METHOD:
                upsert_method(self._conn, symbol.full_name, symbol.name, symbol.signature, symbol.is_abstract, symbol.is_static, file_path=symbol.file_path, line=symbol.line, end_line=symbol.end_line)
            case SymbolKind.PROPERTY:
                upsert_property(self._conn, symbol.full_name, symbol.name, "", file_path=symbol.file_path, line=symbol.line, end_line=symbol.end_line)
            case SymbolKind.FIELD:
                upsert_field(self._conn, symbol.full_name, symbol.name, "", file_path=symbol.file_path, line=symbol.line, end_line=symbol.end_line)
            case _:
                log.debug("Skipping symbol of unhandled kind: %s", symbol.kind)

    def _index_attributes(
        self,
        file_path: str,
        source: str,
        symbols: list[IndexSymbol],
        extractor,
    ) -> None:
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
            else:
                # Multiple symbols with same simple name in this file — set on all matches
                for fn in full_names:
                    set_attributes(self._conn, fn, attrs)

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
                    if type_kind == SymbolKind.INTERFACE:
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
