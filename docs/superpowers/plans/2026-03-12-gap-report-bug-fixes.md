# Gap Report Bug Fixes — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix six interface-dispatch bugs by indexing method-level IMPLEMENTS edges, and three independent bugs (hierarchy disambiguation, change impact filtering, duplicate projects).

**Architecture:** New `MethodImplementsIndexer` class runs as Phase 1.5 after the structural pass. All traversal queries that cross an interface dispatch gap get an expanded end-node condition. Three targeted query/node fixes cover the remaining bugs.

**Tech Stack:** Python 3.11+, FalkorDB (Cypher), pytest, `unittest.mock.MagicMock`.

**Spec:** `docs/superpowers/specs/2026-03-12-gap-report-bug-fixes-design.md`

---

## Chunk 1: Phase 1.5 — MethodImplementsIndexer

### Task 1: Add `upsert_method_implements` to `edges.py`

**Files:**
- Modify: `src/synapse/graph/edges.py`
- Test: `tests/unit/graph/test_edges.py`

- [ ] **Step 1.1: Write the failing test**

Add to `tests/unit/graph/test_edges.py` (note: `MagicMock` is already imported at the top of this file; also add `upsert_method_implements` to the existing import from `synapse.graph.edges`):

```python
def test_upsert_method_implements_writes_edge() -> None:
    conn = MagicMock()
    upsert_method_implements(conn, "Ns.Impl.CreateAsync", "Ns.IFoo.CreateAsync")
    cypher, params = conn.execute.call_args[0]
    assert "IMPLEMENTS" in cypher
    assert params["impl"] == "Ns.Impl.CreateAsync"
    assert params["iface"] == "Ns.IFoo.CreateAsync"
```

- [ ] **Step 1.2: Run test to verify it fails**

```bash
cd /Users/alex/Dev/mcpcontext && source .venv/bin/activate
pytest tests/unit/graph/test_edges.py::test_upsert_method_implements_writes_edge -v
```

Expected: `ImportError` or `AttributeError` — `upsert_method_implements` does not exist.

- [ ] **Step 1.3: Add `upsert_method_implements` to `edges.py`**

Append after `upsert_implements` (the last IMPLEMENTS-related function):

```python
def upsert_method_implements(conn: GraphConnection, impl_method: str, iface_method: str) -> None:
    conn.execute(
        "MATCH (impl:Method {full_name: $impl}), (iface:Method {full_name: $iface}) "
        "MERGE (impl)-[:IMPLEMENTS]->(iface)",
        {"impl": impl_method, "iface": iface_method},
    )
```

- [ ] **Step 1.4: Run test to verify it passes**

```bash
pytest tests/unit/graph/test_edges.py::test_upsert_method_implements_writes_edge -v
```

Expected: PASS

- [ ] **Step 1.5: Commit**

```bash
git add src/synapse/graph/edges.py tests/unit/graph/test_edges.py
git commit -m "feat: add upsert_method_implements edge function

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 2: Create `MethodImplementsIndexer`

**Files:**
- Create: `src/synapse/indexer/method_implements_indexer.py`
- Create: `tests/unit/indexer/test_method_implements_indexer.py`

- [ ] **Step 2.1: Write the failing tests**

Create `tests/unit/indexer/test_method_implements_indexer.py`:

```python
from unittest.mock import MagicMock, call

from synapse.indexer.method_implements_indexer import MethodImplementsIndexer


def test_index_writes_edge_for_shared_method_name() -> None:
    conn = MagicMock()
    conn.query.side_effect = [
        # _get_impl_pairs
        [["Ns.MeetingService", "Ns.IMeetingService"]],
        # _get_methods(MeetingService)
        [["CreateAsync", "Ns.MeetingService.CreateAsync"], ["DeleteAsync", "Ns.MeetingService.DeleteAsync"]],
        # _get_methods(IMeetingService)
        [["CreateAsync", "Ns.IMeetingService.CreateAsync"], ["GetAllAsync", "Ns.IMeetingService.GetAllAsync"]],
    ]
    MethodImplementsIndexer(conn).index()
    # Only CreateAsync is shared — exactly one IMPLEMENTS edge written
    conn.execute.assert_called_once()
    cypher, params = conn.execute.call_args[0]
    assert "IMPLEMENTS" in cypher
    assert params["impl"] == "Ns.MeetingService.CreateAsync"
    assert params["iface"] == "Ns.IMeetingService.CreateAsync"


