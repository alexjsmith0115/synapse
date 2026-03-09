# CLI & MCP Fix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix all CLI commands to return readable output and fix MCP JSON serialization by normalizing service layer returns to plain dicts.

**Architecture:** Apply `_p()` at every service method return boundary to strip FalkorDB Node objects to plain dicts (including their labels). CLI commands format those dicts as human-readable text. MCP tools get serializable data for free.

**Tech Stack:** Python 3.11+, FalkorDB (`falkordb.node.Node`), Typer CLI, pytest, `typer.testing.CliRunner`

---

### Task 1: Update `_p()` to include labels + normalize simple service methods

**Files:**
- Modify: `src/synapse/service.py`
- Test: `tests/unit/test_service.py`

**Step 1: Write the failing tests**

Add to `tests/unit/test_service.py`:

```python
from falkordb.node import Node as FalkorNode


def _node(labels: list[str], props: dict) -> FalkorNode:
    return FalkorNode(node_id=1, labels=labels, properties=props)


def test_p_extracts_properties_and_labels_from_falkordb_node():
    from synapse.service import _p
    node = _node(["Method"], {"full_name": "A.B", "signature": "B() : void"})
    result = _p(node)
    assert result == {"full_name": "A.B", "signature": "B() : void", "_labels": ["Method"]}


def test_p_passes_through_plain_dict():
    from synapse.service import _p
    d = {"full_name": "A.B"}
    assert _p(d) is d


def test_find_callers_returns_plain_dicts():
    svc = _service()
    node = _node(["Method"], {"full_name": "A.Caller", "signature": "Caller() : void"})
    with patch("synapse.service.find_callers", return_value=[node]):
        result = svc.find_callers("A.B")
    assert result == [{"full_name": "A.Caller", "signature": "Caller() : void", "_labels": ["Method"]}]


def test_find_implementations_returns_plain_dicts():
    svc = _service()
    node = _node(["Class"], {"full_name": "A.Impl"})
    with patch("synapse.service.find_implementations", return_value=[node]):
        result = svc.find_implementations("A.IService")
    assert result == [{"full_name": "A.Impl", "_labels": ["Class"]}]


def test_get_symbol_returns_plain_dict_with_labels():
    svc = _service()
    node = _node(["Class"], {"full_name": "A.Cls"})
    with patch("synapse.service.get_symbol", return_value=node):
        result = svc.get_symbol("A.Cls")
    assert result == {"full_name": "A.Cls", "_labels": ["Class"]}


def test_get_symbol_returns_none_when_not_found():
    svc = _service()
    with patch("synapse.service.get_symbol", return_value=None):
        result = svc.get_symbol("Missing")
    assert result is None
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_service.py::test_p_extracts_properties_and_labels_from_falkordb_node tests/unit/test_service.py::test_find_callers_returns_plain_dicts -v
```

Expected: FAIL — `_p()` does not yet include `_labels`

**Step 3: Update `_p()` in `src/synapse/service.py`**

Replace:
```python
def _p(node) -> dict:
    """Extract properties from a FalkorDB Node or pass through a plain dict (used in tests)."""
    return node.properties if hasattr(node, "properties") else node
```

With:
```python
def _p(node) -> dict:
    """Extract properties from a FalkorDB Node (including labels) or pass through a plain dict."""
    if hasattr(node, "properties"):
        result = dict(node.properties)
        if node.labels:
            result["_labels"] = list(node.labels)
        return result
    return node
```

**Step 4: Normalize simple service methods in `src/synapse/service.py`**

Replace each of these methods:

```python
def get_symbol(self, full_name: str) -> dict | None:
    result = get_symbol(self._conn, full_name)
    return _p(result) if result is not None else None

def find_implementations(self, interface_name: str) -> list[dict]:
    return [_p(item) for item in find_implementations(self._conn, interface_name)]

def find_callers(self, method_full_name: str) -> list[dict]:
    return [_p(item) for item in find_callers(self._conn, method_full_name)]

def find_callees(self, method_full_name: str) -> list[dict]:
    return [_p(item) for item in find_callees(self._conn, method_full_name)]

def search_symbols(self, query: str, kind: str | None = None) -> list[dict]:
    return [_p(item) for item in search_symbols(self._conn, query, kind)]

def list_projects(self) -> list[dict]:
    return [_p(item) for item in list_projects(self._conn)]

def list_summarized(self, project_path: str | None = None) -> list[dict]:
    return [_p(item) for item in list_summarized(self._conn, project_path)]
```

