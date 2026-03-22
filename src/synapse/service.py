from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable
from pathlib import Path

from synapse.graph.connection import GraphConnection
from synapse.graph.nodes import set_summary, remove_summary
from synapse.graph.lookups import (
    get_symbol, find_implementations, find_callers, find_callees,
    get_hierarchy, search_symbols, get_summary, list_summarized,
    list_projects, get_index_status, execute_readonly_query,
    get_method_symbol_map, get_symbol_source_info, check_staleness,
    get_containing_type, get_members_overview, get_implemented_interfaces,
    get_constructor, resolve_full_name, resolve_full_name_with_labels,
    find_type_references as query_find_type_references,
    find_dependencies as query_find_dependencies,
    find_callers_with_sites,
    find_relevant_deps,
    find_all_deps,
    find_test_coverage,
    get_called_members,
    _TEST_PATH_PATTERN,
)
from synapse.graph.traversal import trace_call_chain, find_entry_points, get_call_depth
from synapse.graph.analysis import analyze_change_impact, find_interface_contract, find_type_impact, audit_architecture
from synapse.indexer.indexer import Indexer
from synapse.indexer.method_implements_indexer import MethodImplementsIndexer
from synapse.indexer.sync import sync_project as _sync_project, SyncResult
from synapse.indexer.overrides_indexer import OverridesIndexer
from synapse.indexer.symbol_resolver import SymbolResolver
from synapse.lsp.interface import LSPAdapter
from synapse.plugin import LanguagePlugin, LanguageRegistry, default_registry
from synapse.watcher.watcher import FileWatcher

log = logging.getLogger(__name__)


def _p(node) -> dict:
    """Extract properties from a neo4j graph Node (including labels) or pass through a plain dict."""
    if hasattr(node, "element_id"):
        result = dict(node)
        if node.labels:
            result["_labels"] = list(node.labels)
        return result
    return node


def _slim(node, *fields: str) -> dict:
    """Extract only the specified fields from a neo4j Node or plain dict."""
    if hasattr(node, "element_id"):
        return {f: node.get(f) for f in fields if node.get(f) is not None}
    if isinstance(node, dict):
        return {f: node[f] for f in fields if f in node}
    return {}


def _apply_limit(items: list, limit: int) -> list | dict:
    """Return items directly if within limit, or a truncated wrapper if over."""
    if len(items) <= limit:
        return items
    return {"results": items[:limit], "_total": len(items), "_truncated": True}


def _member_line(m) -> str:
    mp = _p(m)
    sig = mp.get("signature") or mp.get("type_name") or ""
    return f"  {mp.get('name', '?')}: {sig}"