def test_index_writes_no_edges_when_no_pairs() -> None:
    conn = MagicMock()
    conn.query.side_effect = [[]]  # no impl pairs
    MethodImplementsIndexer(conn).index()
    conn.execute.assert_not_called()


def test_index_writes_no_edges_when_no_matching_methods() -> None:
    conn = MagicMock()
    conn.query.side_effect = [
        [["Ns.Svc", "Ns.ISvc"]],
        [["PrivateMethod", "Ns.Svc.PrivateMethod"]],   # not on interface
        [["PublicMethod", "Ns.ISvc.PublicMethod"]],     # not on impl
    ]
    MethodImplementsIndexer(conn).index()
    conn.execute.assert_not_called()


def test_index_writes_multiple_edges_for_multiple_pairs() -> None:
    conn = MagicMock()
    conn.query.side_effect = [
        # Two impl pairs
        [["Ns.Dog", "Ns.IAnimal"], ["Ns.Cat", "Ns.IAnimal"]],
        # Dog methods
        [["Speak", "Ns.Dog.Speak"]],
        # IAnimal methods
        [["Speak", "Ns.IAnimal.Speak"]],
        # Cat methods
        [["Speak", "Ns.Cat.Speak"]],
        # IAnimal methods (fetched again for Cat)
        [["Speak", "Ns.IAnimal.Speak"]],
    ]
    MethodImplementsIndexer(conn).index()
    assert conn.execute.call_count == 2
```

- [ ] **Step 2.2: Run tests to verify they fail**

```bash
pytest tests/unit/indexer/test_method_implements_indexer.py -v
```

Expected: `ModuleNotFoundError` — file does not exist yet.

- [ ] **Step 2.3: Create `method_implements_indexer.py`**

Create `src/synapse/indexer/method_implements_indexer.py`:

```python
import logging

from synapse.graph.connection import GraphConnection
from synapse.graph.edges import upsert_method_implements

log = logging.getLogger(__name__)


class MethodImplementsIndexer:
    """Post-structural phase that writes method-level IMPLEMENTS edges.

    Requires all class-level IMPLEMENTS edges and all Method nodes to exist in
    the graph. Run after Indexer.index_project's structural + base-type passes.
    No LSP is needed — operates entirely on the graph.
    """

    def __init__(self, conn: GraphConnection) -> None:
        self._conn = conn

    def index(self) -> None:
        pairs = self._get_impl_pairs()
        log.debug("MethodImplementsIndexer: %d impl/iface pairs", len(pairs))
        for impl_full_name, iface_full_name in pairs:
            impl_methods = self._get_methods(impl_full_name)
            iface_methods = self._get_methods(iface_full_name)
            for name in impl_methods.keys() & iface_methods.keys():
                upsert_method_implements(
                    self._conn,
                    impl_methods[name],
                    iface_methods[name],
                )

    def _get_impl_pairs(self) -> list[tuple[str, str]]:
        rows = self._conn.query(
            "MATCH (impl:Class)-[:IMPLEMENTS]->(iface) "
            "RETURN impl.full_name, iface.full_name"
        )
        return [(r[0], r[1]) for r in rows if r[0] and r[1]]

    def _get_methods(self, class_full_name: str) -> dict[str, str]:
        """Return {short_name: full_name} for all Method nodes contained by class_full_name."""
        rows = self._conn.query(
            "MATCH (n {full_name: $full_name})-[:CONTAINS]->(m:Method) "
            "RETURN m.name, m.full_name",
            {"full_name": class_full_name},
        )
        return {r[0]: r[1] for r in rows if r[0] and r[1]}
