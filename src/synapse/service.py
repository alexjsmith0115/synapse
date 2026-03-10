from __future__ import annotations

import logging

from synapse.graph.connection import GraphConnection
from synapse.graph.nodes import set_summary, remove_summary
from synapse.graph.queries import (
    get_symbol, find_implementations, find_callers, find_callees,
    get_hierarchy, search_symbols, get_summary, list_summarized,
    list_projects, get_index_status, execute_readonly_query,
    get_method_symbol_map, get_symbol_source_info,
    get_containing_type, get_members_overview, get_implemented_interfaces,
    find_type_references as query_find_type_references,
    find_dependencies as query_find_dependencies,
)
from synapse.indexer.indexer import Indexer
from synapse.lsp.csharp import CSharpLSPAdapter
from synapse.lsp.interface import LSPAdapter
from synapse.watcher.watcher import FileWatcher

log = logging.getLogger(__name__)


def _p(node) -> dict:
    """Extract properties from a FalkorDB Node (including labels) or pass through a plain dict."""
    if hasattr(node, "properties"):
        result = dict(node.properties)
        if node.labels:
            result["_labels"] = list(node.labels)
        return result
    return node


class SynapseService:
    def __init__(self, conn: GraphConnection) -> None:
        self._conn = conn
        self._watchers: dict[str, FileWatcher] = {}

    # --- Indexing ---

    def index_project(self, path: str, language: str = "csharp") -> None:
        lsp = CSharpLSPAdapter.create(path)
        indexer = Indexer(self._conn, lsp)
        indexer.index_project(path, language)

    def index_calls(self, path: str) -> None:
        """Run the relationship resolution pass on an already-structurally-indexed project."""
        from synapse.indexer.symbol_resolver import SymbolResolver
        lsp = CSharpLSPAdapter.create(path)
        symbol_map = get_method_symbol_map(self._conn)
        SymbolResolver(self._conn, lsp.language_server).resolve(path, symbol_map)
        lsp.shutdown()

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
        result = get_symbol(self._conn, full_name)
        return _p(result) if result is not None else None

    def find_implementations(self, interface_name: str) -> list[dict]:
        return [_p(item) for item in find_implementations(self._conn, interface_name)]

    def find_callers(self, method_full_name: str, include_interface_dispatch: bool = True) -> list[dict]:
        return [_p(item) for item in find_callers(self._conn, method_full_name, include_interface_dispatch)]

    def find_callees(self, method_full_name: str) -> list[dict]:
        return [_p(item) for item in find_callees(self._conn, method_full_name)]

    def get_hierarchy(self, class_name: str) -> dict:
        raw = get_hierarchy(self._conn, class_name)
        return {"parents": [_p(n) for n in raw["parents"]], "children": [_p(n) for n in raw["children"]]}

    def search_symbols(self, query: str, kind: str | None = None) -> list[dict]:
        return [_p(item) for item in search_symbols(self._conn, query, kind)]

    def list_projects(self) -> list[dict]:
        return [_p(item) for item in list_projects(self._conn)]

    def get_index_status(self, path: str) -> dict | None:
        return get_index_status(self._conn, path)

    def execute_query(self, cypher: str) -> list[dict]:
        raw = execute_readonly_query(self._conn, cypher)
        return [{"row": [_p(cell) if hasattr(cell, "properties") else cell for cell in row]} for row in raw]

    def find_type_references(self, full_name: str) -> list[dict]:
        return [{"symbol": _p(r["symbol"]), "kind": r["kind"]} for r in query_find_type_references(self._conn, full_name)]

    def find_dependencies(self, full_name: str) -> list[dict]:
        return [{"type": _p(r["type"]), "kind": r["kind"]} for r in query_find_dependencies(self._conn, full_name)]

    # --- Summaries ---

    def set_summary(self, full_name: str, content: str) -> None:
        set_summary(self._conn, full_name, content)

    def get_summary(self, full_name: str) -> str | None:
        return get_summary(self._conn, full_name)

    def list_summarized(self, project_path: str | None = None) -> list[dict]:
        return [_p(item) for item in list_summarized(self._conn, project_path)]

    def remove_summary(self, full_name: str) -> None:
        remove_summary(self._conn, full_name)

    # --- Source retrieval ---

    def get_symbol_source(self, full_name: str, include_class_signature: bool = False) -> str | None:
        info = get_symbol_source_info(self._conn, full_name)
        if info is None:
            return None
        file_path = info["file_path"]
        line = info["line"]
        end_line = info["end_line"]
        if line is None or not end_line:
            return f"Symbol '{full_name}' was indexed without line ranges. Re-index the project to enable source retrieval."
        try:
            with open(file_path, encoding="utf-8", errors="ignore") as f:
                all_lines = f.readlines()
        except OSError:
            return f"Source file not found: {file_path}"
        source_lines = all_lines[line:end_line + 1]
        result = f"// {file_path}:{line + 1}\n{''.join(source_lines)}"
        if include_class_signature:
            parent = self._get_parent_signature(full_name)
            if parent:
                result = parent + "\n\n" + result
        return result

    def get_context_for(self, full_name: str) -> str | None:
        symbol = get_symbol(self._conn, full_name)
        if symbol is None:
            return None

        sections: list[str] = []

        source = self.get_symbol_source(full_name)
        sections.append(f"## Target: {full_name}\n\n{source or 'Source not available (re-index may be required)'}")

        parent = get_containing_type(self._conn, full_name)
        if parent:
            parent_fn = _p(parent)["full_name"]
            members = get_members_overview(self._conn, parent_fn)
            member_lines = []
            for m in members:
                mp = _p(m)
                sig = mp.get("signature") or mp.get("type_name") or ""
                member_lines.append(f"  {mp.get('name', '?')}: {sig}")
            sections.append(
                f"## Containing Type: {parent_fn}\n\n"
                + "\n".join(member_lines)
            )

            interfaces = get_implemented_interfaces(self._conn, parent_fn)
            if interfaces:
                iface_lines = []
                for iface in interfaces:
                    iface_fn = _p(iface)["full_name"]
                    iface_members = get_members_overview(self._conn, iface_fn)
                    iface_sigs = [f"  {_p(m).get('name', '?')}: {_p(m).get('signature', '')}" for m in iface_members]
                    iface_lines.append(f"### {iface_fn}\n" + "\n".join(iface_sigs))
                sections.append("## Implemented Interfaces\n\n" + "\n\n".join(iface_lines))

        callees = self.find_callees(full_name)
        if callees:
            callee_lines = [f"- `{c['full_name']}` — {c.get('signature', '')}" for c in callees]
            sections.append("## Called Methods\n\n" + "\n".join(callee_lines))

        deps = self.find_dependencies(full_name)
        if deps:
            dep_lines = []
            seen_types: set[str] = set()
            for dep in deps:
                type_fn = dep["type"]["full_name"]
                if type_fn in seen_types:
                    continue
                seen_types.add(type_fn)
                kind = dep["kind"]
                type_members = get_members_overview(self._conn, type_fn)
                member_sigs = [f"  {_p(m).get('name', '?')}: {_p(m).get('signature', '') or _p(m).get('type_name', '')}" for m in type_members]
                dep_lines.append(f"### {type_fn} ({kind})\n" + "\n".join(member_sigs))
            sections.append("## Parameter & Return Types\n\n" + "\n\n".join(dep_lines))

        return "\n\n---\n\n".join(sections)

    def _get_parent_signature(self, full_name: str) -> str | None:
        """Get the declaration line of the containing class/interface."""
        rows = self._conn.query(
            "MATCH (parent)-[:CONTAINS]->(n {full_name: $full_name}) "
            "WHERE parent:Class OR parent:Interface "
            "RETURN parent.full_name, parent.line, parent.end_line",
            {"full_name": full_name},
        )
        if not rows:
            return None
        parent_full_name = rows[0][0]
        parent_line = rows[0][1]
        if parent_line is None:
            return f"// Containing type: {parent_full_name}"
        parent_info = get_symbol_source_info(self._conn, parent_full_name)
        if not parent_info or not parent_info["file_path"]:
            return f"// Containing type: {parent_full_name}"
        try:
            with open(parent_info["file_path"], encoding="utf-8", errors="ignore") as f:
                all_lines = f.readlines()
            return f"// {parent_info['file_path']}:{parent_line + 1}\n{all_lines[parent_line].rstrip()}"
        except (OSError, IndexError):
            return f"// Containing type: {parent_full_name}"