**Step 5: Run all tests**

```bash
pytest tests/unit/ -v
```

Expected: all pass (existing tests use plain dicts, `_p()` on a plain dict returns it unchanged)

**Step 6: Commit**

```bash
git add src/synapse/service.py tests/unit/test_service.py
git commit -m "fix: normalize service layer to return plain dicts with labels"
```

---

### Task 2: Normalize complex service methods

These return dicts with FalkorDB Nodes nested inside them.

**Files:**
- Modify: `src/synapse/service.py`
- Test: `tests/unit/test_service.py`

**Step 1: Write the failing tests**

Add to `tests/unit/test_service.py`:

```python
def test_find_type_references_unwraps_nested_nodes():
    svc = _service()
    node = _node(["Method"], {"full_name": "A.Caller"})
    with patch("synapse.service.query_find_type_references", return_value=[{"symbol": node, "kind": "parameter"}]):
        result = svc.find_type_references("A.IService")
    assert result == [{"symbol": {"full_name": "A.Caller", "_labels": ["Method"]}, "kind": "parameter"}]


def test_find_dependencies_unwraps_nested_nodes():
    svc = _service()
    node = _node(["Class"], {"full_name": "A.Dep"})
    with patch("synapse.service.query_find_dependencies", return_value=[{"type": node, "kind": "return_type"}]):
        result = svc.find_dependencies("A.Method")
    assert result == [{"type": {"full_name": "A.Dep", "_labels": ["Class"]}, "kind": "return_type"}]


def test_get_hierarchy_unwraps_nodes():
    svc = _service()
    parent = _node(["Class"], {"full_name": "A.Base"})
    child = _node(["Class"], {"full_name": "A.Child"})
    with patch("synapse.service.get_hierarchy", return_value={"parents": [parent], "children": [child]}):
        result = svc.get_hierarchy("A.Middle")
    assert result["parents"] == [{"full_name": "A.Base", "_labels": ["Class"]}]
    assert result["children"] == [{"full_name": "A.Child", "_labels": ["Class"]}]
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_service.py::test_find_type_references_unwraps_nested_nodes tests/unit/test_service.py::test_find_dependencies_unwraps_nested_nodes tests/unit/test_service.py::test_get_hierarchy_unwraps_nodes -v
```

Expected: FAIL

**Step 3: Update complex service methods in `src/synapse/service.py`**

Replace:

```python
def get_hierarchy(self, class_name: str) -> dict:
    return get_hierarchy(self._conn, class_name)

def find_type_references(self, full_name: str) -> list[dict]:
    return query_find_type_references(self._conn, full_name)

def find_dependencies(self, full_name: str) -> list[dict]:
    return query_find_dependencies(self._conn, full_name)
```

With:

```python
def get_hierarchy(self, class_name: str) -> dict:
    raw = get_hierarchy(self._conn, class_name)
    return {"parents": [_p(n) for n in raw["parents"]], "children": [_p(n) for n in raw["children"]]}

def find_type_references(self, full_name: str) -> list[dict]:
    return [{"symbol": _p(r["symbol"]), "kind": r["kind"]} for r in query_find_type_references(self._conn, full_name)]

def find_dependencies(self, full_name: str) -> list[dict]:
    return [{"type": _p(r["type"]), "kind": r["kind"]} for r in query_find_dependencies(self._conn, full_name)]
```

**Step 4: Run all tests**

```bash
pytest tests/unit/ -v
```

Expected: all pass

**Step 5: Commit**

```bash
git add src/synapse/service.py tests/unit/test_service.py
git commit -m "fix: normalize complex service methods (hierarchy, type-refs, dependencies)"
```

---

### Task 3: CLI — remove `index-calls`, add formatting, update list commands

