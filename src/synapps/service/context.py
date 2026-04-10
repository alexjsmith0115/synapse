from __future__ import annotations

from synapps.graph.connection import GraphConnection
from synapps.graph.lookups import (
    get_symbol, get_symbol_source_info,
    get_containing_type, get_members_overview, get_implemented_interfaces,
    get_constructor, get_summary,
    find_callees,
    find_dependencies as query_find_dependencies,
)
from synapps.service.formatting import _p, _slim, _member_line


class ContextBuilder:
    def __init__(self, conn: GraphConnection) -> None:
        self._conn = conn

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
        source_lines = all_lines[line - 1:end_line]
        result = f"// {file_path}:{line}\n{''.join(source_lines)}"
        if include_class_signature:
            parent = self._get_parent_signature(full_name)
            if parent:
                result = parent + "\n\n" + result
        return result

    # --- Context entry point ---

    def get_context_for(self, full_name: str, members_only: bool = False, max_lines: int = 200, structured: bool = False) -> str | dict | None:
        symbol = get_symbol(self._conn, full_name)
        if symbol is None:
            return None

        props = _p(symbol)
        labels = set(props.get("_labels", []))

        if members_only:
            if not labels & {"Class", "Interface"}:
                if structured:
                    return {"error": f"members_only=True requires a type (class or interface), but '{full_name}' is a {props.get('kind', 'unknown')}."}
                return f"members_only=True requires a type (class or interface), but '{full_name}' is a {props.get('kind', 'unknown')}."
            return self._structured_structure(full_name) if structured else self._context_structure(full_name)

        return self._structured_full(full_name, labels=labels) if structured else self._context_full(full_name, labels=labels, max_lines=max_lines)

    # --- Shared section builders ---

    def _target_section(self, full_name: str, max_lines: int = -1, labels: set[str] | None = None) -> str:
        source = self.get_symbol_source(full_name)
        if source is not None and max_lines >= 0:
            line_count = source.count("\n") + 1
            if line_count > max_lines:
                note = f"[Source exceeds {max_lines} lines — showing structure. Use get_symbol_source on individual methods for full source.]"
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
            return f"// {parent_info['file_path']}:{parent_line}\n{all_lines[parent_line - 1].rstrip()}"
        except (OSError, IndexError):
            return f"// Containing type: {parent_full_name}"
