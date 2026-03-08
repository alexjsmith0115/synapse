from __future__ import annotations

import logging
import os
from pathlib import Path

from synapse.graph.connection import GraphConnection
from synapse.graph.edges import upsert_calls
from synapse.indexer.call_extractor import TreeSitterCallExtractor
from synapse.lsp.util import build_full_name

log = logging.getLogger(__name__)

_METHOD_KINDS = {6, 9, 12}  # Method, Constructor, Function


class CallIndexer:
    """
    Post-structural pass that writes CALLS edges into the graph.

    Requires the structural pass (Indexer.index_project) to have already run so
    all Method nodes exist in the graph, and the LSP to still be running.
    """

    def __init__(
        self,
        conn: GraphConnection,
        ls: object,
        extractor: TreeSitterCallExtractor | None = None,
    ) -> None:
        self._conn = conn
        self._ls = ls
        self._extractor = extractor or TreeSitterCallExtractor()

    def index_calls(
        self,
        root_path: str,
        symbol_map: dict[tuple[str, int], str],
    ) -> None:
        """
        Index CALLS edges for all .cs files under root_path.

        :param root_path: absolute path to the repository root.
        :param symbol_map: maps (abs_file_path, 0-indexed line) -> method full_name.
                           Should contain only method symbols (not classes or properties).
        """
        for file_path in self._iter_cs_files(root_path):
            try:
                source = Path(file_path).read_text(encoding="utf-8", errors="ignore")
            except OSError:
                log.warning("Could not read %s", file_path)
                continue
            self._index_file(file_path, source, symbol_map)

    def _index_file(
        self,
        file_path: str,
        source: str,
        symbol_map: dict[tuple[str, int], str],
    ) -> None:
        root = self._ls.repository_root_path
        rel_path = os.path.relpath(file_path, root)

        call_sites = self._extractor.extract(file_path, source, symbol_map)
        if not call_sites:
            return

        try:
            with self._ls.open_file(rel_path):
                for caller_full_name, _callee_simple, call_line_1, call_col_0 in call_sites:
                    self._resolve_and_write(caller_full_name, rel_path, call_line_1 - 1, call_col_0)
        except Exception:
            log.warning("LSP open_file failed for %s, skipping", rel_path)

    def _resolve_and_write(
        self,
        caller_full_name: str,
        rel_path: str,
        line_0: int,
        col_0: int,
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

    @staticmethod
    def _iter_cs_files(root_path: str):
        for path in Path(root_path).rglob("*.cs"):
            if not any(p in {".git", "bin", "obj"} for p in path.parts):
                yield str(path)
