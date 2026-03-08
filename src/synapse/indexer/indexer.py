from __future__ import annotations

import logging
import os

from synapse.graph.connection import GraphConnection
from synapse.graph.edges import (
    upsert_contains_symbol, upsert_dir_contains, upsert_file_contains_symbol,
    upsert_imports, upsert_inherits, upsert_interface_inherits, upsert_implements,
)
from synapse.graph.nodes import (
    upsert_class, upsert_directory, upsert_field, upsert_file,
    upsert_interface, upsert_method, upsert_package, upsert_property,
    upsert_repository, delete_file_nodes,
)
from synapse.indexer.base_type_extractor import CSharpBaseTypeExtractor
from synapse.indexer.call_indexer import CallIndexer
from synapse.indexer.import_extractor import CSharpImportExtractor
from synapse.lsp.interface import IndexSymbol, LSPAdapter, SymbolKind

log = logging.getLogger(__name__)


class Indexer:
    def __init__(self, conn: GraphConnection, lsp: LSPAdapter) -> None:
        self._conn = conn
        self._lsp = lsp
        self._import_extractor = CSharpImportExtractor()
        self._base_type_extractor = CSharpBaseTypeExtractor()

    def index_project(self, root_path: str, language: str, keep_lsp_running: bool = False) -> None:
        files = self._lsp.get_workspace_files(root_path)
        symbols_by_file: dict[str, list[IndexSymbol]] = {}

        for file_path in files:
            symbols = self._lsp.get_document_symbols(file_path)
            symbols_by_file[file_path] = symbols
            self._index_file_structure(file_path, root_path, symbols)

        for symbols in symbols_by_file.values():
            self._index_file_relationships(symbols)

        upsert_repository(self._conn, root_path, language)

        # Build lookup tables for the base type resolution pass
        name_to_full_names: dict[str, list[str]] = {}
        kind_map: dict[str, SymbolKind] = {}
        for syms in symbols_by_file.values():
            for sym in syms:
                name_to_full_names.setdefault(sym.name, []).append(sym.full_name)
                kind_map[sym.full_name] = sym.kind

        for file_path in files:
            try:
                with open(file_path, encoding="utf-8") as f:
                    source = f.read()
                self._index_base_types(file_path, source, name_to_full_names, kind_map)
            except OSError:
                log.warning("Could not read %s for base type extraction", file_path)

        # CALLS resolution requires all Method nodes to be present; must run after the structural pass
        symbol_map = {
            (sym.file_path, sym.line): sym.full_name
            for syms in symbols_by_file.values()
            for sym in syms
            if sym.kind == SymbolKind.METHOD
        }
        CallIndexer(self._conn, self._lsp.language_server).index_calls(root_path, symbol_map)

        if not keep_lsp_running:
            self._lsp.shutdown()

    def reindex_file(self, file_path: str, root_path: str) -> None:
        delete_file_nodes(self._conn, file_path)
        symbols = self._lsp.get_document_symbols(file_path)
        self._index_file_structure(file_path, root_path, symbols)
        self._index_file_relationships(symbols)

    def delete_file(self, file_path: str) -> None:
        delete_file_nodes(self._conn, file_path)

    def _index_file_structure(self, file_path: str, root_path: str, symbols: list[IndexSymbol]) -> None:
        self._upsert_directory_chain(file_path, root_path)
        upsert_file(self._conn, file_path, os.path.basename(file_path), "csharp")
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
                upsert_interface(self._conn, symbol.full_name, symbol.name)
            case SymbolKind.CLASS | SymbolKind.ABSTRACT_CLASS | SymbolKind.ENUM | SymbolKind.RECORD:
                upsert_class(self._conn, symbol.full_name, symbol.name, symbol.kind.value)
            case SymbolKind.METHOD:
                upsert_method(self._conn, symbol.full_name, symbol.name, symbol.signature, symbol.is_abstract, symbol.is_static, symbol.line)
            case SymbolKind.PROPERTY:
                upsert_property(self._conn, symbol.full_name, symbol.name, "")
            case SymbolKind.FIELD:
                upsert_field(self._conn, symbol.full_name, symbol.name, "")
            case _:
                log.debug("Skipping symbol of unhandled kind: %s", symbol.kind)

    def _index_file_relationships(self, symbols: list[IndexSymbol]) -> None:
        for symbol in symbols:
            for base_type in symbol.base_types:
                if symbol.kind == SymbolKind.INTERFACE:
                    upsert_interface_inherits(self._conn, symbol.full_name, base_type)
                elif symbol.kind in (SymbolKind.CLASS, SymbolKind.ABSTRACT_CLASS, SymbolKind.RECORD):
                    # Both edge functions' MATCH labels ensure only valid edges are written.
                    upsert_inherits(self._conn, symbol.full_name, base_type)
                    upsert_implements(self._conn, symbol.full_name, base_type)

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