```

- [ ] **Step 2.4: Run tests to verify they pass**

```bash
pytest tests/unit/indexer/test_method_implements_indexer.py -v
```

Expected: All 4 pass.

- [ ] **Step 2.5: Commit**

```bash
git add src/synapse/indexer/method_implements_indexer.py \
        tests/unit/indexer/test_method_implements_indexer.py
git commit -m "feat: add MethodImplementsIndexer (Phase 1.5)

Writes method-level IMPLEMENTS edges by matching method names across
each (impl:Class)-[:IMPLEMENTS]->(iface) pair. Fixes the root cause
behind find_callers, trace_call_chain, find_entry_points,
analyze_change_impact.transitive_callers, and find_interface_contract
all returning empty results for interface-dispatched calls.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 3: Wire Phase 1.5 into `Indexer` and `SynapseService`

**Files:**
- Modify: `src/synapse/indexer/indexer.py:32-81` (index_project)
- Modify: `src/synapse/service.py`

- [ ] **Step 3.1: Write failing tests for wiring**

Add to `tests/unit/indexer/test_structural_pass.py` (or a new `tests/unit/indexer/test_indexer_wiring.py` if the structural test file is very large):

```python
from unittest.mock import MagicMock, patch

from synapse.indexer.indexer import Indexer


def test_index_project_calls_method_implements_indexer() -> None:
    """Phase 1.5 must run after structural pass completes."""
    conn = MagicMock()
    lsp = MagicMock()
    lsp.get_workspace_files.return_value = []

    with patch("synapse.indexer.indexer.MethodImplementsIndexer") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        Indexer(conn, lsp).index_project("/proj", "csharp")

    mock_instance.index.assert_called_once()
```

Add to `tests/unit/test_service.py`:

```python
from unittest.mock import MagicMock, patch


def test_index_method_implements_calls_indexer() -> None:
    """SynapseService.index_method_implements must delegate to MethodImplementsIndexer."""
    svc = _service()
    with patch("synapse.service.MethodImplementsIndexer") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        svc.index_method_implements()

    mock_cls.assert_called_once_with(svc._conn)
    mock_instance.index.assert_called_once()
```

Check `tests/unit/test_service.py` for the `_service()` helper — use the same pattern to construct the service under test.

- [ ] **Step 3.2: Run tests to verify they fail**

```bash
pytest tests/unit/indexer/test_structural_pass.py::test_index_project_calls_method_implements_indexer \
       tests/unit/test_service.py::test_index_method_implements_calls_indexer -v
```

Expected: FAIL — `MethodImplementsIndexer` not imported yet, `index_method_implements` does not exist.

- [ ] **Step 3.3: Wire into `Indexer.index_project`**

In `src/synapse/indexer/indexer.py`, add the import at the top of the file (with other indexer imports):

```python
from synapse.indexer.method_implements_indexer import MethodImplementsIndexer
```

In `Indexer.index_project`, add Phase 1.5 after the base type extraction loop and before `SymbolResolver`. The insertion point is after the second `for file_path in files:` loop (base types) and before the `_CLASS_KINDS` assignment. The resulting block looks like:

```python
        # Phase 1.5: method-level IMPLEMENTS edges (requires all class-level IMPLEMENTS to exist)
        MethodImplementsIndexer(self._conn).index()

        # CALLS and REFERENCES resolution requires all nodes to be present; must run after structural pass
        _CLASS_KINDS = {SymbolKind.CLASS, SymbolKind.ABSTRACT_CLASS, SymbolKind.INTERFACE}
```

- [ ] **Step 3.4: Add `index_method_implements` to `SynapseService`**

In `src/synapse/service.py`, add after `index_calls`. Also add the top-level import:

```python
from synapse.indexer.method_implements_indexer import MethodImplementsIndexer
```

Then the method:

```python
    def index_method_implements(self) -> None:
        """Write method-level IMPLEMENTS edges for all indexed class-level IMPLEMENTS relationships.

        Can be run standalone after a structural index pass to populate interface dispatch edges
        without re-indexing the full project.
        """
        MethodImplementsIndexer(self._conn).index()
```

