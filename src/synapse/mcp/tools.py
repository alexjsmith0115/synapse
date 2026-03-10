from __future__ import annotations

from synapse.service import SynapseService


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
        return service.get_symbol(full_name)

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
        return service.find_callees(method_full_name)

    @mcp.tool()
    def get_hierarchy(class_name: str) -> dict:
        return service.get_hierarchy(class_name)

    @mcp.tool()
    def search_symbols(query: str, kind: str | None = None) -> list[dict]:
        return service.search_symbols(query, kind)

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
    def execute_query(cypher: str) -> list[dict]:
        return service.execute_query(cypher)

    @mcp.tool()
    def watch_project(path: str) -> str:
        service.watch_project(path)
        return f"Watching {path}"

    @mcp.tool()
    def unwatch_project(path: str) -> str:
        service.unwatch_project(path)
        return f"Stopped watching {path}"

    @mcp.tool()
    def find_type_references(full_name: str) -> list[dict]:
        return service.find_type_references(full_name)

    @mcp.tool()
    def find_dependencies(full_name: str) -> list[dict]:
        return service.find_dependencies(full_name)

    @mcp.tool()
    def get_context_for(full_name: str) -> str:
        result = service.get_context_for(full_name)
        return result or f"Symbol not found: {full_name}"
