from __future__ import annotations

import re

from synapps.graph.connection import GraphConnection
from synapps.graph.nodes import set_summary, remove_summary
from synapps.graph.lookups import (
    get_symbol, find_implementations, find_callers, find_callees,
    get_hierarchy, search_symbols, get_summary, list_summarized,
    list_projects, get_index_status, execute_readonly_query,
    get_symbol_source_info, check_staleness,
    get_members_overview, get_implemented_interfaces,
    resolve_full_name, resolve_full_name_with_labels,
    suggest_similar_names,
    find_type_references as query_find_type_references,
    find_dependencies as query_find_dependencies,
    find_field_dependencies as query_find_field_dependencies,
    find_http_endpoints as query_find_http_endpoints,
    find_http_dependency as query_find_http_dependency,
    find_tests_for as query_find_tests_for,
    find_test_coverage as query_find_test_coverage,
    _TEST_PATH_PATTERN,
)
from synapps.graph.traversal import trace_call_chain, find_entry_points, get_call_depth
from synapps.graph.analysis import analyze_change_impact, find_dead_code, find_type_impact, get_architecture_overview, find_untested
from synapps.plugin import LanguageRegistry, default_registry
from synapps.service.formatting import _p, _slim, _apply_limit, _short_ref, _member_line
from synapps.service.indexing import IndexingService
from synapps.service.context import ContextBuilder