- [ ] **Step 3.5: Run tests to verify they pass**

```bash
pytest tests/unit/indexer/test_structural_pass.py::test_index_project_calls_method_implements_indexer \
       tests/unit/test_service.py::test_index_method_implements_calls_indexer -v
```

Expected: Both PASS.

- [ ] **Step 3.6: Run full unit suite**

```bash
pytest tests/unit/ -v --tb=short
```

Expected: All tests pass.

- [ ] **Step 3.7: Commit**

```bash
git add src/synapse/indexer/indexer.py src/synapse/service.py
git commit -m "feat: wire MethodImplementsIndexer as Phase 1.5 in Indexer and SynapseService

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Chunk 2: Traversal & Analysis Query Fixes

### Task 4: Fix `trace_call_chain` and `find_entry_points` end conditions

**Files:**
- Modify: `src/synapse/graph/traversal.py:15-38` (trace_call_chain), `:41-65` (find_entry_points)
- Test: `tests/unit/graph/test_traversal.py`

- [ ] **Step 4.1: Write failing tests**

Add to `tests/unit/graph/test_traversal.py`:

```python
def test_trace_call_chain_query_includes_interface_dispatch() -> None:
    """Query must find paths that end at an interface method implemented by $end."""
    conn = _conn([])
    trace_call_chain(conn, "A.Controller.Create", "A.Service.CreateAsync")
    cypher = conn.query.call_args[0][0]
    assert "IMPLEMENTS" in cypher, (
        "trace_call_chain must accept paths ending at an interface method "
        "that $end implements, to support controller→interface→service paths"
    )


def test_find_entry_points_query_includes_interface_dispatch() -> None:
    """Query must find entry points that reach $method via its interface."""
    conn = _conn([])
    find_entry_points(conn, "A.Service.CreateAsync")
    cypher = conn.query.call_args[0][0]
    assert "IMPLEMENTS" in cypher, (
        "find_entry_points must accept paths ending at an interface method "
        "that $method implements"
    )
```

- [ ] **Step 4.2: Run tests to verify they fail**

```bash
pytest tests/unit/graph/test_traversal.py::test_trace_call_chain_query_includes_interface_dispatch \
       tests/unit/graph/test_traversal.py::test_find_entry_points_query_includes_interface_dispatch -v
```

Expected: FAIL — `"IMPLEMENTS" not in cypher`.

- [ ] **Step 4.3: Update `trace_call_chain` in `traversal.py`**

Replace the `rows = conn.query(...)` block inside `trace_call_chain` (lines 25-33):

```python
    rows = conn.query(
        f"MATCH p=(s:Method)-[:CALLS*1..{depth}]->(e:Method) "
        "WHERE s.full_name = $start "
        "AND (e.full_name = $end OR (:Method {full_name: $end})-[:IMPLEMENTS]->(e)) "
        "RETURN [n in nodes(p) | n.full_name] AS path "
        "LIMIT 10",
        {"start": start, "end": end},
    )
```

- [ ] **Step 4.4: Update `find_entry_points` in `traversal.py`**

Replace the `rows = conn.query(...)` block inside `find_entry_points` (lines 52-59):

```python
    rows = conn.query(
        f"MATCH p=(entry:Method)-[:CALLS*1..{depth}]->(m:Method) "
        "WHERE NOT ()-[:CALLS]->(entry) "
        "AND (m.full_name = $method OR (:Method {full_name: $method})-[:IMPLEMENTS]->(m)) "
        "RETURN [n in nodes(p) | n.full_name] AS path "
        "LIMIT 20",
        {"method": method},
    )
```

- [ ] **Step 4.5: Run tests to verify new tests pass**

```bash
pytest tests/unit/graph/test_traversal.py -v
```

Expected: All pass including the two new ones.

- [ ] **Step 4.6: Commit**

```bash
git add src/synapse/graph/traversal.py tests/unit/graph/test_traversal.py
git commit -m "fix: expand end-node condition in trace_call_chain and find_entry_points