**Files:**
- Modify: `src/synapse/cli/app.py`
- Create: `tests/unit/test_cli.py`

**Step 1: Write the failing tests**

Create `tests/unit/test_cli.py`:

```python
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner
from synapse.cli.app import app

runner = CliRunner()


def _svc(overrides: dict | None = None):
    """Return a MagicMock SynapseService with sensible defaults."""
    svc = MagicMock()
    svc.find_callers.return_value = []
    svc.find_callees.return_value = []
    svc.find_implementations.return_value = []
    svc.search_symbols.return_value = []
    svc.find_type_references.return_value = []
    svc.find_dependencies.return_value = []
    svc.get_hierarchy.return_value = {"parents": [], "children": []}
    if overrides:
        for k, v in overrides.items():
            setattr(svc, k, MagicMock(return_value=v))
    return svc


def test_callers_prints_full_name_and_signature():
    svc = _svc({"find_callers": [{"full_name": "A.Caller", "signature": "Caller() : void"}]})
    svc.get_symbol.return_value = {"full_name": "A.Method", "_labels": ["Method"]}
    with patch("synapse.cli.app._get_service", return_value=svc):
        result = runner.invoke(app, ["callers", "A.Method"])
    assert result.exit_code == 0
    assert "A.Caller" in result.output
    assert "Caller() : void" in result.output


def test_callers_prints_no_results_when_empty():
    svc = _svc()
    svc.get_symbol.return_value = {"full_name": "A.Method", "_labels": ["Method"]}
    with patch("synapse.cli.app._get_service", return_value=svc):
        result = runner.invoke(app, ["callers", "A.Method"])
    assert "No results" in result.output


def test_search_prints_full_name():
    svc = _svc({"search_symbols": [{"full_name": "A.MyClass", "name": "MyClass"}]})
    with patch("synapse.cli.app._get_service", return_value=svc):
        result = runner.invoke(app, ["search", "MyClass"])
    assert "A.MyClass" in result.output


def test_hierarchy_prints_labeled_sections():
    svc = _svc()
    svc.get_hierarchy.return_value = {
        "parents": [{"full_name": "A.Base"}],
        "children": [{"full_name": "A.Child"}],
    }
    with patch("synapse.cli.app._get_service", return_value=svc):
        result = runner.invoke(app, ["hierarchy", "A.Middle"])
    assert "Parents:" in result.output
    assert "A.Base" in result.output
    assert "Children:" in result.output
    assert "A.Child" in result.output


def test_type_refs_prints_full_name_and_kind():
    svc = _svc({"find_type_references": [{"symbol": {"full_name": "A.Caller"}, "kind": "parameter"}]})
    with patch("synapse.cli.app._get_service", return_value=svc):
        result = runner.invoke(app, ["type-refs", "A.IFoo"])
    assert "A.Caller" in result.output
    assert "parameter" in result.output


def test_dependencies_prints_full_name_and_kind():
    svc = _svc({"find_dependencies": [{"type": {"full_name": "A.Dep"}, "kind": "return_type"}]})
    with patch("synapse.cli.app._get_service", return_value=svc):
        result = runner.invoke(app, ["dependencies", "A.Method"])
    assert "A.Dep" in result.output
    assert "return_type" in result.output


def test_index_calls_command_does_not_exist():
    result = runner.invoke(app, ["index-calls", "/some/path"])
    assert result.exit_code != 0
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_cli.py -v
```

Expected: most FAIL — commands don't format output yet; `index-calls` still exists

**Step 3: Update `src/synapse/cli/app.py`**

Remove the `index-calls` command (delete the `index_calls` function entirely):

```python
# DELETE this entire function:
@app.command("index-calls")
def index_calls(path: str) -> None:
    """Index CALLS edges for an already-structurally-indexed project."""
    _get_service().index_calls(path)
    typer.echo(f"Call edges indexed for {path}")
```

Add a formatting helper after the `_get_service` function:

```python
def _fmt(sym: dict) -> str:
    """Format a symbol dict as 'full_name — signature' for methods, or just 'full_name' for types."""
    fn = sym.get("full_name", "?")
    sig = sym.get("signature")
    return f"{fn} — {sig}" if sig else fn
```

