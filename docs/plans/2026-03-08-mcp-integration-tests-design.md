# MCP Integration Tests Design

## Overview

Add end-to-end integration tests for the MCP tool layer using in-process FastMCP calls against a self-contained C# fixture project. Tests verify tool registration, parameter marshaling, and return value serialization across all 19 tools.

## Approach

Use FastMCP's async `call_tool()` and `list_tools()` methods directly in-process. A real `SynapseService` backed by a real FalkorDB connection indexes the fixture project once at module scope. No transport layer (stdio/HTTP) is involved — the tool dispatch chain is what's being tested.

Async calls are wrapped with a module-level `_run(coro)` helper using `asyncio.run()`. No additional test libraries needed beyond what's already installed.

## Fixture C# Project

**Location:** `tests/fixtures/SynapseTest/`

```
SynapseTest.csproj
IAnimal.cs          — interface with Speak() → string
Animal.cs           — abstract class implementing IAnimal, Name property, field
Dog.cs              — extends Animal, overrides Speak()
Cat.cs              — extends Animal, overrides Speak()
AnimalService.cs    — takes IAnimal via constructor (DI), MakeNoise() calls _animal.Speak()
```

Relationships covered:
- Interface + implementations (IAnimal → Dog, Cat)
- Inheritance (Animal → Dog, Cat)
- DI pattern (AnimalService depends on IAnimal)
- Method calls (MakeNoise → Speak)
- Properties and fields

## Test Structure

**File:** `tests/mcp/test_tools_integration.py`

Module-scoped `mcp_server` fixture:
1. Creates `GraphConnection("synapse_test_mcp")`, ensures schema, clears graph
2. Creates `SynapseService` and `FastMCP`, calls `register_tools()`
3. Indexes the fixture project
4. Yields the `FastMCP` instance
5. Deletes graph on teardown

Marker: `@pytest.mark.integration`

## Tool Coverage

| Tool | Assertion |
|---|---|
| `list_tools` | all 19 tool names present |
| `list_projects` | fixture path appears |
| `get_index_status` | file_count > 0, symbol_count > 0 |
| `get_symbol` | `SynapseTest.Dog` returns dict with full_name |
| `get_symbol_source` | returns C# source lines for `Animal` |
| `find_implementations` | `IAnimal` → contains Dog and Cat |
| `find_callers` | `IAnimal.Speak` → MakeNoise in AnimalService |
| `find_callees` | `AnimalService.MakeNoise` → Speak |
| `get_hierarchy` | `Dog` → parents include Animal and IAnimal |
| `search_symbols` | `"Animal"` → at least Dog, Cat, Animal |
| `find_type_references` | `IAnimal` → AnimalService references it |
| `find_dependencies` | `AnimalService` → IAnimal appears |
| `get_context_for` | `AnimalService` → non-empty string |
| `set_summary` / `get_summary` | round-trip on Dog |
| `list_summarized` | Dog appears after set_summary |
| `execute_query` | valid Cypher returns list; mutating raises |
| `watch_project` / `unwatch_project` | returns expected strings, no exception |
| `index_project` | done in fixture setup |
| `delete_project` | done in fixture teardown |

## Dependencies

- FalkorDB running on localhost:6379
- .NET SDK (for C# LSP indexing)
- Run with: `pytest tests/mcp/ -v -m integration`
