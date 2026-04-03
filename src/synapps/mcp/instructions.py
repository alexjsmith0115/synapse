"""Server-level instructions sent to every MCP client during initialization."""

SERVER_INSTRUCTIONS = """\
Synapps is a code intelligence graph. Use Synapps tools instead of grep or file reads \
for understanding code structure, relationships, and navigating symbols.

WORKFLOW:
- Projects must be indexed before querying. Call list_projects to check what is indexed, \
index_project to index a new project, sync_project to refresh a stale index.
- If queries return empty results, call list_projects(path=...) to check whether the project is indexed.

TOOL SELECTION (by task):
- Understand a symbol before editing: get_context_for with scope="edit" (not manual file reads)
- Read source code of a symbol: get_context_for (not reading files by line range)
- Symbol metadata (file, line, kind): get_context_for with scope="structure"
- Find a symbol by name: search_symbols (not guessing full_name strings)
- Find who calls a method: find_usages (auto-selects strategy by symbol kind)
- Find what a method calls: find_callees (not execute_query). Use depth param for reachable call tree
- All usages of any symbol: find_usages. Use kind param to filter type references
- Impact analysis before changes: get_context_for with scope="impact" (not manual caller tracing)
- Find API/controller entry points: find_entry_points (not recursive find_callers)
- Find all classes implementing an interface: find_implementations
- Understand class inheritance: get_hierarchy
- Find constructor/field dependencies: find_dependencies
- Architecture overview of a project: get_architecture (packages, hotspots, HTTP map, stats in one call)
- [Experimental] Find dead code (methods with zero callers): find_dead_code (excludes tests, HTTP handlers, \
interface implementations, dispatch targets, constructors, overrides)
- [Experimental] Find which tests cover a method: find_tests_for (direct TESTS edge lookup)
- [Experimental] Find production methods with no test coverage: find_untested (same exclusions as find_dead_code)
- Annotate symbols with non-derivable context (design rationale, constraints, ownership, \
deprecation plans): summary with action='set'/'get'/'list'. Do NOT store structural descriptions \
— use get_context_for, find_dependencies, etc. for that
- Custom graph queries: call get_schema first, then execute_query (last resort -- prefer dedicated tools)

AVOID:
- Do not use execute_query when a dedicated tool exists for the task.
- Do not read files with grep or cat when get_context_for can retrieve the exact code.
- Do not guess symbol names -- use search_symbols to discover them first.
- Do not skip get_context_for with scope="edit" before modifying a method -- it shows callers, \
dependencies, and tests that might break.

EFFICIENCY:
- Use the scope parameter on get_context_for to control detail level: \
"structure" for overview, "method" for focused, "edit" for modification prep, "impact" for change analysis.
- Use search_symbols with kind, namespace, or file_path filters to narrow results.

KNOWN GRAPH BOUNDARIES:
- Only project-defined symbols are indexed. Calls to external framework types (Spring Data, \
RestTemplate, JDK stdlib, .NET BCL, Entity Framework) do not appear as CALLS edges. \
Use get_context_for to read call sites directly when framework method calls are needed.

CLI-ONLY TOOLS (not available via MCP):
- synapps doctor -- check runtime environment and dependencies
- synapps delete <path> -- delete a project and all its graph data
- synapps status <path> -- detailed index status (also available via list_projects(path=...))

HTTP ENDPOINTS:
- Search endpoints by route, HTTP method, or language: find_http_endpoints (substring match on route)
- Trace server handler + all client call sites: find_http_endpoints with trace=True (requires exact route and http_method).\
"""
