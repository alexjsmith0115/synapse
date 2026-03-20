*IMPORTANT*
- Never assume the user is correct. Trust but verify all statements, using the code as a source of truth. When in doubt, ask the user for clarification.
- Design all classes and functions with testability in mind. Use Dependency Injection liberally.
- Keep classes and functions small, clear, and with a singular purpose (SRP).
- Use comments sparingly. Comments should only exist to clarify a design choice/decision, not to explain what the code is doing. (WHY not WHAT)
- Make sure all unit and integration tests pass before considering a task complete.
- Every bugfix must include a regression test that would have caught the bug.

## Synapse MCP

This project is indexed by the Synapse MCP server. Use it instead of grep/read for navigating code relationships:

- Before modifying a method, use `get_context_for` (scope="edit") to understand its callers, callees, dependencies, and test coverage
- Use `find_callers` / `find_usages` to trace how a symbol is used across the codebase — prefer this over grep
- Use `find_callees` or `get_call_depth` to understand what a method depends on downstream
- After making changes, use `analyze_change_impact` to verify no unexpected breakage
- Use `get_hierarchy` to understand inheritance before modifying class structures
- Use `search_symbols` to find symbols by name, kind, file, or namespace — faster and more precise than file search
- Use `execute_query` for ad-hoc Cypher queries; call `get_schema` first to see available labels and relationships
- If any issues with the MCP or inconsistencies in the graph vs filesystem are found, report this to the user as a side note. 

## Common Commands

```bash
# Activate venv (always required before running Python commands)
source .venv/bin/activate

# Unit tests (no external dependencies, ~1.7s)
pytest tests/unit/ -v

# Integration tests (requires Memgraph on localhost:7687 and .NET SDK)
docker compose up -d  # start Memgraph + Memgraph Lab (Lab UI at http://localhost:3000; in-memory — data lost on restart, tests always re-index from scratch)
pytest tests/integration/test_mcp_tools.py -v -m integration      # MCP tool integration(C#) tests
pytest tests/integration/test_mcp_tools_typescript.py -v -m integration # Typescript integration tests (MCP)
pytest tests/integration/test_mcp_tools_python.py -v -m integration # Python integration tests (MCP)

pytest tests/integration/test_cli_commands.py -v -m integration   # CLI command integration tests
pytest tests/integration/test_cli_commands_python.py -v -m integration   # Python CLI command integration tests
pytest tests/integration/test_cli_commands_typescript.py -v -m integration   # typescript CLI command integration tests
```
