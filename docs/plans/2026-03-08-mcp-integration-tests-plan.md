# MCP Integration Tests Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add end-to-end integration tests for all 19 MCP tools using in-process FastMCP calls against a self-contained C# fixture project.

**Architecture:** A minimal C# project (`tests/fixtures/SynapseTest/`) is committed to the repo. A module-scoped pytest fixture creates a real `SynapseService` backed by FalkorDB, registers tools on a `FastMCP` instance, and indexes the fixture project once. Tests call `mcp.call_tool()` directly (async, wrapped with `asyncio.run()`).

**Tech Stack:** Python 3.11+, pytest, FastMCP (`mcp>=1.26`), FalkorDB, .NET SDK (for C# LSP indexing)

**Prerequisites to run:** FalkorDB on localhost:6379 (`docker run -p 6379:6379 -it --rm falkordb/falkordb:latest`), .NET SDK installed.

**Run with:** `pytest tests/mcp/ -v -m integration`

---

## Task 1: Create the C# fixture project

**Files:**
- Create: `tests/fixtures/SynapseTest/SynapseTest.csproj`
- Create: `tests/fixtures/SynapseTest/IAnimal.cs`
- Create: `tests/fixtures/SynapseTest/Animal.cs`
- Create: `tests/fixtures/SynapseTest/Dog.cs`
- Create: `tests/fixtures/SynapseTest/Cat.cs`
- Create: `tests/fixtures/SynapseTest/AnimalService.cs`

**Step 1: Create `SynapseTest.csproj`**

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Library</OutputType>
    <TargetFramework>net8.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
  </PropertyGroup>
</Project>
```

**Step 2: Create `IAnimal.cs`**

```csharp
namespace SynapseTest;

public interface IAnimal
{
    string Speak();
}
```

**Step 3: Create `Animal.cs`**

```csharp
namespace SynapseTest;

public abstract class Animal : IAnimal
{
    public string Name { get; set; }
    protected readonly string _species;

    protected Animal(string name, string species)
    {
        Name = name;
        _species = species;
    }

    public abstract string Speak();
}
```

**Step 4: Create `Dog.cs`**

```csharp
namespace SynapseTest;

public class Dog : Animal
{
    public Dog(string name) : base(name, "Canis lupus familiaris") { }

    public override string Speak() => "Woof!";
}
```

**Step 5: Create `Cat.cs`**

```csharp
namespace SynapseTest;

public class Cat : Animal
{
    public Cat(string name) : base(name, "Felis catus") { }

    public override string Speak() => "Meow!";
}
```

**Step 6: Create `AnimalService.cs`**

```csharp
namespace SynapseTest;

public class AnimalService
{
    private readonly IAnimal _animal;

    public AnimalService(IAnimal animal)
    {
        _animal = animal;
    }

    public string MakeNoise()
    {
        return _animal.Speak();
    }
}
```

**Step 7: Verify the project builds (optional sanity check)**

```bash
dotnet build tests/fixtures/SynapseTest/SynapseTest.csproj
```

Expected: Build succeeded with 0 error(s).

**Step 8: Commit**

```bash
git add tests/fixtures/
git commit -m "test: add SynapseTest C# fixture project for MCP integration tests"
```

---

## Task 2: Scaffold the test module with fixture and helpers

**Files:**
- Modify: `tests/mcp/test_tools_integration.py` (currently empty — only `__init__.py` exists in `tests/mcp/`)

**Step 1: Write the scaffold**

```python
"""
MCP tool integration tests.

Requires FalkorDB on localhost:6379 and .NET SDK.
Run with: pytest tests/mcp/ -v -m integration
"""
from __future__ import annotations

import asyncio
import json
import pathlib

import pytest
from mcp.server.fastmcp import FastMCP

from synapse.graph.connection import GraphConnection
from synapse.graph.schema import ensure_schema
from synapse.mcp.tools import register_tools
from synapse.service import SynapseService

FIXTURE_PATH = str(pathlib.Path(__file__).parent.parent / "fixtures" / "SynapseTest")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    """Run an async coroutine from a synchronous test."""
    return asyncio.run(coro)


def _content(result) -> list:
    """Extract the content list from a call_tool result.

    FastMCP 1.26 returns either (content_list, structured_dict) or bare
    content_list depending on the tool's return type annotation.
    """
    return result[0] if isinstance(result, tuple) else result


def _text(result) -> str:
    return _content(result)[0].text


def _json(result):
    return json.loads(_text(result))


# ---------------------------------------------------------------------------
# Module-scoped fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def mcp_server():
    conn = GraphConnection.create(graph_name="synapse_test_mcp")
    ensure_schema(conn)
    conn.execute("MATCH (n) DETACH DELETE n")

    service = SynapseService(conn=conn)
    mcp = FastMCP("synapse-test")
    register_tools(mcp, service)

    service.index_project(FIXTURE_PATH, "csharp")

    yield mcp

    conn.execute("MATCH (n) DETACH DELETE n")
```

**Step 2: Verify the file is importable**

```bash
source .venv/bin/activate
python -c "import tests.mcp.test_tools_integration"
```

Expected: no errors.

**Step 3: Commit**

```bash
git add tests/mcp/test_tools_integration.py
git commit -m "test: scaffold MCP integration test module with fixture and helpers"
```

---

## Task 3: Tool listing and project-level tests

**Files:**
- Modify: `tests/mcp/test_tools_integration.py`

Append the following tests to the file.

**Step 1: Add the tests**

```python
# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

EXPECTED_TOOLS = {
    "index_project", "list_projects", "delete_project", "get_index_status",
    "get_symbol", "get_symbol_source", "find_implementations", "find_callers",
    "find_callees", "get_hierarchy", "search_symbols", "set_summary",
    "get_summary", "list_summarized", "execute_query", "watch_project",
    "unwatch_project", "find_type_references", "find_dependencies",
    "get_context_for",
}


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_all_tools_registered(mcp_server: FastMCP) -> None:
    tools = _run(mcp_server.list_tools())
    names = {t.name for t in tools}
    assert EXPECTED_TOOLS == names


# ---------------------------------------------------------------------------
# Project-level tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_list_projects(mcp_server: FastMCP) -> None:
    result = _run(mcp_server.call_tool("list_projects", {}))
    projects = _json(result)
    paths = [p["path"] for p in projects]
    assert FIXTURE_PATH in paths


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_index_status(mcp_server: FastMCP) -> None:
    result = _run(mcp_server.call_tool("get_index_status", {"path": FIXTURE_PATH}))
    status = _json(result)
    assert status["file_count"] > 0
    assert status["symbol_count"] > 0
```

**Step 2: Run the tests (requires integration env)**

```bash
pytest tests/mcp/test_tools_integration.py -v -m integration -k "test_all_tools or test_list_projects or test_get_index_status"
```

Expected: 3 passed. If the fixture indexing step fails, check FalkorDB is running and .NET SDK is installed.

**Step 3: Commit**

```bash
git add tests/mcp/test_tools_integration.py
git commit -m "test: add MCP tool registration and project-level tests"
```

---

## Task 4: Symbol query tests

**Files:**
- Modify: `tests/mcp/test_tools_integration.py`

Append:

```python
# ---------------------------------------------------------------------------
# Symbol query tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_symbol(mcp_server: FastMCP) -> None:
    result = _run(mcp_server.call_tool("get_symbol", {"full_name": "SynapseTest.Dog"}))
    symbol = _json(result)
    assert symbol is not None
    assert symbol["full_name"] == "SynapseTest.Dog"


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_symbol_not_found(mcp_server: FastMCP) -> None:
    result = _run(mcp_server.call_tool("get_symbol", {"full_name": "DoesNotExist.Nope"}))
    assert _json(result) is None


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_symbol_source(mcp_server: FastMCP) -> None:
    result = _run(mcp_server.call_tool("get_symbol_source", {"full_name": "SynapseTest.Animal"}))
    source = _text(result)
    assert "Animal" in source
    assert "abstract" in source.lower() or "IAnimal" in source


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_search_symbols(mcp_server: FastMCP) -> None:
    result = _run(mcp_server.call_tool("search_symbols", {"query": "Animal"}))
    symbols = _json(result)
    names = [s["full_name"] for s in symbols]
    assert any("Dog" in n for n in names)
    assert any("Cat" in n for n in names)
    assert any("Animal" in n for n in names)
```

**Step 2: Run**

```bash
pytest tests/mcp/test_tools_integration.py -v -m integration -k "symbol"
```

Expected: 4 passed.

**Step 3: Commit**

```bash
git add tests/mcp/test_tools_integration.py
git commit -m "test: add MCP symbol query tool tests"
```

---

## Task 5: Relationship query tests

**Files:**
- Modify: `tests/mcp/test_tools_integration.py`

Append:

```python
# ---------------------------------------------------------------------------
# Relationship query tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_implementations(mcp_server: FastMCP) -> None:
    result = _run(mcp_server.call_tool("find_implementations", {"interface_name": "SynapseTest.IAnimal"}))
    impls = _json(result)
    names = [i["full_name"] for i in impls]
    assert "SynapseTest.Dog" in names
    assert "SynapseTest.Cat" in names


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_callers(mcp_server: FastMCP) -> None:
    result = _run(mcp_server.call_tool("find_callers", {"method_full_name": "SynapseTest.IAnimal.Speak"}))
    callers = _json(result)
    names = [c["full_name"] for c in callers]
    assert any("MakeNoise" in n or "AnimalService" in n for n in names)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_callees(mcp_server: FastMCP) -> None:
    result = _run(mcp_server.call_tool("find_callees", {"method_full_name": "SynapseTest.AnimalService.MakeNoise"}))
    callees = _json(result)
    names = [c["full_name"] for c in callees]
    assert any("Speak" in n for n in names)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_hierarchy(mcp_server: FastMCP) -> None:
    result = _run(mcp_server.call_tool("get_hierarchy", {"class_name": "SynapseTest.Dog"}))
    hierarchy = _json(result)
    # hierarchy dict should reference Animal and/or IAnimal somewhere
    text = json.dumps(hierarchy)
    assert "Animal" in text


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_type_references(mcp_server: FastMCP) -> None:
    result = _run(mcp_server.call_tool("find_type_references", {"full_name": "SynapseTest.IAnimal"}))
    refs = _json(result)
    names = [r.get("full_name", "") for r in refs]
    assert any("AnimalService" in n for n in names)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_dependencies(mcp_server: FastMCP) -> None:
    result = _run(mcp_server.call_tool("find_dependencies", {"full_name": "SynapseTest.AnimalService"}))
    deps = _json(result)
    names = [d.get("full_name", "") for d in deps]
    assert any("IAnimal" in n for n in names)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_context_for(mcp_server: FastMCP) -> None:
    result = _run(mcp_server.call_tool("get_context_for", {"full_name": "SynapseTest.AnimalService"}))
    context = _text(result)
    assert len(context) > 0
    assert "AnimalService" in context
```

**Step 2: Run**

```bash
pytest tests/mcp/test_tools_integration.py -v -m integration -k "find or hierarchy or context"
```

Expected: 7 passed. Note: `find_callers` and `find_callees` depend on CALLS edges being indexed — if they return empty lists, the call-edge indexing pass may not have run. Check `service.index_project` triggers both phases.

**Step 3: Commit**

```bash
git add tests/mcp/test_tools_integration.py
git commit -m "test: add MCP relationship query tool tests"
```

---

## Task 6: Summary tool tests

**Files:**
- Modify: `tests/mcp/test_tools_integration.py`

Append:

```python
# ---------------------------------------------------------------------------
# Summary tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_set_and_get_summary(mcp_server: FastMCP) -> None:
    _run(mcp_server.call_tool("set_summary", {
        "full_name": "SynapseTest.Dog",
        "content": "Represents a dog in the test fixture.",
    }))
    result = _run(mcp_server.call_tool("get_summary", {"full_name": "SynapseTest.Dog"}))
    assert _text(result) == "Represents a dog in the test fixture."


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_list_summarized(mcp_server: FastMCP) -> None:
    # Depends on test_set_and_get_summary having run first (module scope preserves state)
    result = _run(mcp_server.call_tool("list_summarized", {}))
    items = _json(result)
    names = [i.get("full_name") for i in items]
    assert "SynapseTest.Dog" in names
```

**Step 2: Run**

```bash
pytest tests/mcp/test_tools_integration.py -v -m integration -k "summary or summarized"
```

Expected: 2 passed.

**Step 3: Commit**

```bash
git add tests/mcp/test_tools_integration.py
git commit -m "test: add MCP summary tool tests"
```

---

## Task 7: Query and watch tool tests

**Files:**
- Modify: `tests/mcp/test_tools_integration.py`

Append:

```python
# ---------------------------------------------------------------------------
# execute_query
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_execute_valid_query(mcp_server: FastMCP) -> None:
    result = _run(mcp_server.call_tool("execute_query", {
        "cypher": "MATCH (n:Class) RETURN n.name LIMIT 5"
    }))
    rows = _json(result)
    assert isinstance(rows, list)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_execute_mutating_query_raises(mcp_server: FastMCP) -> None:
    with pytest.raises(Exception):
        _run(mcp_server.call_tool("execute_query", {
            "cypher": "CREATE (n:Fake) RETURN n"
        }))


# ---------------------------------------------------------------------------
# Watch tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_watch_and_unwatch_project(mcp_server: FastMCP) -> None:
    watch_result = _run(mcp_server.call_tool("watch_project", {"path": FIXTURE_PATH}))
    assert FIXTURE_PATH in _text(watch_result)

    unwatch_result = _run(mcp_server.call_tool("unwatch_project", {"path": FIXTURE_PATH}))
    assert FIXTURE_PATH in _text(unwatch_result)
```

**Step 2: Run**

```bash
pytest tests/mcp/test_tools_integration.py -v -m integration -k "query or watch"
```

Expected: 3 passed. Note: `test_execute_mutating_query_raises` expects any exception — FastMCP wraps tool errors, so the exception may be a `ToolError` or similar MCP exception type.

**Step 3: Commit**

```bash
git add tests/mcp/test_tools_integration.py
git commit -m "test: add MCP execute_query and watch tool tests"
```

---

## Task 8: Run the full suite and verify

**Step 1: Run all MCP integration tests**

```bash
pytest tests/mcp/ -v -m integration
```

Expected: all tests pass. The module fixture indexes the project once; total runtime is dominated by the indexing step (~30-120s depending on machine).

**Step 2: Also confirm unit tests still pass**

```bash
pytest tests/unit/ -v
```

Expected: 63 tests, all pass.

**Step 3: Push**

```bash
git push
```
