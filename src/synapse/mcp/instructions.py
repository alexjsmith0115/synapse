"""Server-level instructions sent to every MCP client during initialization."""

SERVER_INSTRUCTIONS = """\
Synapse is a code intelligence graph. Use Synapse tools instead of grep or file reads \
for understanding code structure, relationships, and navigating symbols.

WORKFLOW:
- Projects must be indexed before querying. Call list_projects to check what is indexed, \
index_project to index a new project, sync_project to refresh a stale index.
- If queries return empty results, call get_index_status to check whether the project is indexed.

TOOL SELECTION (by task):
- Understand a symbol before editing: get_context_for with scope="edit" (not manual file reads)
- Find who calls a method: find_callers (not execute_query with CALLS pattern)
- Find what a method calls: find_callees (not execute_query)
- Read source code of a symbol: get_symbol_source (not reading files by line range)
- Full context (source + relationships): get_context_for (not get_symbol + get_symbol_source + find_callers separately)
- Find a symbol by name: search_symbols (not guessing full_name strings)
- All usages of any symbol: find_usages (auto-selects strategy by symbol kind)
- Impact analysis before changes: analyze_change_impact (not manual caller tracing)
- Trace call paths between two methods: trace_call_chain (not recursive find_callees)
- Find API/controller entry points: find_entry_points (not recursive find_callers)
- Find all classes implementing an interface: find_implementations
- Understand class inheritance: get_hierarchy
- Find constructor/field dependencies: find_dependencies
- Custom graph queries: call get_schema first, then execute_query (last resort — prefer dedicated tools)

AVOID:
- Do not use execute_query when a dedicated tool exists for the task.
- Do not read files with grep or cat when get_symbol_source or get_context_for can retrieve the exact code.
- Do not guess symbol names — use search_symbols to discover them first.
- Do not skip get_context_for with scope="edit" before modifying a method — it shows callers, \
dependencies, and tests that might break.

EFFICIENCY:
- Use the scope parameter on get_context_for to control detail level: \
"structure" for overview, "method" for focused, "edit" for modification prep.
- Use search_symbols with kind, namespace, or file_path filters to narrow results.\
"""