Paths from controllers to services pass through an interface method node
via DI dispatch. The end condition now also accepts nodes that are
implemented by the target method, allowing paths to be found even when
the final hop is controller→IMeetingService rather than controller→MeetingService.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 5: Fix `find_interface_contract` — mandatory sibling MATCH

**Files:**
- Modify: `src/synapse/graph/analysis.py:47-79`
- Test: `tests/unit/graph/test_analysis.py`

- [ ] **Step 5.1: Write failing test**

Add to `tests/unit/graph/test_analysis.py`:

```python
def test_find_interface_contract_no_siblings() -> None:
    """Returns the interface and contract even when there are no other implementations."""
    conn = MagicMock()
    conn.query.side_effect = [
        # First query: finds interface and contract method
        [["Ns.IService", "Ns.IService.Do", "Ns.MyImpl"]],
        # Second query: no siblings
        [],
    ]
    result = find_interface_contract(conn, "Ns.MyImpl.Do")
    assert result["interface"] == "Ns.IService"
    assert result["contract_method"] == "Ns.IService.Do"
    assert result["sibling_implementations"] == []
```

- [ ] **Step 5.2: Run test to verify it fails**

```bash
pytest tests/unit/graph/test_analysis.py::test_find_interface_contract_no_siblings -v
```

Expected: FAIL — current single-query implementation returns `None` for `interface` when there are no siblings.

- [ ] **Step 5.3: Update existing `test_find_interface_contract_returns_siblings`**

The existing test uses `conn.query.return_value` (single call) but the new implementation uses two calls. Replace lines 51-59 in `tests/unit/graph/test_analysis.py`:

```python
def test_find_interface_contract_returns_siblings() -> None:
    conn = MagicMock()
    conn.query.side_effect = [
        # First query: contract found
        [["Ns.IService", "Ns.IService.Do", "Ns.MyImpl"]],
        # Second query: one sibling
        [["OtherImpl", "/proj/Other.cs"]],
    ]
    result = find_interface_contract(conn, "Ns.MyImpl.Do")
    assert result["method"] == "Ns.MyImpl.Do"
    assert result["interface"] == "Ns.IService"
    assert result["contract_method"] == "Ns.IService.Do"
    assert len(result["sibling_implementations"]) == 1
```

- [ ] **Step 5.4: Run tests to see current state**

```bash
pytest tests/unit/graph/test_analysis.py -v
```

Expected: `test_find_interface_contract_returns_siblings` now FAILS (we updated the mock but not the implementation yet), `test_find_interface_contract_no_siblings` also FAILS.

- [ ] **Step 5.5: Replace `find_interface_contract` in `analysis.py`**

Replace the full function body (lines 47-79):

```python
def find_interface_contract(conn: GraphConnection, method: str) -> dict:
    """Find the interface a method satisfies and all sibling implementations.

    The method parameter should be a resolved full_name. The simple method
    name is extracted by splitting on '.' and taking the last segment.
    """
    simple_name = method.rsplit(".", 1)[-1]
    rows = conn.query(
        "MATCH (impl:Class)-[:CONTAINS]->(m:Method) "
        "WHERE m.full_name = $full_name "
        "MATCH (impl)-[:IMPLEMENTS]->(i)-[:CONTAINS]->(contract:Method {name: $name}) "
        "RETURN i.full_name, contract.full_name, impl.full_name",
        {"name": simple_name, "full_name": method},
    )

    if not rows:
        return {
            "method": method,
            "interface": None,
            "contract_method": None,
            "sibling_implementations": [],
        }

    iface_full_name = rows[0][0]
    impl_class_full_name = rows[0][2]

    sibling_rows = conn.query(
        "MATCH (sibling:Class)-[:IMPLEMENTS]->(i {full_name: $iface}) "
        "WHERE sibling.full_name <> $impl_class "
        "RETURN sibling.name, sibling.file_path",
        {"iface": iface_full_name, "impl_class": impl_class_full_name},
    )

    return {
        "method": method,
        "interface": iface_full_name,
        "contract_method": rows[0][1],
        "sibling_implementations": [
            {"class_name": r[0], "file_path": r[1]} for r in sibling_rows
        ],
    }
```

