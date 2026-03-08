from __future__ import annotations

import logging
import os

from synapse.graph.connection import GraphConnection
from synapse.graph.edges import (
    upsert_contains, upsert_contains_symbol,
    upsert_inherits, upsert_implements,
)
from synapse.graph.nodes import (
    upsert_class, upsert_directory, upsert_field, upsert_file,
    upsert_method, upsert_namespace, upsert_property, upsert_repository,
    delete_file_nodes,
)
from synapse.lsp.interface import IndexSymbol, LSPAdapter, SymbolKind

log = logging.getLogger(__name__)


class Indexer:
    def __init__(self, conn: GraphConnection, lsp: LSPAdapter) -> None:
        self._conn = conn
        self._lsp = lsp

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
        dir_path = os.path.dirname(file_path)
        dir_name = os.path.basename(dir_path)
        upsert_directory(self._conn, dir_path, dir_name)
        upsert_file(self._conn, file_path, os.path.basename(file_path), "csharp")
        upsert_contains(self._conn, from_path=dir_path, to_full_name=file_path)

        for symbol in symbols:
            self._upsert_symbol(symbol)
            upsert_contains(self._conn, from_path=file_path, to_full_name=symbol.full_name)

    def _upsert_symbol(self, symbol: IndexSymbol) -> None:
        match symbol.kind:
            case SymbolKind.NAMESPACE:
                upsert_namespace(self._conn, symbol.full_name, symbol.name)
            case SymbolKind.CLASS | SymbolKind.INTERFACE | SymbolKind.ABSTRACT_CLASS | SymbolKind.ENUM | SymbolKind.RECORD:
                upsert_class(self._conn, symbol.full_name, symbol.name, symbol.kind.value)
            case SymbolKind.METHOD:
                upsert_method(self._conn, symbol.full_name, symbol.name, symbol.signature, symbol.is_abstract, symbol.is_static)
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
                    upsert_inherits(self._conn, symbol.full_name, base_type)
                else:
                    upsert_implements(self._conn, symbol.full_name, base_type)