Replace these CLI commands with the formatted versions:

```python
@app.command()
def callers(method_full_name: str) -> None:
    """Find all methods that call a given method."""
    svc = _get_service()
    results = svc.find_callers(method_full_name)
    if not results:
        typer.echo("No results.")
        return
    for item in results:
        typer.echo(_fmt(item))


@app.command()
def callees(method_full_name: str) -> None:
    """Find all methods called by a given method."""
    svc = _get_service()
    results = svc.find_callees(method_full_name)
    if not results:
        typer.echo("No results.")
        return
    for item in results:
        typer.echo(_fmt(item))


@app.command()
def implementations(interface_name: str) -> None:
    """Find all concrete implementations of an interface."""
    svc = _get_service()
    results = svc.find_implementations(interface_name)
    if not results:
        typer.echo("No results.")
        return
    for item in results:
        typer.echo(_fmt(item))


@app.command()
def hierarchy(class_name: str) -> None:
    """Show the full inheritance chain for a class."""
    result = _get_service().get_hierarchy(class_name)
    parents = result["parents"]
    children = result["children"]
    typer.echo("Parents:")
    for p in parents:
        typer.echo(f"  {p.get('full_name', '?')}")
    if not parents:
        typer.echo("  (none)")
    typer.echo("Children:")
    for c in children:
        typer.echo(f"  {c.get('full_name', '?')}")
    if not children:
        typer.echo("  (none)")


@app.command()
def search(query: str, kind: Optional[str] = None) -> None:
    """Search symbols by name."""
    results = _get_service().search_symbols(query, kind)
    if not results:
        typer.echo("No results.")
        return
    for item in results:
        typer.echo(_fmt(item))


@app.command("type-refs")
def type_refs(full_name: str) -> None:
    """Find all symbols that reference a type."""
    results = _get_service().find_type_references(full_name)
    if not results:
        typer.echo("No results.")
        return
    for item in results:
        fn = item["symbol"].get("full_name", "?")
        kind = item.get("kind", "")
        typer.echo(f"{fn} ({kind})")


@app.command()
def dependencies(full_name: str) -> None:
    """Find all types referenced by a symbol."""
    results = _get_service().find_dependencies(full_name)
    if not results:
        typer.echo("No results.")
        return
    for item in results:
        fn = item["type"].get("full_name", "?")
        kind = item.get("kind", "")
        typer.echo(f"{fn} ({kind})")
```

**Step 4: Run all tests**

```bash
pytest tests/unit/ -v
```

Expected: all pass

**Step 5: Commit**

```bash
git add src/synapse/cli/app.py tests/unit/test_cli.py
git commit -m "fix: format CLI output as human-readable text, remove index-calls"
```

---

### Task 4: CLI — semantic validation for `callers`, `callees`, `implementations`

**Files:**
- Modify: `src/synapse/cli/app.py`
- Modify: `tests/unit/test_cli.py`

**Step 1: Write the failing tests**

Add to `tests/unit/test_cli.py`:

```python
def test_callers_errors_when_given_a_class():
    svc = MagicMock()
    svc.get_symbol.return_value = {"full_name": "A.MyClass", "_labels": ["Class"]}
    with patch("synapse.cli.app._get_service", return_value=svc):
        result = runner.invoke(app, ["callers", "A.MyClass"])
    assert result.exit_code != 0
    assert "Class" in result.output
    assert "not a Method" in result.output


def test_callees_errors_when_given_a_class():
    svc = MagicMock()
    svc.get_symbol.return_value = {"full_name": "A.MyClass", "_labels": ["Class"]}
    with patch("synapse.cli.app._get_service", return_value=svc):
        result = runner.invoke(app, ["callees", "A.MyClass"])
    assert result.exit_code != 0
    assert "not a Method" in result.output


def test_implementations_errors_when_given_a_class():
    svc = MagicMock()
    svc.get_symbol.return_value = {"full_name": "A.MyClass", "_labels": ["Class"]}
    with patch("synapse.cli.app._get_service", return_value=svc):
        result = runner.invoke(app, ["implementations", "A.MyClass"])
    assert result.exit_code != 0
    assert "synapse hierarchy" in result.output


def test_callers_errors_when_symbol_not_found():
    svc = MagicMock()
    svc.get_symbol.return_value = None
    with patch("synapse.cli.app._get_service", return_value=svc):
        result = runner.invoke(app, ["callers", "A.Missing"])
    assert result.exit_code != 0
    assert "not found" in result.output.lower()
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_cli.py::test_callers_errors_when_given_a_class tests/unit/test_cli.py::test_implementations_errors_when_given_a_class -v
```