- [ ] **Step 5.6: Run tests to verify all pass**

```bash
pytest tests/unit/graph/test_analysis.py -v
```

Expected: All pass including both `find_interface_contract` tests.

- [ ] **Step 5.7: Commit**

```bash
git add src/synapse/graph/analysis.py tests/unit/graph/test_analysis.py
git commit -m "fix: split find_interface_contract into two queries; fix sibling exclusion

The original single query used a mandatory MATCH for siblings, collapsing
results to zero rows when the class was the only implementation. Now uses
two queries: one for the contract (always required), one for siblings
(optional). Sibling exclusion uses sibling.full_name <> impl_class to
correctly exclude the implementing class itself.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 6: Fix `analyze_change_impact` transitive query

**Files:**
- Modify: `src/synapse/graph/analysis.py:10-44`
- Test: `tests/unit/graph/test_analysis.py`

- [ ] **Step 6.1: Write failing test**

Add to `tests/unit/graph/test_analysis.py`:

```python
def test_analyze_change_impact_transitive_includes_interface_dispatch() -> None:
    """Transitive query must cross the interface dispatch gap."""
    conn = MagicMock()
    conn.query.side_effect = [[], [], []]
    analyze_change_impact(conn, "Ns.Svc.Method")
    transitive_cypher = conn.query.call_args_list[1][0][0]
    assert "IMPLEMENTS" in transitive_cypher, (
        "Transitive callers query must accept callers that reach the method "
        "via its interface (IMPLEMENTS edge)"
    )
```

- [ ] **Step 6.2: Run test to verify it fails**

```bash
pytest tests/unit/graph/test_analysis.py::test_analyze_change_impact_transitive_includes_interface_dispatch -v
```

Expected: FAIL — `"IMPLEMENTS" not in transitive_cypher`.

- [ ] **Step 6.3: Update the transitive query in `analyze_change_impact`**

In `src/synapse/graph/analysis.py`, replace the `transitive` query block (lines 21-24):

```python
    transitive = conn.query(
        "MATCH (c:Method)-[:CALLS*2..4]->(m) "
        "WHERE m.full_name = $method OR (:Method {full_name: $method})-[:IMPLEMENTS]->(m) "
        "RETURN DISTINCT c.full_name, c.file_path",
        {"method": method},
    )
```

- [ ] **Step 6.4: Run tests to verify all pass**

```bash
pytest tests/unit/graph/test_analysis.py -v
```

Expected: All pass.

- [ ] **Step 6.5: Commit**

```bash
git add src/synapse/graph/analysis.py tests/unit/graph/test_analysis.py
git commit -m "fix: extend analyze_change_impact transitive query to cross interface dispatch

Transitive callers were always empty because the traversal terminated
at the interface method boundary. Now also matches methods that reach
the target via an IMPLEMENTS relationship (controller→IMeetingService
→MeetingService pattern).

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Chunk 3: Simple Standalone Bug Fixes

### Task 7: Fix `resolve_full_name` — prefer Class/Interface over Method

**Files:**
- Modify: `src/synapse/graph/lookups.py:248-271`
- Test: `tests/unit/graph/test_resolve.py`

- [ ] **Step 7.1: Write failing test**

Add to `tests/unit/graph/test_resolve.py`:

```python
def test_suffix_fallback_prefers_class_over_method() -> None:
    """When suffix matches both a Class and a Method, return the Class unambiguously."""
    conn = MagicMock()
    conn.query.side_effect = [
        [],  # exact match: nothing
        [   # suffix match: Class node + constructor Method node
            ["Ns.Services.MeetingService", ["Class"]],
            ["Ns.Services.MeetingService.MeetingService", ["Method"]],
        ],
    ]
    result = resolve_full_name(conn, "MeetingService")
    assert result == "Ns.Services.MeetingService", (
        "Should resolve to the Class node, not raise an ambiguity error"
    )
```

- [ ] **Step 7.2: Run test to verify it fails**

```bash
pytest tests/unit/graph/test_resolve.py::test_suffix_fallback_prefers_class_over_method -v
```

