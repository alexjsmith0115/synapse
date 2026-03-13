from __future__ import annotations

from synapse.service import SynapseService

_GRAPH_SCHEMA = {
    "node_labels": {
        "Repository": ["path", "name", "last_indexed"],
        "Directory": ["path", "name"],
        "File": ["path", "name"],
        "Package": ["name"],
        "Class": ["full_name", "name", "kind", "file_path", "line", "end_line", "signature"],
        "Interface": ["full_name", "name", "file_path", "line", "end_line"],
        "Method": ["full_name", "name", "file_path", "line", "end_line", "signature"],
        "Property": ["full_name", "name", "file_path", "line", "end_line"],
        "Field": ["full_name", "name", "file_path", "line", "end_line"],
    },
    "relationship_types": {
        "CONTAINS": "Repository/Directory/File/Class/Interface → any",
        "INHERITS": "Class → Class",
        "IMPLEMENTS": "Class → Interface  |  Method → Method (concrete implements interface method)",
        "DISPATCHES_TO": "Method → Method (interface method → concrete implementation; inverse of method-level IMPLEMENTS, written at index time to enable interface-crossing path traversal)",
        "CALLS": "Method → Method",
        "REFERENCES": "any → Class/Interface (field type, param type, return type)",
    },
    "notes": [
        "execute_query(cypher=...) accepts read-only Cypher only (no CREATE/MERGE/SET/DELETE/REMOVE/DROP).",
        "Nodes with summaries also carry the :Summarized label and a 'summary' property.",
        "Class.kind values: 'class', 'abstract_class', 'enum', 'record'.",
    ],
}


