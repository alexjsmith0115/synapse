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
        "CALLS": "Method → Method",
        "REFERENCES": "any → Class/Interface (field type, param type, return type)",
    },
    "notes": [
        "execute_query accepts read-only Cypher only (no CREATE/MERGE/SET/DELETE/REMOVE/DROP).",
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
    def find_callees(method_full_name: str) -> list[dict]:
        """Find methods called by the given method (direct CALLS edges only).

        Note: in C# DI codebases, callees are often interface methods. The graph
        stores the edge to the concrete or interface method depending on the call site.
        """
        return service.find_callees(method_full_name)

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

        Read-only: CREATE, MERGE, SET, DELETE, REMOVE, DROP are blocked.

        Schema summary (call get_schema() for full details):
          Nodes: Repository, Directory, File, Package, Class, Interface, Method, Property, Field
          Edges: CONTAINS, INHERITS, IMPLEMENTS, CALLS, REFERENCES
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