Expected: FAIL — current implementation returns `["Ns.Services.MeetingService", "Ns.Services.MeetingService.MeetingService"]` (a list, triggering ambiguity error).

- [ ] **Step 7.3: Update existing suffix-fallback tests**

The suffix query now returns 2-column rows `[full_name, labels]`. Update the three existing tests that mock the suffix query return value in `tests/unit/graph/test_resolve.py`:

```python
def test_suffix_fallback_single_match() -> None:
    conn = MagicMock()
    conn.query.side_effect = [[], [["Ns.Sub.MyClass", ["Class"]]]]
    result = resolve_full_name(conn, "MyClass")
    assert result == "Ns.Sub.MyClass"


def test_suffix_fallback_multiple_matches() -> None:
    conn = MagicMock()
    conn.query.side_effect = [[], [["A.MyClass", ["Class"]], ["B.MyClass", ["Class"]]]]
    result = resolve_full_name(conn, "MyClass")
    assert result == ["A.MyClass", "B.MyClass"]


def test_no_match_returns_original() -> None:
    conn = MagicMock()
    conn.query.side_effect = [[], []]
    result = resolve_full_name(conn, "NoSuchThing")
    assert result == "NoSuchThing"
```

- [ ] **Step 7.4: Run all resolve tests to see current state**

```bash
pytest tests/unit/graph/test_resolve.py -v
```

Expected: `test_suffix_fallback_single_match`, `test_suffix_fallback_multiple_matches`, `test_no_match_returns_original` now FAIL (mock shape changed), `test_suffix_fallback_prefers_class_over_method` also FAILS.

- [ ] **Step 7.5: Replace `resolve_full_name` in `lookups.py`**

Replace the full function body (lines 248-271):

```python
def resolve_full_name(conn: GraphConnection, name: str) -> str | list[str]:
    """Resolve a possibly-short symbol name to its full qualified name.

    Tries exact match first, then falls back to suffix matching.
    When suffix matching returns both Class/Interface and Method nodes for the
    same name (e.g. class + its constructor), Class/Interface nodes are preferred
    to avoid spurious ambiguity errors on short class names.
    Returns the original name unchanged if no match is found (lets
    downstream queries fail naturally with empty results).
    """
    rows = conn.query(
        "MATCH (n {full_name: $name}) RETURN n.full_name LIMIT 1",
        {"name": name},
    )
    if rows:
        return rows[0][0]

    rows = conn.query(
        "MATCH (n) WHERE n.full_name ENDS WITH $suffix "
        "RETURN n.full_name, labels(n)",
        {"suffix": "." + name},
    )
    if not rows:
        return name

    # Prefer Class/Interface nodes over Method nodes when disambiguating
    type_nodes = [r for r in rows if any(lbl in ("Class", "Interface") for lbl in r[1])]
    candidates = type_nodes if type_nodes else rows

    if len(candidates) == 1:
        return candidates[0][0]
    return [r[0] for r in candidates]
```

- [ ] **Step 7.6: Run tests to verify all pass**

```bash
pytest tests/unit/graph/test_resolve.py -v
```

Expected: All 6 pass.

- [ ] **Step 7.7: Commit**

```bash
git add src/synapse/graph/lookups.py tests/unit/graph/test_resolve.py
git commit -m "fix: prefer Class/Interface nodes in resolve_full_name suffix disambiguation

Short class names like 'MeetingService' matched both the class node and
its constructor method (same name suffix). The ambiguity error listed
both, looking like two classes to the user. Now filters to Class/Interface
nodes first before deciding ambiguity.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 8: Fix `analyze_change_impact` — direct callers includes test files

**Files:**
- Modify: `src/synapse/graph/analysis.py:10-44`
- Test: `tests/unit/graph/test_analysis.py`

- [ ] **Step 8.1: Write failing test**

Add to `tests/unit/graph/test_analysis.py`:

```python
def test_analyze_change_impact_direct_callers_excludes_tests() -> None:
    """direct_callers must not include test methods; test_coverage is the correct field."""
    conn = MagicMock()
    conn.query.side_effect = [[], [], []]
    analyze_change_impact(conn, "Ns.Svc.Method")
    direct_cypher = conn.query.call_args_list[0][0][0]
    assert "Tests" in direct_cypher and "NOT" in direct_cypher, (
        "direct_callers query must filter out test files"
    )
