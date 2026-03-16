from __future__ import annotations

import logging
from collections.abc import Callable

from synapse.graph.connection import GraphConnection
from synapse.graph.nodes import set_summary, remove_summary
from synapse.graph.lookups import (
    get_symbol, find_implementations, find_callers, find_callees,
    get_hierarchy, search_symbols, get_summary, list_summarized,
    list_projects, get_index_status, execute_readonly_query,
    get_method_symbol_map, get_symbol_source_info, check_staleness,
    get_containing_type, get_members_overview, get_implemented_interfaces,
    get_constructor, resolve_full_name,
    find_type_references as query_find_type_references,
    find_dependencies as query_find_dependencies,
    find_callers_with_sites,
    find_relevant_deps,
    find_all_deps,
    find_test_coverage,
)
from synapse.graph.traversal import trace_call_chain, find_entry_points, get_call_depth
from synapse.graph.analysis import analyze_change_impact, find_interface_contract, find_type_impact, audit_architecture
from synapse.indexer.indexer import Indexer
from synapse.indexer.method_implements_indexer import MethodImplementsIndexer
from synapse.lsp.csharp import CSharpLSPAdapter
from synapse.lsp.interface import LSPAdapter
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


def _member_line(m) -> str:
    mp = _p(m)
    sig = mp.get("signature") or mp.get("type_name") or ""
    return f"  {mp.get('name', '?')}: {sig}"


class SynapseService:
    def __init__(self, conn: GraphConnection) -> None:
        self._conn = conn
        self._watchers: dict[str, FileWatcher] = {}

    def _resolve(self, name: str) -> str:
        """Resolve a possibly-short name to a fully qualified name.

        Raises ValueError if the name is ambiguous (matches multiple symbols).
        """
        result = resolve_full_name(self._conn, name)
        if isinstance(result, list):
            options = ", ".join(result[:10])
            raise ValueError(
                f"Ambiguous name '{name}' — matches: {options}. "
                "Use the fully qualified name."
            )
        return result

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
        if on_progress:
            on_progress("Starting language server...")
        lsp = CSharpLSPAdapter.create(path)
        indexer = Indexer(self._conn, lsp)
        indexer.index_project(path, language, on_progress=on_progress)

    def index_calls(self, path: str) -> None:
        """Run the relationship resolution pass on an already-structurally-indexed project."""
        from synapse.indexer.symbol_resolver import SymbolResolver
        lsp = CSharpLSPAdapter.create(path)
        symbol_map = get_method_symbol_map(self._conn)
        SymbolResolver(self._conn, lsp.language_server).resolve(path, symbol_map)
        lsp.shutdown()

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
        full_name = self._resolve(full_name)
        result = get_symbol(self._conn, full_name)
        return _p(result) if result is not None else None

    def find_implementations(self, interface_name: str) -> list[dict]:
        interface_name = self._resolve(interface_name)
        return [_p(item) for item in find_implementations(self._conn, interface_name)]

    def find_callers(self, method_full_name: str, include_interface_dispatch: bool = True, exclude_test_callers: bool = True) -> list[dict]:
        method_full_name = self._resolve(method_full_name)
        return [_p(item) for item in find_callers(self._conn, method_full_name, include_interface_dispatch, exclude_test_callers)]

    def find_callees(self, method_full_name: str, include_interface_dispatch: bool = True) -> list[dict]:
        method_full_name = self._resolve(method_full_name)
        return [_p(item) for item in find_callees(self._conn, method_full_name, include_interface_dispatch)]

    def get_hierarchy(self, class_name: str) -> dict:
        class_name = self._resolve(class_name)
        raw = get_hierarchy(self._conn, class_name)
        return {
            "parents": [_p(n) for n in raw["parents"]],
            "children": [_p(n) for n in raw["children"]],
            "implements": [_p(n) for n in raw["implements"]],
        }

    def search_symbols(
        self,
        query: str,
        kind: str | None = None,
        namespace: str | None = None,
        file_path: str | None = None,
    ) -> list[dict]:
        return [_p(item) for item in search_symbols(self._conn, query, kind, namespace, file_path)]

    def list_projects(self) -> list[dict]:
        return [_p(item) for item in list_projects(self._conn)]

    def get_index_status(self, path: str) -> dict | None:
        return get_index_status(self._conn, path)

    def execute_query(self, cypher: str) -> list[dict]:
        raw = execute_readonly_query(self._conn, cypher)
        return [{"row": [_p(cell) if hasattr(cell, "element_id") else cell for cell in row]} for row in raw]

    def find_type_references(self, full_name: str) -> list[dict]:
        full_name = self._resolve(full_name)
        return [{"symbol": _p(r["symbol"]), "kind": r["kind"]} for r in query_find_type_references(self._conn, full_name)]

    def find_dependencies(self, full_name: str, depth: int = 1) -> list[dict]:
        full_name = self._resolve(full_name)
        return [
            {"type": _p(r["type"]), "depth": r["depth"]}
            for r in query_find_dependencies(self._conn, full_name, depth)
        ]

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

    def get_context_for(self, full_name: str, scope: str | None = None) -> str | None:
        full_name = self._resolve(full_name)
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
            return self._context_method(full_name)
        elif scope == "edit":
            if labels & {"Method"}:
                return self._context_edit_method(full_name)
            elif labels & {"Class", "Interface"}:
                return self._context_edit_type(full_name, is_interface=bool(labels & {"Interface"}))
            else:
                kind = props.get("kind", "unknown")
                return f"scope='edit' requires a method, class, or interface, but '{full_name}' is a {kind}."
        elif scope is not None:
            return f"Unknown scope '{scope}'. Valid values: 'structure', 'method', 'edit'."

        return self._context_full(full_name)

    # -- Shared section builders used by _context_full / _context_structure / _context_method --

    def _target_section(self, full_name: str) -> str:
        source = self.get_symbol_source(full_name)
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
            members = get_members_overview(self._conn, dep_fn)
            dep_lines.append(f"### {dep_fn}\n" + "\n".join(_member_line(m) for m in members))
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

    def _context_full(self, full_name: str) -> str:
        sections: list[str] = []

        sections.append(self._target_section(full_name))

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

    def _context_method(self, full_name: str) -> str:
        sections: list[str] = []

        sections.append(self._target_section(full_name))

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

    def _context_edit_method(self, full_name: str) -> str:
        sections: list[str] = []

        sections.append(self._target_section(full_name))

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

    def _context_edit_type(self, full_name: str, is_interface: bool = False) -> str:
        sections: list[str] = []

        sections.append(self._target_section(full_name))

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
        start = self._resolve(start)
        end = self._resolve(end)
        return trace_call_chain(self._conn, start, end, max_depth)

    def find_entry_points(self, method: str, max_depth: int = 8, exclude_pattern: str = "") -> dict:
        method = self._resolve(method)
        return find_entry_points(self._conn, method, max_depth, exclude_pattern)

    def get_call_depth(self, method: str, depth: int = 3) -> dict:
        method = self._resolve(method)
        return get_call_depth(self._conn, method, depth)

    def analyze_change_impact(self, method: str) -> dict:
        method = self._resolve(method)
        return analyze_change_impact(self._conn, method)

    def find_interface_contract(self, method: str) -> dict:
        method = self._resolve(method)
        return find_interface_contract(self._conn, method)

    def find_type_impact(self, type_name: str) -> dict:
        type_name = self._resolve(type_name)
        return find_type_impact(self._conn, type_name)

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