class SynapseService:
    def __init__(
        self,
        conn: GraphConnection,
        registry: LanguageRegistry | None = None,
    ) -> None:
        self._conn = conn
        self._registry = registry or default_registry()
        self._watchers: dict[str, FileWatcher] = {}

    def _resolve(self, name: str, preference: str | None = None) -> str:
        """Resolve a possibly-short name to a fully qualified name.

        preference: 'concrete' prefers :Class, 'interface' prefers :Interface.
        For type nodes, filters directly by label. For method nodes, checks the
        containing type's label (via CONTAINS edge) to resolve interface-vs-concrete pairs.
        Raises ValueError if the name is ambiguous after applying preference.
        """
        result = resolve_full_name(self._conn, name)
        if not isinstance(result, list):
            return result

        if preference in ("concrete", "interface"):
            labeled = resolve_full_name_with_labels(self._conn, name)
            if isinstance(labeled, list):
                target_label = "Class" if preference == "concrete" else "Interface"
                # Try direct label match (works for type-level ambiguity)
                filtered = [fn for fn, labels in labeled if target_label in labels]
                if len(filtered) == 1:
                    return filtered[0]

                # For method-level ambiguity, check containing type's label
                all_methods = all("Method" in labels for _, labels in labeled)
                if all_methods and len(labeled) > 1:
                    filtered = self._filter_methods_by_parent_label(
                        [fn for fn, _ in labeled], target_label,
                    )
                    if len(filtered) == 1:
                        return filtered[0]

        options = ", ".join(result[:10])
        raise ValueError(
            f"Ambiguous name '{name}' — matches: {options}. "
            "Use the fully qualified name."
        )

    def _filter_methods_by_parent_label(
        self, method_full_names: list[str], target_label: str,
    ) -> list[str]:
        """Return methods whose containing type has the given label."""
        rows = self._conn.query(
            "MATCH (parent)-[:CONTAINS]->(m:Method) "
            "WHERE m.full_name IN $names "
            "RETURN m.full_name, labels(parent)",
            {"names": method_full_names},
        )
        return [r[0] for r in rows if target_label in r[1]]

    def _staleness_warning(self, full_name: str) -> str | None:
        """Return a warning string if the symbol's file is stale, else None."""
        source_info = get_symbol_source_info(self._conn, full_name)
        if not source_info or not source_info.get("file_path"):
            return None
        staleness = check_staleness(self._conn, source_info["file_path"])
        if staleness and staleness["is_stale"]:
            return (
                f"Warning: {staleness['file_path']} was modified after last indexing. "
                "Results may be outdated. Run watch_project or re-index to refresh."
            )
        return None

    # --- Indexing ---

    def index_project(
        self,
        path: str,
        language: str = "csharp",
        on_progress: Callable[[str], None] | None = None,
    ) -> None:
        plugins = self._registry.detect(path)
        if not plugins:
            raise ValueError(f"No language plugin found for project at {path!r}")
        for plugin in plugins:
            if on_progress:
                on_progress(f"Starting language server for {plugin.name}...")
            lsp = plugin.create_lsp_adapter(path)
            indexer = Indexer(self._conn, lsp, plugin=plugin)
            indexer.index_project(path, plugin.name, on_progress=on_progress)

    def index_calls(self, path: str) -> None:
        """Run the relationship resolution pass on an already-structurally-indexed project."""
        plugins = self._registry.detect(path)
        if not plugins:
            raise ValueError(f"No language plugin found for project at {path!r}")
        symbol_map = get_method_symbol_map(self._conn)
        for plugin in plugins:
            lsp = plugin.create_lsp_adapter(path)
            call_ext = plugin.create_call_extractor()
            type_ref_ext = plugin.create_type_ref_extractor()

            module_full_names: set[str] = set()
            if plugin.name in ("python", "typescript"):
                module_map: dict[str, str] = {}
                rows = self._conn.query(
                    "MATCH (n:Class {kind: 'module'}) RETURN n.full_name, n.file_path"
                )
                for full_name, file_path in rows:
                    if full_name and file_path:
                        module_full_names.add(full_name)
                        module_map[file_path] = full_name
                if call_ext is not None and hasattr(call_ext, "_module_name_resolver"):
                    call_ext._module_name_resolver = lambda fp, _m=module_map: _m.get(fp)

            resolver = SymbolResolver(
                self._conn, lsp.language_server,
                call_extractor=call_ext,
                type_ref_extractor=type_ref_ext,
                file_extensions=plugin.file_extensions,
                module_full_names=module_full_names,
            )
            resolver.resolve(path, symbol_map)

            if plugin.name in ("python", "typescript", "java") and hasattr(resolver, "_unresolved_sites"):
                for site_msg in resolver._unresolved_sites:
                    log.debug(site_msg)

            if plugin.name in ("python", "typescript", "java") and call_ext is not None:
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

            if plugin.name in ("python", "typescript", "java"):
                OverridesIndexer(self._conn).index()

            lsp.shutdown()

    def sync_project(self, path: str) -> SyncResult:
        """Sync the graph with the current filesystem state.

        Detects stale, new, and deleted files and re-indexes only what changed.
        Requires the project to have been fully indexed at least once.
        """
        plugins = self._registry.detect(path)
        if not plugins:
            raise ValueError(f"No language plugin found for project at {path!r}")

        total = SyncResult(updated=0, deleted=0, unchanged=0)
        for plugin in plugins:
            lsp = plugin.create_lsp_adapter(path)
            try:
                indexer = Indexer(self._conn, lsp, plugin=plugin)
                workspace_files = lsp.get_workspace_files(path)
                disk_files = {}
                for fp in workspace_files:
                    try:
                        disk_files[fp] = os.path.getmtime(fp)
                    except OSError:
                        pass
                result = _sync_project(
                    conn=self._conn,
                    indexer=indexer,
                    root_path=path,
                    disk_files=disk_files,
                )
                total.updated += result.updated
                total.deleted += result.deleted
                total.unchanged += result.unchanged
            finally:
                # reindex_file does not manage LSP lifecycle (unlike index_project), so shut down explicitly
                lsp.shutdown()

        return total

    def index_method_implements(self) -> None:
        """Write method-level IMPLEMENTS edges for all indexed class-level IMPLEMENTS relationships.

        Can be run standalone after a structural index pass to populate interface dispatch edges
        without re-indexing the full project.
        """
        MethodImplementsIndexer(self._conn).index()

    def delete_project(self, path: str) -> None:
        self._conn.execute(
            "MATCH (r:Repository {path: $path})-[:CONTAINS*]->(n) DETACH DELETE n",
            {"path": path},
        )
        self._conn.execute("MATCH (r:Repository {path: $path}) DETACH DELETE r", {"path": path})

    def watch_project(self, path: str, lsp_adapter: LSPAdapter | None = None) -> None:
        if path in self._watchers:
            return

        if lsp_adapter is not None:
            plugins_and_lsps: list[tuple[LanguagePlugin | None, LSPAdapter]] = [
                (None, lsp_adapter),
            ]
        else:
            plugins = self._registry.detect(path)
            if not plugins:
                raise ValueError(f"No language plugin found for project at {path!r}")
            plugins_and_lsps = [
                (p, p.create_lsp_adapter(path)) for p in plugins
            ]

        # Build extension→indexer map and index each language
        ext_to_indexer: dict[str, Indexer] = {}
        all_extensions: set[str] = set()
        for plugin, lsp in plugins_and_lsps:
            indexer = Indexer(self._conn, lsp, plugin=plugin)
            lang_name = plugin.name if plugin else "csharp"
            indexer.index_project(path, lang_name, keep_lsp_running=True)
            exts = plugin.file_extensions if plugin else frozenset({".cs"})
            for ext in exts:
                ext_to_indexer[ext] = indexer
            all_extensions |= exts

        def on_change(file_path: str) -> None:
            ext = Path(file_path).suffix.lower()
            indexer = ext_to_indexer.get(ext)
            if indexer:
                log.info("Re-indexing changed file: %s", file_path)
                indexer.reindex_file(file_path, path)

        def on_delete(file_path: str) -> None:
            ext = Path(file_path).suffix.lower()
            indexer = ext_to_indexer.get(ext)
            if indexer:
                log.info("Removing deleted file: %s", file_path)
                indexer.delete_file(file_path)

        watcher = FileWatcher(
            root_path=path, on_change=on_change, on_delete=on_delete,
            watched_extensions=frozenset(all_extensions),
        )
        watcher.start()
        self._watchers[path] = watcher

    def unwatch_project(self, path: str) -> None:
        watcher = self._watchers.pop(path, None)
        if watcher:
            watcher.stop()

    # --- Queries ---

    def get_symbol(self, full_name: str) -> dict | None:
        full_name = self._resolve(full_name)
        result = get_symbol(self._conn, full_name)
        return _p(result) if result is not None else None

    def find_implementations(self, interface_name: str, limit: int = 50) -> list[dict] | dict:
        interface_name = self._resolve(interface_name, preference="interface")
        result = [_slim(item, "full_name", "file_path", "line") for item in find_implementations(self._conn, interface_name)]
        return _apply_limit(result, limit)

    def find_callers(self, method_full_name: str, include_interface_dispatch: bool = True, exclude_test_callers: bool = True, limit: int = 50) -> list[dict] | dict:
        method_full_name = self._resolve(method_full_name, preference="concrete")
        result = [_slim(item, "full_name", "file_path", "line") for item in find_callers(self._conn, method_full_name, include_interface_dispatch, exclude_test_callers)]
        return _apply_limit(result, limit)

    def find_callees(self, method_full_name: str, include_interface_dispatch: bool = True, limit: int = 50) -> list[dict] | dict:
        method_full_name = self._resolve(method_full_name, preference="concrete")
        result = [_slim(item, "full_name", "file_path", "line") for item in find_callees(self._conn, method_full_name, include_interface_dispatch)]
        return _apply_limit(result, limit)

    def get_hierarchy(self, class_name: str) -> dict:
        class_name = self._resolve(class_name)
        raw = get_hierarchy(self._conn, class_name)
        return {
            "parents": [_slim(n, "full_name", "file_path") for n in raw["parents"]],
            "children": [_slim(n, "full_name", "file_path") for n in raw["children"]],
            "implements": [_slim(n, "full_name", "file_path") for n in raw["implements"]],
        }

    def search_symbols(
        self,
        query: str,
        kind: str | None = None,
        namespace: str | None = None,
        file_path: str | None = None,
        language: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        result = [_slim(item, "full_name", "name", "kind", "file_path", "line") for item in search_symbols(self._conn, query, kind, namespace, file_path, language)]
        return _apply_limit(result, limit)

    def list_projects(self) -> list[dict]:
        return [_p(item) for item in list_projects(self._conn)]

    def get_index_status(self, path: str) -> dict | None:
        return get_index_status(self._conn, path)

    def execute_query(self, cypher: str) -> list[dict]:
        raw = execute_readonly_query(self._conn, cypher)
        return [{"row": [_p(cell) if hasattr(cell, "element_id") else cell for cell in row]} for row in raw]

    _VALID_REF_KINDS = frozenset({"parameter", "return_type", "property_type"})

    def find_type_references(self, full_name: str, kind: str | None = None, limit: int = 50) -> list[dict] | dict:
        if kind is not None and kind not in self._VALID_REF_KINDS:
            raise ValueError(
                f"Unknown reference kind: {kind!r}. "
                f"Valid values: {sorted(self._VALID_REF_KINDS)}"
            )
        full_name = self._resolve(full_name)
        result = [{"symbol": _slim(r["symbol"], "full_name", "file_path"), "kind": r["kind"]} for r in query_find_type_references(self._conn, full_name, kind=kind)]
        return _apply_limit(result, limit)

    _USAGES_SUPPORTED_LABELS = {"Method", "Property", "Field", "Class", "Interface"}

    def find_usages(self, full_name: str, exclude_test_callers: bool = True, limit: int = 20) -> dict:
        full_name = self._resolve(full_name)
        symbol = get_symbol(self._conn, full_name)
        if symbol is None:
            return {"error": f"Symbol not found: {full_name}"}

        props = _p(symbol)
        labels = set(props.get("_labels", []))

        supported = labels & self._USAGES_SUPPORTED_LABELS
        if not supported:
            label = next(iter(labels), "unknown")
            return {"error": f"find_usages does not support {label} symbols"}

        # Method/Property/Field — return callers
        if labels & {"Method", "Property", "Field"}:
            callers = self.find_callers(full_name, exclude_test_callers=exclude_test_callers, limit=limit)
            kind = "Method" if "Method" in labels else ("Property" if "Property" in labels else "Field")
            return {"symbol": full_name, "kind": kind, "callers": callers}

        # Class or Interface — return tiered summary
        kind = "Interface" if "Interface" in labels else "Class"
        test_re = re.compile(_TEST_PATH_PATTERN) if exclude_test_callers else None

        # Type references: get count + limited items
        raw_refs = [
            {"full_name": _slim(r["symbol"], "full_name")["full_name"],
             "file_path": _slim(r["symbol"], "file_path").get("file_path", ""),
             "kind": r["kind"]}
            for r in query_find_type_references(self._conn, full_name)
        ]
        if test_re:
            raw_refs = [r for r in raw_refs if not test_re.match(r.get("file_path", ""))]

        ref_total = len(raw_refs)
        ref_items = raw_refs[:limit]

        # Collect affected files
        affected_files: set[str] = set()
        for r in raw_refs:
            fp = r.get("file_path")
            if fp:
                affected_files.add(fp)

        # Method callers — summarize as counts + top callers per method
        members = get_members_overview(self._conn, full_name)
        all_members = [_p(m) for m in members]
        methods = [m for m in all_members if "Method" in set(m.get("_labels", []))]
        method_summary: dict[str, dict] = {}
        total_method_callers = 0
        for method in methods:
            method_fn = method["full_name"]
            method_short = method.get("name", method_fn.rsplit(".", 1)[-1])
            callers = self.find_callers(method_fn, exclude_test_callers=exclude_test_callers, limit=1000)
            # find_callers may return list or truncated dict
            if isinstance(callers, dict):
                caller_list = callers["results"]
                count = callers["_total"]
            else:
                caller_list = callers
                count = len(callers)
            if count > 0:
                top_callers = [c["full_name"] for c in caller_list[:5]]
                method_summary[method_short] = {"count": count, "top_callers": top_callers}
                total_method_callers += count
                for c in caller_list:
                    fp = c.get("file_path")
                    if fp:
                        affected_files.add(fp)

        return {
            "symbol": full_name,
            "kind": kind,
            "type_references": {"total": ref_total, "items": ref_items},
            "method_callers": {"total": total_method_callers, "by_method": method_summary},
            "affected_files": len(affected_files),
        }

    def find_dependencies(self, full_name: str, depth: int = 1, limit: int = 50) -> list[dict] | dict:
        full_name = self._resolve(full_name)
        result = [
            {"type": _slim(r["type"], "full_name", "file_path"), "depth": r["depth"]}
            for r in query_find_dependencies(self._conn, full_name, depth)
        ]
        return _apply_limit(result, limit)

    # --- Summaries ---

    def set_summary(self, full_name: str, content: str) -> None:
        set_summary(self._conn, full_name, content)

    def get_summary(self, full_name: str) -> str | None:
        full_name = self._resolve(full_name)
        return get_summary(self._conn, full_name)

    def list_summarized(self, project_path: str | None = None) -> list[dict]:
        return [_p(item) for item in list_summarized(self._conn, project_path)]

    def remove_summary(self, full_name: str) -> None:
        remove_summary(self._conn, full_name)

    # --- Source retrieval ---

    def get_symbol_source(self, full_name: str, include_class_signature: bool = False) -> str | None:
        full_name = self._resolve(full_name)
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

    def get_context_for(self, full_name: str, scope: str | None = None, max_lines: int = 200) -> str | None:
        full_name = self._resolve(full_name, preference="concrete")
        symbol = get_symbol(self._conn, full_name)
        if symbol is None:
            return None

        props = _p(symbol)
        labels = set(props.get("_labels", []))

        if scope == "structure":
            if not labels & {"Class", "Interface"}:
                return f"scope='structure' requires a type (class or interface), but '{full_name}' is a {props.get('kind', 'unknown')}."
            return self._context_structure(full_name)
        elif scope == "method":
            if not labels & {"Method", "Property"}:
                return f"scope='method' requires a method or property, but '{full_name}' is a {props.get('kind', 'unknown')}."
            return self._context_method(full_name, max_lines=max_lines)
        elif scope == "edit":
            if labels & {"Method"}:
                return self._context_edit_method(full_name, max_lines=max_lines)
            elif labels & {"Class", "Interface"}:
                return self._context_edit_type(full_name, is_interface=bool(labels & {"Interface"}), max_lines=max_lines)
            else:
                kind = props.get("kind", "unknown")
                return f"scope='edit' requires a method, class, or interface, but '{full_name}' is a {kind}."
        elif scope is not None:
            return f"Unknown scope '{scope}'. Valid values: 'structure', 'method', 'edit'."

        return self._context_full(full_name, labels=labels, max_lines=max_lines)

    # -- Shared section builders used by _context_full / _context_structure / _context_method --

    def _target_section(self, full_name: str, max_lines: int = -1, labels: set[str] | None = None) -> str:
        source = self.get_symbol_source(full_name)
        if source is not None and max_lines >= 0:
            line_count = source.count("\n") + 1
            if line_count > max_lines:
                note = f"[Source exceeds {max_lines} lines — showing structure. Use scope='method' on individual methods for full source.]"
                if labels and labels & {"Class", "Interface"}:
                    members = get_members_overview(self._conn, full_name)
                    member_lines = "\n".join(_member_line(m) for m in members)
                    return f"## Target: {full_name}\n\n{note}\n\n{member_lines}"
                else:
                    sig_line = source.split("\n", 1)[0]
                    return f"## Target: {full_name}\n\n{note}\n\n{sig_line}"
        return f"## Target: {full_name}\n\n{source or 'Source not available (re-index may be required)'}"

    def _interfaces_section(self, type_full_name: str) -> str | None:
        interfaces = get_implemented_interfaces(self._conn, type_full_name)
        if not interfaces:
            return None
        iface_blocks = []
        for iface in interfaces:
            iface_fn = _p(iface)["full_name"]
            iface_members = get_members_overview(self._conn, iface_fn)
            lines = [_member_line(m) for m in iface_members]
            iface_blocks.append(f"### {iface_fn}\n" + "\n".join(lines))
        return "## Implemented Interfaces\n\n" + "\n\n".join(iface_blocks)

    _CALLER_LIMIT = 15

    def _callers_section(self, full_name: str, limit: int = _CALLER_LIMIT) -> str | None:
        results = find_callers_with_sites(self._conn, full_name)
        if not results:
            return None
        lines = []
        for entry in results[:limit]:
            caller_props = _p(entry["caller"])
            sites = entry["call_sites"]
            line_str = self._format_call_sites(sites)
            fp = caller_props.get("file_path", "")
            fn = caller_props["full_name"]
            if line_str:
                lines.append(f"- `{fn}` — {fp} ({line_str})")
            else:
                lines.append(f"- `{fn}` — {fp}")
        if len(results) > limit:
            lines.append(f"... and {len(results) - limit} more callers")
        return "## Direct Callers\n\n" + "\n".join(lines)

    @staticmethod
    def _format_call_sites(sites: list) -> str:
        if not sites:
            return ""
        line_numbers = sorted({s[0] for s in sites if s and s[0] is not None})
        if not line_numbers:
            return ""
        if len(line_numbers) == 1:
            return f"line {line_numbers[0]}"
        return f"lines {', '.join(str(n) for n in line_numbers)}"

    def _test_coverage_section(self, full_name: str) -> str | None:
        tests = find_test_coverage(self._conn, full_name)
        if not tests:
            return None
        lines = [f"- `{t['full_name']}` — {t['file_path']}" for t in tests]
        return "## Test Coverage\n\n" + "\n".join(lines)

    def _relevant_deps_section(self, class_full_name: str, method_full_name: str) -> str | None:
        deps = find_relevant_deps(self._conn, class_full_name, method_full_name)
        if not deps:
            return None
        dep_lines = []
        for dep_node in deps:
            dep_fn = _p(dep_node)["full_name"]
            called = get_called_members(self._conn, method_full_name, dep_fn)
            if called:
                dep_lines.append(f"### {dep_fn}\n" + "\n".join(_member_line(m) for m in called))
            else:
                members = get_members_overview(self._conn, dep_fn)
                dep_lines.append(
                    f"### {dep_fn}\n*(all members shown — no direct method calls detected)*\n"
                    + "\n".join(_member_line(m) for m in members)
                )
        return "## Constructor Dependencies (used by this method)\n\n" + "\n\n".join(dep_lines)

    def _callees_section(self, full_name: str) -> str | None:
        callees = self.find_callees(full_name)
        if not callees:
            return None
        lines = [f"- `{c['full_name']}` — {c.get('signature', '')}" for c in callees]
        return "## Called Methods\n\n" + "\n".join(lines)

    def _dependencies_section(self, full_name: str) -> str | None:
        deps = self.find_dependencies(full_name)
        if not deps:
            return None
        dep_lines = []
        seen_types: set[str] = set()
        for dep in deps:
            type_fn = dep["type"]["full_name"]
            if type_fn in seen_types:
                continue
            seen_types.add(type_fn)
            type_members = get_members_overview(self._conn, type_fn)
            dep_lines.append(f"### {type_fn}\n" + "\n".join(_member_line(m) for m in type_members))
        return "## Parameter & Return Types\n\n" + "\n\n".join(dep_lines)

    def _summaries_section(self, full_names: list[str]) -> str | None:
        entries = []
        for fn in full_names:
            s = get_summary(self._conn, fn)
            if s:
                entries.append(f"**{fn}:** {s}")
        if not entries:
            return None
        return "## Summaries\n\n" + "\n\n".join(entries)

    def _context_full(self, full_name: str, labels: set[str] | None = None, max_lines: int = -1) -> str:
        sections: list[str] = []

        sections.append(self._target_section(full_name, max_lines=max_lines, labels=labels or set()))

        parent = get_containing_type(self._conn, full_name)
        if parent:
            parent_fn = _p(parent)["full_name"]
            members = get_members_overview(self._conn, parent_fn)
            sections.append(
                f"## Containing Type: {parent_fn}\n\n"
                + "\n".join(_member_line(m) for m in members)
            )

            iface_section = self._interfaces_section(parent_fn)
            if iface_section:
                sections.append(iface_section)

        callees_section = self._callees_section(full_name)
        if callees_section:
            sections.append(callees_section)

        deps_section = self._dependencies_section(full_name)
        if deps_section:
            sections.append(deps_section)

        # Summaries: symbol + parent + parent's interfaces, or symbol + own interfaces
        summary_fns = [full_name]
        if parent:
            parent_fn = _p(parent)["full_name"]
            summary_fns.append(parent_fn)
            for iface in get_implemented_interfaces(self._conn, parent_fn):
                summary_fns.append(_p(iface)["full_name"])
        else:
            for iface in get_implemented_interfaces(self._conn, full_name):
                summary_fns.append(_p(iface)["full_name"])
        summaries_section = self._summaries_section(summary_fns)
        if summaries_section:
            sections.append(summaries_section)

        return "\n\n---\n\n".join(sections)

    def _context_structure(self, full_name: str) -> str:
        sections: list[str] = []

        # Constructor source (if exists)
        ctor = get_constructor(self._conn, full_name)
        if ctor is not None:
            ctor_fn = _p(ctor)["full_name"]
            ctor_source = self.get_symbol_source(ctor_fn)
            if ctor_source:
                sections.append(f"## Constructor\n\n{ctor_source}")

        # Member signatures
        members = get_members_overview(self._conn, full_name)
        if members:
            sections.append(
                f"## Members: {full_name}\n\n"
                + "\n".join(_member_line(m) for m in members)
            )

        # Implemented interfaces
        iface_section = self._interfaces_section(full_name)
        if iface_section:
            sections.append(iface_section)

        # Summaries (type + interfaces only)
        interfaces = get_implemented_interfaces(self._conn, full_name)
        summary_fns = [full_name] + [_p(iface)["full_name"] for iface in interfaces]
        summaries_section = self._summaries_section(summary_fns)
        if summaries_section:
            sections.append(summaries_section)

        if not sections:
            return f"No structure information available for `{full_name}`."
        return "\n\n---\n\n".join(sections)

    def _context_method(self, full_name: str, max_lines: int = -1) -> str:
        sections: list[str] = []

        sections.append(self._target_section(full_name, max_lines=max_lines, labels={"Method"}))

        # Interface contract
        contract = find_interface_contract(self._conn, full_name)
        if contract["interface"] is not None:
            contract_lines = [
                f"Interface: `{contract['interface']}`",
                f"Contract method: `{contract['contract_method']}`",
            ]
            if contract["sibling_implementations"]:
                siblings = ", ".join(
                    f"{s['class_name']} ({s['file_path']})"
                    for s in contract["sibling_implementations"]
                )
                contract_lines.append(f"Other implementations: {siblings}")
            sections.append("## Interface Contract\n\n" + "\n".join(contract_lines))

        callees_section = self._callees_section(full_name)
        if callees_section:
            sections.append(callees_section)

        deps_section = self._dependencies_section(full_name)
        if deps_section:
            sections.append(deps_section)

        # Summaries (method + containing type)
        summary_fns = [full_name]
        parent = get_containing_type(self._conn, full_name)
        if parent:
            summary_fns.append(_p(parent)["full_name"])
        summaries_section = self._summaries_section(summary_fns)
        if summaries_section:
            sections.append(summaries_section)

        return "\n\n---\n\n".join(sections)

    def _context_edit_method(self, full_name: str, max_lines: int = -1) -> str:
        sections: list[str] = []

        sections.append(self._target_section(full_name, max_lines=max_lines, labels={"Method"}))

        # Interface contract
        contract = find_interface_contract(self._conn, full_name)
        if contract["interface"] is not None:
            contract_lines = [
                f"Interface: `{contract['interface']}`",
                f"Contract method: `{contract['contract_method']}`",
            ]
            if contract["sibling_implementations"]:
                siblings = ", ".join(
                    f"{s['class_name']} ({s['file_path']})"
                    for s in contract["sibling_implementations"]
                )
                contract_lines.append(f"Other implementations: {siblings}")
            sections.append("## Interface Contract\n\n" + "\n".join(contract_lines))

        # Direct callers
        callers_section = self._callers_section(full_name)
        if callers_section:
            sections.append(callers_section)

        # Relevant constructor deps
        parent = get_containing_type(self._conn, full_name)
        if parent:
            parent_fn = _p(parent)["full_name"]
            deps_section = self._relevant_deps_section(parent_fn, full_name)
            if deps_section:
                sections.append(deps_section)

        # Test coverage
        test_section = self._test_coverage_section(full_name)
        if test_section:
            sections.append(test_section)

        # Summaries
        summary_fns = [full_name]
        if parent:
            parent_fn = _p(parent)["full_name"]
            summary_fns.append(parent_fn)
            for iface in get_implemented_interfaces(self._conn, parent_fn):
                summary_fns.append(_p(iface)["full_name"])
        summaries_section = self._summaries_section(summary_fns)
        if summaries_section:
            sections.append(summaries_section)

        return "\n\n---\n\n".join(sections)

    _TYPE_CALLER_LIMIT = 10
    _TYPE_METHOD_LIMIT = 10

    def _context_edit_type(self, full_name: str, is_interface: bool = False, max_lines: int = -1) -> str:
        sections: list[str] = []

        labels = {"Interface"} if is_interface else {"Class"}
        sections.append(self._target_section(full_name, max_lines=max_lines, labels=labels))

        # Interface contracts (only for classes)
        if not is_interface:
            iface_section = self._interfaces_section(full_name)
            if iface_section:
                sections.append(iface_section)

        # Callers of public methods
        members = get_members_overview(self._conn, full_name)
        all_member_props = [_p(m) for m in members]
        methods = [mp for mp in all_member_props if "Method" in mp.get("_labels", [])]

        methods_with_callers = []
        for method in methods:
            method_fn = method["full_name"]
            results = find_callers_with_sites(self._conn, method_fn)
            if results:
                methods_with_callers.append((method, results))

        # Sort by caller count descending, limit to top N methods
        methods_with_callers.sort(key=lambda x: len(x[1]), reverse=True)
        omitted_methods = max(0, len(methods_with_callers) - self._TYPE_METHOD_LIMIT)
        callers_parts = []
        for method, results in methods_with_callers[:self._TYPE_METHOD_LIMIT]:
            sig = method.get("signature", method.get("name", "?"))
            method_lines = [f"### {method['full_name']} — {sig}"]
            for entry in results[:self._TYPE_CALLER_LIMIT]:
                caller_props = _p(entry["caller"])
                sites = entry["call_sites"]
                line_str = self._format_call_sites(sites)
                fp = caller_props.get("file_path", "")
                fn = caller_props["full_name"]
                if line_str:
                    method_lines.append(f"- `{fn}` — {fp} ({line_str})")
                else:
                    method_lines.append(f"- `{fn}` — {fp}")
            if len(results) > self._TYPE_CALLER_LIMIT:
                method_lines.append(f"... and {len(results) - self._TYPE_CALLER_LIMIT} more callers")
            callers_parts.append("\n".join(method_lines))

        if callers_parts:
            header = "## Callers of Public Methods"
            if omitted_methods > 0:
                header += f"\n\n(showing top {self._TYPE_METHOD_LIMIT} methods by caller count; {omitted_methods} more omitted)"
            sections.append(header + "\n\n" + "\n\n".join(callers_parts))
        elif methods:
            pass  # methods exist but none have callers — omit section
        else:
            sections.append("## Callers of Public Methods\n\nNo public methods found.")

        # Constructor dependencies (all, not filtered — skip for interfaces)
        if not is_interface:
            deps = find_all_deps(self._conn, full_name)
            if deps:
                dep_lines = []
                for dep_node in deps:
                    dep_fn = _p(dep_node)["full_name"]
                    dep_members = get_members_overview(self._conn, dep_fn)
                    dep_lines.append(f"### {dep_fn}\n" + "\n".join(_member_line(m) for m in dep_members))
                sections.append("## Constructor Dependencies\n\n" + "\n\n".join(dep_lines))

        # Test coverage (flat list across all methods)
        all_tests: list[dict] = []
        seen_tests: set[str] = set()
        for method in methods:
            for t in find_test_coverage(self._conn, method["full_name"]):
                if t["full_name"] not in seen_tests:
                    seen_tests.add(t["full_name"])
                    all_tests.append(t)
        if all_tests:
            test_lines = [f"- `{t['full_name']}` — {t['file_path']}" for t in all_tests]
            sections.append("## Test Coverage\n\n" + "\n".join(test_lines))

        # Summaries
        interfaces = get_implemented_interfaces(self._conn, full_name)
        summary_fns = [full_name] + [_p(iface)["full_name"] for iface in interfaces]
        summaries_section = self._summaries_section(summary_fns)
        if summaries_section:
            sections.append(summaries_section)

        return "\n\n---\n\n".join(sections)

    def trace_call_chain(self, start: str, end: str, max_depth: int = 6) -> dict:
        start = self._resolve(start, preference="concrete")
        end = self._resolve(end, preference="concrete")
        return trace_call_chain(self._conn, start, end, max_depth)

    def find_entry_points(
        self,
        method: str,
        max_depth: int = 8,
        exclude_pattern: str = "",
        exclude_test_callers: bool = True,
    ) -> dict:
        method = self._resolve(method, preference="concrete")
        return find_entry_points(self._conn, method, max_depth, exclude_pattern, exclude_test_callers)

    def get_call_depth(self, method: str, depth: int = 3) -> dict:
        method = self._resolve(method, preference="concrete")
        return get_call_depth(self._conn, method, depth)

    def analyze_change_impact(self, method: str) -> dict:
        method = self._resolve(method, preference="concrete")
        return analyze_change_impact(self._conn, method)

    def find_interface_contract(self, method: str) -> dict:
        method = self._resolve(method, preference="interface")
        return find_interface_contract(self._conn, method)

    def find_type_impact(self, type_name: str, limit: int = 50) -> dict:
        type_name = self._resolve(type_name)
        result = find_type_impact(self._conn, type_name)
        if len(result["references"]) > limit:
            result["_total_references"] = len(result["references"])
            result["references"] = result["references"][:limit]
            result["_truncated"] = True
        else:
            result["_total_references"] = len(result["references"])
        return result

    def audit_architecture(self, rule: str) -> dict:
        return audit_architecture(self._conn, rule)

    def summarize_from_graph(self, class_name: str) -> dict | None:
        """Auto-generate a structural summary of a class from graph data.

        The summary is returned but NOT stored automatically. Call set_summary
        to persist it after review.
        """
        class_name = self._resolve(class_name)
        symbol = _p(get_symbol(self._conn, class_name))
        if not symbol:
            return None

        interfaces = [
            _p(i)["full_name"]
            for i in get_implemented_interfaces(self._conn, class_name)
        ]

        members = get_members_overview(self._conn, class_name)
        method_count = len(members)

        deps = self.find_dependencies(class_name)
        dep_names = list({d["type"]["full_name"] for d in deps})

        impact = self.find_type_impact(class_name)
        dependents = [r["full_name"] for r in impact["references"] if r["context"] == "prod"]
        test_classes = list({
            r["full_name"].rsplit(".", 1)[0]
            for r in impact["references"]
            if r["context"] == "test"
        })

        parts = []
        name = symbol.get("name", class_name)
        if interfaces:
            parts.append(f"{name}: implements {', '.join(i.rsplit('.', 1)[-1] for i in interfaces)} ({method_count} methods).")
        else:
            parts.append(f"{name}: {symbol.get('kind', 'class')} ({method_count} methods).")

        if dep_names:
            parts.append(f"Dependencies: {', '.join(n.rsplit('.', 1)[-1] for n in dep_names)}.")

        if dependents or test_classes:
            dep_str = f"{len(dependents)} prod references" if dependents else ""
            test_str = f"{len(test_classes)} test references" if test_classes else ""
            combined = ", ".join(filter(None, [dep_str, test_str]))
            parts.append(f"Depended on by: {combined}.")

        return {
            "full_name": class_name,
            "summary": "\n".join(parts),
            "data": {
                "kind": symbol.get("kind", "class"),
                "interfaces": interfaces,
                "method_count": method_count,
                "dependencies": dep_names,
                "dependents": dependents,
                "test_classes": test_classes,
            },
        }

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