class SynappsService:
    def __init__(
        self,
        conn: GraphConnection,
        registry: LanguageRegistry | None = None,
    ) -> None:
        self._conn = conn
        self._indexing = IndexingService(conn, registry)
        self._context = ContextBuilder(conn, service=self)
        self._project_roots: list[str] | None = None

    # --- Name resolution ---

    def _get_project_roots(self) -> list[str]:
        """Return cached list of indexed project root paths."""
        if self._project_roots is None:
            rows = self._conn.query("MATCH (r:Repository) RETURN r.path")
            self._project_roots = [r[0] for r in rows if r[0]]
        return self._project_roots

    def _rel_path(self, file_path: str) -> str:
        """Strip project root prefix from an absolute file path."""
        for root in self._get_project_roots():
            if file_path.startswith(root):
                return file_path[len(root):].lstrip("/")
        return file_path

    def _resolve(self, name: str, preference: str | None = None) -> str:
        """Resolve a possibly-short name to a fully qualified name.

        preference: 'concrete' prefers :Class, 'interface' prefers :Interface.
        For type nodes, filters directly by label. For method nodes, checks the
        containing type's label (via CONTAINS edge) to resolve interface-vs-concrete pairs.
        Raises ValueError if the name is ambiguous or not found.
        """
        result = resolve_full_name(self._conn, name)

        if result is None:
            suggestions = suggest_similar_names(self._conn, name)
            if suggestions:
                hint = ", ".join(suggestions[:5])
                raise ValueError(
                    f"Symbol not found: '{name}'. Did you mean: {hint}?"
                )
            raise ValueError(f"Symbol not found: '{name}'")

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

    # --- Indexing (delegated) ---

    def index_project(self, path, language="csharp", on_progress=None, plugin_files=None):
        return self._indexing.index_project(path, language, on_progress, plugin_files)

    def index_calls(self, path):
        return self._indexing.index_calls(path)

    def sync_project(self, path, plugin_files=None):
        return self._indexing.sync_project(path, plugin_files)

    def smart_index(self, path, language="csharp", on_progress=None, allowed_languages=None):
        return self._indexing.smart_index(path, language, on_progress, allowed_languages=allowed_languages)

    def index_method_implements(self):
        return self._indexing.index_method_implements()

    def delete_project(self, path):
        return self._indexing.delete_project(path)

    def watch_project(self, path, lsp_adapter=None, on_file_event=None):
        return self._indexing.watch_project(path, lsp_adapter, on_file_event)

    def unwatch_project(self, path):
        return self._indexing.unwatch_project(path)

    # --- Queries ---

    def get_symbol(self, full_name: str) -> dict | None:
        full_name = self._resolve(full_name)
        result = get_symbol(self._conn, full_name)
        return _p(result) if result is not None else None

    def find_implementations(self, full_name: str, limit: int = 50) -> list[dict] | dict:
        full_name = self._resolve(full_name, preference="interface")
        result = [_slim(item, "full_name", "file_path", "line") for item in find_implementations(self._conn, full_name)]
        return _apply_limit(result, limit)

    def find_callers(self, full_name: str, include_interface_dispatch: bool = True, exclude_test_callers: bool = True, limit: int = 50) -> list[dict] | dict:
        full_name = self._resolve(full_name, preference="concrete")
        result = [_slim(item, "full_name", "file_path", "line") for item in find_callers(self._conn, full_name, include_interface_dispatch, exclude_test_callers)]
        return _apply_limit(result, limit)

    def find_callees(self, full_name: str, include_interface_dispatch: bool = True, limit: int = 50) -> list[dict] | dict:
        full_name = self._resolve(full_name, preference="concrete")
        result = [_slim(item, "full_name", "name", "file_path", "line") for item in find_callees(self._conn, full_name, include_interface_dispatch)]
        return _apply_limit(result, limit)

    def get_hierarchy(self, full_name: str) -> dict:
        full_name = self._resolve(full_name)
        raw = get_hierarchy(self._conn, full_name)
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
        raw = [_slim(item, "full_name", "name", "kind", "file_path", "line", "language") for item in search_symbols(self._conn, query, kind, namespace, file_path, language)]
        for item in raw:
            if "file_path" in item:
                item["file_path"] = self._rel_path(item["file_path"])
        return _apply_limit(raw, limit)

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

    def find_usages(self, full_name: str, exclude_test_callers: bool = True, limit: int = 20) -> str:
        full_name = self._resolve(full_name)
        symbol = get_symbol(self._conn, full_name)
        if symbol is None:
            return f"Symbol not found: {full_name}"

        props = _p(symbol)
        labels = set(props.get("_labels", []))

        supported = labels & self._USAGES_SUPPORTED_LABELS
        if not supported:
            label = next(iter(labels), "unknown")
            return f"find_usages does not support {label} symbols"

        # Method/Property/Field — compact caller list
        if labels & {"Method", "Property", "Field"}:
            kind = "Method" if "Method" in labels else ("Property" if "Property" in labels else "Field")
            callers = self.find_callers(full_name, exclude_test_callers=exclude_test_callers, limit=limit)
            if isinstance(callers, dict):
                caller_list = callers["results"]
                total = callers["_total"]
            else:
                caller_list = callers
                total = len(callers)
            lines = [f"## Usages of {full_name} ({kind})", f"\n{total} callers:\n"]
            for c in caller_list:
                fp = self._rel_path(c.get("file_path", ""))
                ln = c.get("line", "")
                lines.append(f"- `{c['full_name']}` — {fp}:{ln}")
            if total > len(caller_list):
                lines.append(f"\n... and {total - len(caller_list)} more")
            return "\n".join(lines)

        # Class or Interface — compact tiered summary
        kind = "Interface" if "Interface" in labels else "Class"
        test_re = re.compile(_TEST_PATH_PATTERN) if exclude_test_callers else None

        # Type references
        raw_refs = [
            {"full_name": _slim(r["symbol"], "full_name").get("full_name", "?"),
             "file_path": _slim(r["symbol"], "file_path").get("file_path", ""),
             "kind": r["kind"]}
            for r in query_find_type_references(self._conn, full_name)
        ]
        if test_re:
            raw_refs = [r for r in raw_refs if not test_re.match(r.get("file_path", ""))]

        ref_total = len(raw_refs)

        # Collect affected files (use relative paths)
        affected_files: set[str] = set()
        for r in raw_refs:
            fp = r.get("file_path")
            if fp:
                affected_files.add(self._rel_path(fp))

        # Method callers — counts + short top callers per method
        members = get_members_overview(self._conn, full_name)
        all_members = [_p(m) for m in members]
        methods = [m for m in all_members if "Method" in set(m.get("_labels", []))]
        method_lines: list[str] = []
        total_method_callers = 0
        for method in methods:
            method_fn = method["full_name"]
            method_short = method.get("name", method_fn.rsplit(".", 1)[-1])
            callers = self.find_callers(method_fn, exclude_test_callers=exclude_test_callers, limit=1000)
            if isinstance(callers, dict):
                caller_list = callers["results"]
                count = callers["_total"]
            else:
                caller_list = callers
                count = len(callers)
            if count > 0:
                top = ", ".join(_short_ref(c["full_name"]) for c in caller_list[:5])
                method_lines.append(f"- {method_short}(): {count} callers — {top}")
                total_method_callers += count
                for c in caller_list:
                    fp = c.get("file_path")
                    if fp:
                        affected_files.add(self._rel_path(fp))

        # Group type references by file for compact display (short names, relative paths)
        refs_by_file: dict[str, list[str]] = {}
        for r in raw_refs[:limit]:
            fp = self._rel_path(r.get("file_path", "?"))
            refs_by_file.setdefault(fp, []).append(_short_ref(r["full_name"]))

        lines = [
            f"## Usages of {full_name} ({kind})",
            f"\n{ref_total} type references, {total_method_callers} method callers across {len(affected_files)} files",
        ]

        if refs_by_file:
            lines.append(f"\n### Type References ({min(ref_total, limit)} of {ref_total})\n")
            for fp, symbols in refs_by_file.items():
                lines.append(f"- {fp}: {', '.join(symbols)}")

        if method_lines:
            lines.append(f"\n### Method Callers ({total_method_callers} total)\n")
            # Sort by count descending
            method_lines.sort(key=lambda l: int(l.split("(): ")[1].split(" ")[0]), reverse=True)
            lines.extend(method_lines)

        return "\n".join(lines)

    def find_dependencies(self, full_name: str, depth: int = 1, limit: int = 50) -> list[dict] | dict:
        full_name = self._resolve(full_name)
        refs = [
            {"type": _slim(r["type"], "full_name", "file_path"), "depth": r["depth"]}
            for r in query_find_dependencies(self._conn, full_name, depth)
        ]
        result = _apply_limit(refs, limit)
        fields = query_find_field_dependencies(self._conn, full_name)
        if fields:
            return {"dependencies": result, "fields": fields}
        return result

    def find_http_endpoints(
        self,
        route: str | None = None,
        http_method: str | None = None,
        language: str | None = None,
        limit: int = 50,
    ) -> list[dict] | dict:
        rows = query_find_http_endpoints(
            self._conn, route=route, http_method=http_method, language=language,
        )
        result = []
        for ep_node, has_server, handler_node in rows:
            ep_props = _p(ep_node)
            handler_props = _p(handler_node) if handler_node is not None else None
            result.append({
                "route": ep_props.get("route"),
                "http_method": ep_props.get("http_method"),
                "handler_full_name": handler_props.get("full_name") if handler_props else None,
                "file_path": self._rel_path(handler_props["file_path"]) if handler_props and handler_props.get("file_path") else None,
                "line": handler_props.get("line") if handler_props else None,
                "language": handler_props.get("language") if handler_props else None,
                "has_server_handler": has_server,
            })
        return _apply_limit(result, limit)

    def trace_http_dependency(self, route: str, http_method: str) -> dict:
        data = query_find_http_dependency(self._conn, route, http_method)
        handler_node = data.get("handler")
        callers = data.get("callers", [])
        handler_props = _p(handler_node) if handler_node is not None else None
        server_handler = (
            {
                "full_name": handler_props.get("full_name"),
                "file_path": self._rel_path(handler_props["file_path"]) if handler_props.get("file_path") else None,
                "line": handler_props.get("line"),
                "language": handler_props.get("language"),
            }
            if handler_props else None
        )
        client_callers = []
        for c in callers:
            cp = _p(c)
            client_callers.append({
                "full_name": cp.get("full_name"),
                "file_path": self._rel_path(cp["file_path"]) if cp.get("file_path") else None,
                "line": cp.get("line"),
                "language": cp.get("language"),
            })
        return {
            "route": route,
            "http_method": http_method,
            "has_server_handler": handler_node is not None,
            "server_handler": server_handler,
            "client_callers": client_callers,
        }

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

    # --- Source & Context (delegated) ---

    def get_symbol_source(self, full_name: str, include_class_signature: bool = False) -> str | None:
        full_name = self._resolve(full_name)
        return self._context.get_symbol_source(full_name, include_class_signature)

    def get_context_for(self, full_name: str, scope: str | None = None, max_lines: int = 200) -> str | None:
        full_name = self._resolve(full_name, preference="concrete")
        return self._context.get_context_for(full_name, scope, max_lines)

    # --- Graph traversal & analysis ---

    def trace_call_chain(self, start: str, end: str, max_depth: int = 6) -> dict:
        start = self._resolve(start, preference="concrete")
        end = self._resolve(end, preference="concrete")
        return trace_call_chain(self._conn, start, end, max_depth)

    def find_entry_points(
        self,
        full_name: str,
        max_depth: int = 8,
        exclude_pattern: str = "",
        exclude_test_callers: bool = True,
    ) -> dict:
        full_name = self._resolve(full_name, preference="concrete")
        return find_entry_points(self._conn, full_name, max_depth, exclude_pattern, exclude_test_callers)

    def get_call_depth(self, full_name: str, depth: int = 3) -> dict:
        full_name = self._resolve(full_name, preference="concrete")
        return get_call_depth(self._conn, full_name, depth)

    def analyze_change_impact(self, full_name: str) -> str:
        full_name = self._resolve(full_name, preference="concrete")
        data = analyze_change_impact(self._conn, full_name)

        lines = [f"## Change Impact: {full_name}"]

        total = data["total_affected"]
        dc = len(data["direct_callers"])
        tc = len(data["transitive_callers"])
        tests = len(data["test_coverage"])
        lines.append(f"\n{total} affected — {dc} direct callers, {tc} transitive, {tests} tests\n")

        if data["direct_callers"]:
            lines.append("### Direct Callers\n")
            for c in data["direct_callers"]:
                lines.append(f"- `{_short_ref(c['full_name'])}` — {self._rel_path(c['file_path'])}")

        if data["transitive_callers"]:
            lines.append("\n### Transitive Callers\n")
            for c in data["transitive_callers"]:
                lines.append(f"- `{_short_ref(c['full_name'])}` — {self._rel_path(c['file_path'])}")

        if data["test_coverage"]:
            lines.append("\n### Test Coverage\n")
            for t in data["test_coverage"]:
                lines.append(f"- `{_short_ref(t['full_name'])}` — {self._rel_path(t['file_path'])}")

        if data["direct_callees"]:
            lines.append("\n### Direct Callees (downstream)\n")
            for c in data["direct_callees"]:
                lines.append(f"- `{_short_ref(c['full_name'])}` — {self._rel_path(c['file_path'])}")

        return "\n".join(lines)

    def find_type_impact(self, full_name: str, limit: int = 50) -> dict:
        full_name = self._resolve(full_name)
        result = find_type_impact(self._conn, full_name)
        if len(result["references"]) > limit:
            result["_total_references"] = len(result["references"])
            result["references"] = result["references"][:limit]
            result["_truncated"] = True
        else:
            result["_total_references"] = len(result["references"])
        return result

    def get_architecture_overview(self, limit: int = 10) -> dict:
        return get_architecture_overview(self._conn, limit=limit)

    def find_dead_code(self, exclude_pattern: str = "", limit: int = 15, offset: int = 0) -> dict:
        return find_dead_code(self._conn, exclude_pattern=exclude_pattern, limit=limit, offset=offset)

    def find_tests_for(self, full_name: str) -> list[dict]:
        full_name = self._resolve(full_name)
        result = query_find_tests_for(self._conn, full_name)
        if not result:
            result = query_find_test_coverage(self._conn, full_name)
        return result

    def find_untested(self, exclude_pattern: str = "", limit: int = 15, offset: int = 0) -> dict:
        return find_untested(self._conn, exclude_pattern=exclude_pattern, limit=limit, offset=offset)