def register_tools(mcp: object, service: SynapseService) -> None:
    """Register all MCP tools on the given MCP server instance."""

    @mcp.tool()
    def index_project(path: str, language: str = "csharp") -> str:
        service.index_project(path, language)
        return f"Indexed {path}"

    @mcp.tool()
    def list_projects() -> list[dict]:
        return service.list_projects()

    @mcp.tool()
    def delete_project(path: str) -> str:
        service.delete_project(path)
        return f"Deleted {path}"

    @mcp.tool()
    def get_index_status(path: str) -> dict | None:
        return service.get_index_status(path)

    @mcp.tool()
    def get_symbol(full_name: str) -> dict | None:
        """Get a symbol node by full name (supports short names)."""
        result = service.get_symbol(full_name)
        if result:
            warning = service._staleness_warning(full_name)
            if warning:
                result["_staleness_warning"] = warning
        return result

    @mcp.tool()
    def get_symbol_source(full_name: str, include_class_signature: bool = False) -> str:
        result = service.get_symbol_source(full_name, include_class_signature)
        if result is not None:
            return result
        if service.get_symbol(full_name) is not None:
            return f"Source not available for {full_name} — re-index required"
        return f"Symbol not found: {full_name}"

    @mcp.tool()
    def find_implementations(interface_name: str) -> list[dict]:
        """Find all classes that implement the given interface.

        Accepts both full names (e.g. "MyNs.IFoo") and short names (e.g. "IFoo").
        Short names use a suffix match when an exact match is not found.
        """
        return service.find_implementations(interface_name)

    @mcp.tool()
    def find_callers(
        method_full_name: str,
        include_interface_dispatch: bool = True,
    ) -> list[dict]:
        """Find methods that call the given method.

        By default, includes callers that invoke this method through an interface
        (common in C# DI codebases). Set include_interface_dispatch=False for
        direct CALLS edges only.
        """
        return service.find_callers(method_full_name, include_interface_dispatch)

    @mcp.tool()
    def find_callees(
        method_full_name: str,
        include_interface_dispatch: bool = True,
    ) -> list[dict]:
        """Find methods called by the given method.

        By default, includes concrete implementations when the call site targets an
        interface method (common in C# DI codebases). Set include_interface_dispatch=False
        for direct CALLS edges only.
        """
        return service.find_callees(method_full_name, include_interface_dispatch)

    @mcp.tool()
    def get_hierarchy(class_name: str) -> dict:
        """Get the inheritance hierarchy for a class or interface (supports short names)."""
        result = service.get_hierarchy(class_name)
        warning = service._staleness_warning(class_name)
        if warning:
            result["_staleness_warning"] = warning
        return result

    @mcp.tool()
    def search_symbols(
        query: str,
        kind: str | None = None,
        namespace: str | None = None,
        file_path: str | None = None,
    ) -> list[dict]:
        """Search for symbols by name substring.

        kind: filter by node type. Valid values: Class, Interface, Method, Property,
              Field, Namespace, File, Directory, Repository.
        namespace: filter to symbols whose full_name starts with this prefix
                   (e.g. "MyNs.Services").
        file_path: filter to symbols defined in this file path.
        """
        return service.search_symbols(query, kind, namespace, file_path)

    @mcp.tool()
    def set_summary(full_name: str, content: str) -> str:
        service.set_summary(full_name, content)
        return f"Summary saved for {full_name}"

    @mcp.tool()
    def get_summary(full_name: str) -> str | None:
        return service.get_summary(full_name)

    @mcp.tool()
    def list_summarized(project_path: str | None = None) -> list[dict]:
        return service.list_summarized(project_path)

    @mcp.tool()
    def get_schema() -> dict:
        """Return the full graph schema: node labels with properties, relationship types, and usage notes.

        Use this before writing raw Cypher for execute_query.
        """
        return _GRAPH_SCHEMA

    @mcp.tool()
    def execute_query(cypher: str) -> list[dict]:
        """Execute a read-only Cypher query against the graph.

        Args:
            cypher: The Cypher query string to execute. Must be read-only.

        Read-only: CREATE, MERGE, SET, DELETE, REMOVE, DROP are blocked.

        Schema summary (call get_schema() for full details):
          Nodes: Repository, Directory, File, Package, Class, Interface, Method, Property, Field
          Edges: CONTAINS, INHERITS, IMPLEMENTS, DISPATCHES_TO, CALLS, REFERENCES
          Key properties: full_name, name, file_path, line, end_line, signature, kind

        Example: MATCH (m:Method {full_name: 'MyNs.MyClass.MyMethod'}) RETURN m
        """
        return service.execute_query(cypher)

    @mcp.tool()
    def watch_project(path: str) -> str:
        """Start a file watcher that automatically re-indexes changed .cs files.

        The watcher keeps the LSP process alive between file changes, enabling
        incremental re-indexing without a full index_project call. Use after
        index_project during active development sessions.
        """
        service.watch_project(path)
        return f"Watching {path}"

    @mcp.tool()
    def unwatch_project(path: str) -> str:
        """Stop the file watcher for the given project path.

        Call this when done with active development to release the LSP process.
        """
        service.unwatch_project(path)
        return f"Stopped watching {path}"

    @mcp.tool()
    def find_type_references(full_name: str) -> list[dict]:
        return service.find_type_references(full_name)

    @mcp.tool()
    def find_dependencies(full_name: str, depth: int = 1) -> list[dict]:
        """Find field-type dependencies for the given symbol.

        depth: how many hops to traverse (default 1 = direct deps only, max 5).
        Each result includes a 'depth' field indicating how many hops from the root.
        Useful for impact analysis — depth=2 shows transitive dependencies.
        """
        return service.find_dependencies(full_name, depth)

    @mcp.tool()
    def get_context_for(full_name: str) -> str:
        """Get rich context for a symbol: source, hierarchy, dependencies, and summaries.

        Useful for giving an AI full context before asking it to modify a class.
        """
        result = service.get_context_for(full_name)
        if result:
            warning = service._staleness_warning(full_name)
            if warning:
                result = f"\u26a0\ufe0f {warning}\n\n---\n\n{result}"
        return result or "Symbol not found."

    @mcp.tool()
    def trace_call_chain(start: str, end: str, max_depth: int = 6) -> dict:
        """Find all call paths between two methods up to max_depth hops.

        Supports short names (e.g. 'CreateMeeting' instead of full namespace).
        Returns {paths: [[str]], start, end, max_depth}.
        """
        return service.trace_call_chain(start, end, max_depth)

    @mcp.tool()
    def find_entry_points(method: str, max_depth: int = 8, exclude_pattern: str = "") -> dict:
        """Find all root callers (no incoming CALLS edges) that eventually call a method.

        Useful for finding controller/API entry points that reach a given service method.
        exclude_pattern: optional regex on full_name to filter unwanted entry points
        (e.g. ".*\\.Tests\\..*" excludes test methods, ".*Controller.*" narrows to controllers).
        Returns {entry_points: [{entry, path}], target, max_depth}.
        Each entry point appears once with the shortest path to the target.
        """
        return service.find_entry_points(method, max_depth, exclude_pattern)

    @mcp.tool()
    def get_call_depth(method: str, depth: int = 3) -> dict:
        """Get all methods reachable from a starting method up to N levels deep.

        Returns {root, callees: [{full_name, file_path, depth}], depth_limit}.
        """
        return service.get_call_depth(method, depth)

    @mcp.tool()
    def analyze_change_impact(method: str) -> dict:
        """Analyze the impact of changing a method: direct callers, transitive callers, test coverage.

        Returns {target, direct_callers, transitive_callers, test_coverage, total_affected}.
        """
        return service.analyze_change_impact(method)

    @mcp.tool()
    def find_interface_contract(method: str) -> dict:
        """Find the interface contract a method satisfies and all sibling implementations.

        Returns {method, interface, contract_method, sibling_implementations}.
        """
        return service.find_interface_contract(method)

    @mcp.tool()
    def find_type_impact(type_name: str) -> dict:
        """Find all code affected if a type's shape changes, categorized as prod or test.

        Returns {type, references: [{full_name, file_path, context}], prod_count, test_count}.
        """
        return service.find_type_impact(type_name)

    @mcp.tool()
    def audit_architecture(rule: str) -> dict:
        """Run an architectural audit rule against the codebase graph.

        Valid rules: layering_violations, untested_services, repeated_db_writes.
        Returns {rule, description, violations: [dict], count}.
        These rules are C#/.NET-specific.
        """
        return service.audit_architecture(rule)

    @mcp.tool()
    def summarize_from_graph(class_name: str) -> dict:
        """Auto-generate a structural summary of a class from graph data.

        Returns {full_name, summary, data: {kind, interfaces, method_count, dependencies, dependents, test_classes}}.
        The summary is NOT stored automatically — call set_summary to persist after review.
        """
        return service.summarize_from_graph(class_name)
