*IMPORTANT*
- Never assume the user is correct. Trust but verify all statements, using the code as a source of truth. When in doubt, ask the user for clarification.
- Design all classes and functions with testability in mind. Use Dependency Injection liberally.
- Keep classes and functions small, clear, and with a singular purpose (SRP).
- Use comments sparingly. Comments should only exist to clarify a design choice/decision, not to explain what the code is doing. (WHY not WHAT)
- Make sure all unit and integration tests pass before considering a task complete. 

## Common Commands

```bash
# Activate venv (always required before running Python commands)
source .venv/bin/activate

# Unit tests (no external dependencies, ~1.7s)
pytest tests/unit/ -v

# Integration tests (requires Memgraph on localhost:7687 and .NET SDK)
docker compose up -d  # start Memgraph + Memgraph Lab (Lab UI at http://localhost:3000; in-memory — data lost on restart, tests always re-index from scratch)
pytest tests/integration/test_mcp_tools.py -v -m integration      # MCP tool integration tests
pytest tests/integration/test_cli_commands.py -v -m integration   # CLI command integration tests
```