Expected: FAIL — no validation exists yet

**Step 3: Add validation helper and update commands in `src/synapse/cli/app.py`**

Add after `_fmt`:

```python
def _require_label(svc: "SynapseService", full_name: str, required: str, hint: str) -> bool:
    """Check that a symbol exists and has the required node label.
    Prints an error and returns False if the check fails."""
    sym = svc.get_symbol(full_name)
    if sym is None:
        typer.echo(f"Symbol not found: {full_name}", err=True)
        return False
    labels = sym.get("_labels", [])
    if required not in labels:
        actual = labels[0] if labels else "Unknown"
        typer.echo(hint.format(name=full_name, actual=actual), err=True)
        return False
    return True
```

Update `callers`, `callees`, and `implementations` to call `_require_label` before the service query:

```python
@app.command()
def callers(method_full_name: str) -> None:
    """Find all methods that call a given method."""
    svc = _get_service()
    if not _require_label(
        svc, method_full_name, "Method",
        "'{name}' is a {actual}, not a Method. Try a specific method like '{name}.MethodName'.",
    ):
        raise typer.Exit(1)
    results = svc.find_callers(method_full_name)
    if not results:
        typer.echo("No results.")
        return
    for item in results:
        typer.echo(_fmt(item))


@app.command()
def callees(method_full_name: str) -> None:
    """Find all methods called by a given method."""
    svc = _get_service()
    if not _require_label(
        svc, method_full_name, "Method",
        "'{name}' is a {actual}, not a Method. Try a specific method like '{name}.MethodName'.",
    ):
        raise typer.Exit(1)
    results = svc.find_callees(method_full_name)
    if not results:
        typer.echo("No results.")
        return
    for item in results:
        typer.echo(_fmt(item))


@app.command()
def implementations(interface_name: str) -> None:
    """Find all concrete implementations of an interface."""
    svc = _get_service()
    if not _require_label(
        svc, interface_name, "Interface",
        "'{name}' is a {actual}. To find what interfaces it implements, use: synapse hierarchy {name}",
    ):
        raise typer.Exit(1)
    results = svc.find_implementations(interface_name)
    if not results:
        typer.echo("No results.")
        return
    for item in results:
        typer.echo(_fmt(item))
```

**Step 4: Run all tests**

```bash
pytest tests/unit/ -v
```

Expected: all pass

**Step 5: Commit**

```bash
git add src/synapse/cli/app.py tests/unit/test_cli.py
git commit -m "fix: add semantic validation to callers, callees, implementations"
```

---

### Task 5: Smoke-test against live graph

Verify the fixes work end-to-end against an indexed C# project.

**Step 1: Run smoke tests**

```bash
# Should list implementations of the interface
synapse implementations <Namespace>.IEncryptionService

# Should list callers of a specific method
synapse callers <Namespace>.EncryptionService.Encrypt

# Should print helpful error when given a class name
synapse callers <Namespace>.EncryptionService

# Should print helpful error when given a class for implementations
synapse implementations <Namespace>.EncryptionService

# Should show hierarchy sections
synapse hierarchy <Namespace>.EncryptionService

# Should list symbols by name
synapse search Encryption

# Should show type references
synapse type-refs <Namespace>.IEncryptionService

# Should confirm index-calls is gone
synapse index-calls /path 2>&1 | grep -i "no such command"
```

**Step 2: Re-index if needed**

If any command returns "No results." unexpectedly (e.g. `callers`, `type-refs`), the graph may need re-indexing:

```bash
synapse delete <path/to/csharp/project>
synapse index <path/to/csharp/project>
```

Then re-run the smoke tests.
