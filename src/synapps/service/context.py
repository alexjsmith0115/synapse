from __future__ import annotations

from typing import TYPE_CHECKING

from synapps.graph.connection import GraphConnection

if TYPE_CHECKING:
    from synapps.service import SynappsService
from synapps.graph.lookups import (
    get_symbol, get_symbol_source_info,
    get_containing_type, get_members_overview, get_implemented_interfaces,
    get_constructor, get_summary,
    find_callers_with_sites, find_callees,
    find_relevant_deps, find_all_deps, find_test_coverage,
    get_called_members, get_served_endpoint, find_http_callers,
    find_dependencies as query_find_dependencies,
)
from synapps.graph.analysis import find_interface_contract
from synapps.service.formatting import _p, _slim, _member_line


class ContextBuilder:
    _CALLER_LIMIT = 15
    _TYPE_CALLER_LIMIT = 10
    _TYPE_METHOD_LIMIT = 10

    def __init__(self, conn: GraphConnection, service: SynappsService | None = None) -> None:
        self._conn = conn
        self._service = service

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

    # --- Context entry point ---

    def get_context_for(self, full_name: str, scope: str | None = None, max_lines: int = 200, structured: bool = False) -> str | dict | None:
        # Impact scope delegates to SynappsService which handles its own resolution
        if scope == "impact":
            if self._service is None:
                return "Impact scope requires service reference"
            return self._service.analyze_change_impact(full_name, structured=structured)

        symbol = get_symbol(self._conn, full_name)
        if symbol is None:
            return None

        props = _p(symbol)
        labels = set(props.get("_labels", []))

        if scope == "structure":
            if not labels & {"Class", "Interface"}:
                if structured:
                    return {"error": f"scope='structure' requires a type (class or interface), but '{full_name}' is a {props.get('kind', 'unknown')}."}
                return f"scope='structure' requires a type (class or interface), but '{full_name}' is a {props.get('kind', 'unknown')}."
            return self._structured_structure(full_name) if structured else self._context_structure(full_name)
        elif scope == "method":
            if not labels & {"Method", "Property"}:
                if structured:
                    return {"error": f"scope='method' requires a method or property, but '{full_name}' is a {props.get('kind', 'unknown')}."}
                return f"scope='method' requires a method or property, but '{full_name}' is a {props.get('kind', 'unknown')}."
            return self._structured_method(full_name) if structured else self._context_method(full_name, max_lines=max_lines)
        elif scope == "edit":
            if labels & {"Method"}:
                return self._structured_edit_method(full_name) if structured else self._context_edit_method(full_name, max_lines=max_lines)
            elif labels & {"Class", "Interface"}:
                if structured:
                    return self._structured_edit_type(full_name, is_interface=bool(labels & {"Interface"}))
                return self._context_edit_type(full_name, is_interface=bool(labels & {"Interface"}), max_lines=max_lines)
            else:
                kind = props.get("kind", "unknown")
                if structured:
                    return {"error": f"scope='edit' requires a method, class, or interface, but '{full_name}' is a {kind}."}
                return f"scope='edit' requires a method, class, or interface, but '{full_name}' is a {kind}."
        elif scope is not None:
            if structured:
                return {"error": f"Unknown scope '{scope}'. Valid values: 'structure', 'method', 'edit', 'impact'."}
            return f"Unknown scope '{scope}'. Valid values: 'structure', 'method', 'edit', 'impact'."

        return self._structured_full(full_name, labels=labels) if structured else self._context_full(full_name, labels=labels, max_lines=max_lines)

    # --- Shared section builders ---

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

    def _interface_contract_section(self, full_name: str) -> str | None:
        contract = find_interface_contract(self._conn, full_name)
        if contract["interface"] is None:
            return None
        lines = [
            f"Interface: `{contract['interface']}`",
            f"Contract method: `{contract['contract_method']}`",
        ]
        if contract["sibling_implementations"]:
            siblings = ", ".join(
                f"{s['class_name']} ({s['file_path']})"
                for s in contract["sibling_implementations"]
            )
            lines.append(f"Other implementations: {siblings}")
        return "## Interface Contract\n\n" + "\n".join(lines)

    def _endpoint_section(self, full_name: str) -> str | None:
        ep = get_served_endpoint(self._conn, full_name)
        if not ep:
            return None
        lines = [f"## HTTP Endpoint\n\n`{ep['http_method']} {ep['route']}`"]
        http_callers = find_http_callers(self._conn, full_name)
        if http_callers:
            lines.append("\n**Client call sites:**")
            for c in http_callers:
                lines.append(f"- `{c['full_name']}` — {c['file_path']}")
        return "\n".join(lines)

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
        raw = find_callees(self._conn, full_name, include_interface_dispatch=True)
        callees = [_slim(item, "full_name", "signature") for item in raw]
        if not callees:
            return None
        lines = [f"- `{c['full_name']}` — {c.get('signature', '')}" for c in callees]
        return "## Called Methods\n\n" + "\n".join(lines)

    def _dependencies_section(self, full_name: str) -> str | None:
        raw = query_find_dependencies(self._conn, full_name, depth=1)
        deps = [{"type": _slim(r["type"], "full_name", "file_path"), "depth": r["depth"]} for r in raw]
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

    # --- Context composers ---

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

        contract_section = self._interface_contract_section(full_name)
        if contract_section:
            sections.append(contract_section)

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

        contract_section = self._interface_contract_section(full_name)
        if contract_section:
            sections.append(contract_section)

        # HTTP endpoint (if this method serves one)
        endpoint_section = self._endpoint_section(full_name)
        if endpoint_section:
            sections.append(endpoint_section)

        # Direct callers (always show section so users know it was checked)
        callers_section = self._callers_section(full_name)
        sections.append(callers_section or "## Direct Callers\n\nNo callers found.")

        # Relevant constructor deps
        parent = get_containing_type(self._conn, full_name)
        if parent:
            parent_fn = _p(parent)["full_name"]
            deps_section = self._relevant_deps_section(parent_fn, full_name)
            if deps_section:
                sections.append(deps_section)

        # Test coverage (always show section so users know it was checked)
        test_section = self._test_coverage_section(full_name)
        sections.append(test_section or "## Test Coverage\n\nNo tests found.")

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
            sections.append("## Callers of Public Methods\n\nNo callers found for any public method.")
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
        elif methods:
            sections.append("## Test Coverage\n\nNo tests found.")

        # Summaries
        interfaces = get_implemented_interfaces(self._conn, full_name)
        summary_fns = [full_name] + [_p(iface)["full_name"] for iface in interfaces]
        summaries_section = self._summaries_section(summary_fns)
        if summaries_section:
            sections.append(summaries_section)

        return "\n\n---\n\n".join(sections)

    # --- Structured output composers ---

    def _build_summaries_list(self, full_names: list[str]) -> list[dict]:
        entries = []
        for fn in full_names:
            s = get_summary(self._conn, fn)
            if s:
                entries.append({"full_name": fn, "summary": s})
        return entries

    def _build_interfaces_list(self, type_full_name: str) -> list[dict]:
        interfaces = get_implemented_interfaces(self._conn, type_full_name)
        rows = []
        for iface in interfaces:
            iface_fn = _p(iface)["full_name"]
            iface_members = get_members_overview(self._conn, iface_fn)
            for m in iface_members:
                mp = _p(m)
                rows.append({
                    "full_name": mp.get("full_name", ""),
                    "file_path": mp.get("file_path", ""),
                    "line": mp.get("line"),
                })
        return rows

    def _build_callees_list(self, full_name: str) -> list[dict]:
        raw = find_callees(self._conn, full_name, include_interface_dispatch=True)
        return [_slim(item, "full_name", "signature") for item in raw]

    def _build_dependencies_list(self, full_name: str) -> list[dict]:
        raw = query_find_dependencies(self._conn, full_name, depth=1)
        seen: set[str] = set()
        rows = []
        for dep in raw:
            type_node = dep["type"]
            type_fn = _slim(type_node, "full_name").get("full_name", "")
            if type_fn in seen:
                continue
            seen.add(type_fn)
            tp = _slim(type_node, "full_name", "file_path")
            rows.append({
                "full_name": tp.get("full_name", ""),
                "file_path": tp.get("file_path", ""),
                "line": _p(type_node).get("line"),
            })
        return rows

    def _build_callers_list(self, full_name: str, limit: int = _CALLER_LIMIT) -> list[dict]:
        results = find_callers_with_sites(self._conn, full_name)
        rows = []
        for entry in results[:limit]:
            caller_props = _p(entry["caller"])
            sites = entry["call_sites"]
            line_nums = sorted({s[0] for s in sites if s and s[0] is not None})
            rows.append({
                "full_name": caller_props.get("full_name", ""),
                "file_path": caller_props.get("file_path", ""),
                "line": line_nums[0] if line_nums else None,
            })
        return rows

    def _build_tests_list(self, full_name: str) -> list[dict]:
        tests = find_test_coverage(self._conn, full_name)
        return [{"full_name": t["full_name"], "file_path": t["file_path"]} for t in tests]

    def _structured_structure(self, full_name: str) -> dict:
        result: dict = {}

        ctor = get_constructor(self._conn, full_name)
        if ctor is not None:
            ctor_fn = _p(ctor)["full_name"]
            result["constructor_source"] = self.get_symbol_source(ctor_fn)
        else:
            result["constructor_source"] = None

        members_raw = get_members_overview(self._conn, full_name)
        result["members"] = []
        for m in members_raw:
            mp = _p(m)
            labels_list = mp.get("_labels", [])
            kind = next((l for l in labels_list if l not in {"_labels"}), mp.get("kind", ""))
            result["members"].append({
                "full_name": mp.get("full_name", ""),
                "kind": kind,
                "signature": mp.get("signature") or mp.get("type_name") or "",
                "file_path": mp.get("file_path", ""),
                "line": mp.get("line"),
            })

        result["interfaces"] = self._build_interfaces_list(full_name)

        interfaces = get_implemented_interfaces(self._conn, full_name)
        summary_fns = [full_name] + [_p(iface)["full_name"] for iface in interfaces]
        result["summaries"] = self._build_summaries_list(summary_fns)

        return result

    def _structured_method(self, full_name: str) -> dict:
        result: dict = {}

        result["source"] = self.get_symbol_source(full_name)

        contract = find_interface_contract(self._conn, full_name)
        if contract["interface"] is not None:
            result["interface_contract"] = contract
        else:
            result["interface_contract"] = None

        result["callees"] = self._build_callees_list(full_name)
        result["dependencies"] = self._build_dependencies_list(full_name)

        summary_fns = [full_name]
        parent = get_containing_type(self._conn, full_name)
        if parent:
            summary_fns.append(_p(parent)["full_name"])
        result["summaries"] = self._build_summaries_list(summary_fns)

        return result

    def _structured_edit_method(self, full_name: str) -> dict:
        result: dict = {}

        result["source"] = self.get_symbol_source(full_name)

        contract = find_interface_contract(self._conn, full_name)
        result["interface_contract"] = contract if contract["interface"] is not None else None

        ep = get_served_endpoint(self._conn, full_name)
        if ep:
            http_callers = find_http_callers(self._conn, full_name)
            result["endpoint"] = {
                "http_method": ep["http_method"],
                "route": ep["route"],
                "client_callers": [{"full_name": c["full_name"], "file_path": c["file_path"]} for c in http_callers],
            }
        else:
            result["endpoint"] = None

        result["callers"] = self._build_callers_list(full_name)

        parent = get_containing_type(self._conn, full_name)
        if parent:
            parent_fn = _p(parent)["full_name"]
            deps = find_relevant_deps(self._conn, parent_fn, full_name)
            dep_rows = []
            for dep_node in deps:
                dep_fn = _p(dep_node)["full_name"]
                dp = _slim(dep_node, "full_name", "file_path")
                dep_rows.append({
                    "full_name": dp.get("full_name", dep_fn),
                    "file_path": dp.get("file_path", ""),
                    "line": _p(dep_node).get("line"),
                })
            result["dependencies"] = dep_rows
        else:
            result["dependencies"] = []

        result["tests"] = self._build_tests_list(full_name)

        summary_fns = [full_name]
        if parent:
            parent_fn = _p(parent)["full_name"]
            summary_fns.append(parent_fn)
            for iface in get_implemented_interfaces(self._conn, parent_fn):
                summary_fns.append(_p(iface)["full_name"])
        result["summaries"] = self._build_summaries_list(summary_fns)

        return result

    def _structured_edit_type(self, full_name: str, is_interface: bool = False) -> dict:
        result: dict = {}

        result["source"] = self.get_symbol_source(full_name)

        if not is_interface:
            result["interfaces"] = self._build_interfaces_list(full_name)
        else:
            result["interfaces"] = []

        members_raw = get_members_overview(self._conn, full_name)
        all_member_props = [_p(m) for m in members_raw]
        methods = [mp for mp in all_member_props if "Method" in mp.get("_labels", [])]

        callers_rows = []
        for method in methods:
            method_fn = method["full_name"]
            results = find_callers_with_sites(self._conn, method_fn)
            for entry in results[:self._TYPE_CALLER_LIMIT]:
                caller_props = _p(entry["caller"])
                sites = entry["call_sites"]
                line_nums = sorted({s[0] for s in sites if s and s[0] is not None})
                callers_rows.append({
                    "full_name": caller_props.get("full_name", ""),
                    "file_path": caller_props.get("file_path", ""),
                    "line": line_nums[0] if line_nums else None,
                })
        result["callers"] = callers_rows

        all_tests: list[dict] = []
        seen_tests: set[str] = set()
        for method in methods:
            for t in find_test_coverage(self._conn, method["full_name"]):
                if t["full_name"] not in seen_tests:
                    seen_tests.add(t["full_name"])
                    all_tests.append({"full_name": t["full_name"], "file_path": t["file_path"]})
        result["tests"] = all_tests

        interfaces = get_implemented_interfaces(self._conn, full_name)
        summary_fns = [full_name] + [_p(iface)["full_name"] for iface in interfaces]
        result["summaries"] = self._build_summaries_list(summary_fns)

        return result

    def _structured_full(self, full_name: str, labels: set[str] | None = None) -> dict:
        result: dict = {}

        result["source"] = self.get_symbol_source(full_name)

        parent = get_containing_type(self._conn, full_name)
        if parent:
            parent_fn = _p(parent)["full_name"]
            members_raw = get_members_overview(self._conn, parent_fn)
            result["containing_type"] = {
                "name": parent_fn,
                "members": [
                    {
                        "full_name": _p(m).get("full_name", ""),
                        "kind": next((l for l in _p(m).get("_labels", []) if l not in {"_labels"}), ""),
                        "signature": _p(m).get("signature") or _p(m).get("type_name") or "",
                    }
                    for m in members_raw
                ],
            }
            result["interfaces"] = self._build_interfaces_list(parent_fn)
        else:
            result["containing_type"] = None
            result["interfaces"] = self._build_interfaces_list(full_name)

        result["callees"] = self._build_callees_list(full_name)
        result["dependencies"] = self._build_dependencies_list(full_name)

        summary_fns = [full_name]
        if parent:
            parent_fn = _p(parent)["full_name"]
            summary_fns.append(parent_fn)
            for iface in get_implemented_interfaces(self._conn, parent_fn):
                summary_fns.append(_p(iface)["full_name"])
        else:
            for iface in get_implemented_interfaces(self._conn, full_name):
                summary_fns.append(_p(iface)["full_name"])
        result["summaries"] = self._build_summaries_list(summary_fns)

        return result

    # --- Internal helpers ---

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