```

- [ ] **Step 8.2: Run test to verify it fails**

```bash
pytest tests/unit/graph/test_analysis.py::test_analyze_change_impact_direct_callers_excludes_tests -v
```

Expected: FAIL — `"Tests" not in direct_cypher`.

- [ ] **Step 8.3: Update the direct query in `analyze_change_impact`**

In `src/synapse/graph/analysis.py`, replace the `direct` query block (lines 15-19):

```python
    direct = conn.query(
        "MATCH (c:Method)-[:CALLS]->(m {full_name: $method}) "
        "WHERE NOT c.file_path CONTAINS 'Tests' "
        "RETURN c.full_name, c.file_path",
        {"method": method},
    )
```

- [ ] **Step 8.4: Run all analysis tests**

```bash
pytest tests/unit/graph/test_analysis.py -v
```

Expected: All pass.

- [ ] **Step 8.5: Commit**

```bash
git add src/synapse/graph/analysis.py tests/unit/graph/test_analysis.py
git commit -m "fix: exclude test files from analyze_change_impact direct_callers

direct_callers and test_coverage were returning identical lists because
direct_callers had no file_path filter. Production callers and test
coverage are now distinct fields.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 9: Fix `list_projects` — duplicate entry from trailing slash

**Files:**
- Modify: `src/synapse/graph/nodes.py:5-9`
- Test: `tests/unit/graph/test_nodes.py`

- [ ] **Step 9.1: Write failing test**

Add to `tests/unit/graph/test_nodes.py`:

```python
def test_upsert_repository_strips_trailing_slash() -> None:
    """Paths with and without trailing slash must produce the same node."""
    from synapse.graph.nodes import upsert_repository
    conn = MagicMock()
    upsert_repository(conn, "/Users/alex/Dev/myrepo/", "csharp")
    _, params = conn.execute.call_args[0]
    assert not params["path"].endswith("/"), (
        "Trailing slash must be stripped to prevent duplicate Repository nodes"
    )
    assert params["path"] == "/Users/alex/Dev/myrepo"
```

- [ ] **Step 9.2: Run test to verify it fails**

```bash
pytest tests/unit/graph/test_nodes.py::test_upsert_repository_strips_trailing_slash -v
```

Expected: FAIL — current implementation stores the path verbatim.

- [ ] **Step 9.3: Update `upsert_repository` in `nodes.py`**

Replace the function body (lines 5-9):

```python
def upsert_repository(conn: GraphConnection, path: str, language: str) -> None:
    path = path.rstrip("/")
    conn.execute(
        "MERGE (n:Repository {path: $path}) SET n.language = $language, n.last_indexed = $ts",
        {"path": path, "language": language, "ts": _now()},
    )
```

- [ ] **Step 9.4: Run test to verify it passes**

```bash
pytest tests/unit/graph/test_nodes.py::test_upsert_repository_strips_trailing_slash -v
```

Expected: PASS.

- [ ] **Step 9.5: Run full unit suite**

```bash
pytest tests/unit/ -v --tb=short
```

Expected: All tests pass.

- [ ] **Step 9.6: Commit**

```bash
git add src/synapse/graph/nodes.py tests/unit/graph/test_nodes.py
git commit -m "fix: strip trailing slash in upsert_repository to prevent duplicate entries

Indexing the same repo twice — once with and once without a trailing slash —
produced two distinct Repository nodes. Normalising the path on write
ensures MERGE matches the existing node in both cases.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Final Verification

- [ ] **Run the full unit suite one last time**

```bash
cd /Users/alex/Dev/mcpcontext && source .venv/bin/activate
pytest tests/unit/ -v --tb=short
```

Expected: All tests pass (153 baseline + ~15 new).
