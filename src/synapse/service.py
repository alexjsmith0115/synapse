from __future__ import annotations

import logging

from synapse.graph.connection import GraphConnection
from synapse.graph.nodes import set_summary, remove_summary
from synapse.graph.queries import (
    get_symbol, find_implementations, find_callers, find_callees,
    get_hierarchy, search_symbols, get_summary, list_summarized,
    list_projects, get_index_status, execute_readonly_query,
)
from synapse.indexer.indexer import Indexer
from synapse.lsp.csharp import CSharpLSPAdapter
from synapse.lsp.interface import LSPAdapter
from synapse.watcher.watcher import FileWatcher

log = logging.getLogger(__name__)


class SynapseService:
    def __init__(self, conn: GraphConnection) -> None:
        self._conn = conn
        self._watchers: dict[str, FileWatcher] = {}

    # --- Indexing ---

    def index_project(self, path: str, language: str = "csharp") -> None:
        lsp = CSharpLSPAdapter.create(path)
        indexer = Indexer(self._conn, lsp)
        indexer.index_project(path, language)

    def delete_project(self, path: str) -> None:
        self._conn.execute(
            "MATCH (r:Repository {path: $path})-[:CONTAINS*]->(n) DETACH DELETE n",
            {"path": path},
        )
        self._conn.execute("MATCH (r:Repository {path: $path}) DETACH DELETE r", {"path": path})

    def watch_project(self, path: str, lsp_adapter: LSPAdapter | None = None) -> None:
        if path in self._watchers:
            return
        lsp = lsp_adapter or CSharpLSPAdapter.create(path)
        indexer = Indexer(self._conn, lsp)
        indexer.index_project(path, "csharp", keep_lsp_running=True)

        def on_change(file_path: str) -> None:
            log.info("Re-indexing changed file: %s", file_path)
            indexer.reindex_file(file_path, path)

        def on_delete(file_path: str) -> None:
            log.info("Removing deleted file: %s", file_path)
            indexer.delete_file(file_path)

        watcher = FileWatcher(root_path=path, on_change=on_change, on_delete=on_delete)
        watcher.start()
        self._watchers[path] = watcher

    def unwatch_project(self, path: str) -> None:
        watcher = self._watchers.pop(path, None)
        if watcher:
            watcher.stop()

    # --- Queries ---

    def get_symbol(self, full_name: str) -> dict | None:
        return get_symbol(self._conn, full_name)

    def find_implementations(self, interface_name: str) -> list[dict]:
        return find_implementations(self._conn, interface_name)

    def find_callers(self, method_full_name: str) -> list[dict]:
        return find_callers(self._conn, method_full_name)

    def find_callees(self, method_full_name: str) -> list[dict]:
        return find_callees(self._conn, method_full_name)

    def get_hierarchy(self, class_name: str) -> dict:
        return get_hierarchy(self._conn, class_name)

    def search_symbols(self, query: str, kind: str | None = None) -> list[dict]:
        return search_symbols(self._conn, query, kind)

    def list_projects(self) -> list[dict]:
        return list_projects(self._conn)

    def get_index_status(self, path: str) -> dict | None:
        return get_index_status(self._conn, path)

    def execute_query(self, cypher: str) -> list:
        return execute_readonly_query(self._conn, cypher)

    # --- Summaries ---

    def set_summary(self, full_name: str, content: str) -> None:
        set_summary(self._conn, full_name, content)

    def get_summary(self, full_name: str) -> str | None:
        return get_summary(self._conn, full_name)

    def list_summarized(self, project_path: str | None = None) -> list[dict]:
        return list_summarized(self._conn, project_path)

    def remove_summary(self, full_name: str) -> None:
        remove_summary(self._conn, full_name)
