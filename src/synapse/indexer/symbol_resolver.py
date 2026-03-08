from __future__ import annotations

import logging
import os
from pathlib import Path

from synapse.graph.connection import GraphConnection
from synapse.graph.edges import upsert_calls, upsert_references
from synapse.indexer.call_extractor import TreeSitterCallExtractor
from synapse.indexer.type_ref_extractor import TreeSitterTypeRefExtractor, TypeRef
from synapse.lsp.util import build_full_name

log = logging.getLogger(__name__)

_METHOD_KINDS = {6, 9, 12}  # Method, Constructor, Function
_TYPE_KINDS = {5, 11}  # Class, Interface


class SymbolResolver:
    """
    Walks .cs files once, runs call extraction and type reference extraction,
    then resolves both via LSP and writes CALLS and REFERENCES edges.
    """

    def __init__(
        self,
        conn: GraphConnection,
        ls: object,
        call_extractor: TreeSitterCallExtractor | None = None,
        type_ref_extractor: TreeSitterTypeRefExtractor | None = None,
    ) -> None:
        self._conn = conn
        self._ls = ls
        self._call_extractor = call_extractor or TreeSitterCallExtractor()
        self._type_ref_extractor = type_ref_extractor or TreeSitterTypeRefExtractor()

    def resolve(
        self,
        root_path: str,
        symbol_map: dict[tuple[str, int], str],
    ) -> None:
        for file_path in self._iter_cs_files(root_path):
            try:
                source = Path(file_path).read_text(encoding="utf-8", errors="ignore")
            except OSError:
                log.warning("Could not read %s", file_path)
                continue
            self._resolve_file(file_path, source, symbol_map)

    def resolve_single_file(
        self,
        file_path: str,
        symbol_map: dict[tuple[str, int], str],
    ) -> None:
        try:
            source = Path(file_path).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            log.warning("Could not read %s", file_path)
            return
        self._resolve_file(file_path, source, symbol_map)

    def _resolve_file(
        self,
        file_path: str,
        source: str,
        symbol_map: dict[tuple[str, int], str],
    ) -> None:
        root = self._ls.repository_root_path
        rel_path = os.path.relpath(file_path, root)

        call_sites = self._call_extractor.extract(file_path, source, symbol_map)
        type_refs = self._type_ref_extractor.extract(file_path, source, symbol_map)

        if not call_sites and not type_refs:
            return

        try:
            with self._ls.open_file(rel_path):
                for caller_full_name, _callee_simple, call_line_1, call_col_0 in call_sites:
                    self._resolve_call(caller_full_name, rel_path, call_line_1 - 1, call_col_0)
                for ref in type_refs:
                    self._resolve_type_ref(ref, rel_path)
        except Exception:
            log.warning("LSP open_file failed for %s, skipping", rel_path)

    def _resolve_call(
        self, caller_full_name: str, rel_path: str, line_0: int, col_0: int,
    ) -> None:
        try:
            symbol = self._ls.request_defining_symbol(rel_path, line_0, col_0)
        except Exception:
            return
        if symbol is None:
            return
        if symbol.get("kind") not in _METHOD_KINDS:
            return
        callee_full_name = build_full_name(symbol)
        if callee_full_name and callee_full_name != caller_full_name:
            upsert_calls(self._conn, caller_full_name, callee_full_name)

    def _resolve_type_ref(self, ref: TypeRef, rel_path: str) -> None:
        try:
            symbol = self._ls.request_defining_symbol(rel_path, ref.line, ref.col)
        except Exception:
            return
        if symbol is None:
            return
        if symbol.get("kind") not in _TYPE_KINDS:
            return
        target_full_name = build_full_name(symbol)
        if target_full_name and ref.owner_full_name:
            upsert_references(self._conn, ref.owner_full_name, target_full_name, ref.ref_kind)

    @staticmethod
    def _iter_cs_files(root_path: str):
        for path in Path(root_path).rglob("*.cs"):
            if not any(p in {".git", "bin", "obj"} for p in path.parts):
                yield str(path)
