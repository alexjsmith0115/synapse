# Gap Report Bug Fixes — Design Spec
**Date:** 2026-03-12
**Source:** `docs/2026-03-12_gap_report.md`
**Scope:** Four bug clusters from the real-world test against the `oneonone` backend.

---

## Out of Scope

- Bug #6: REFERENCES edge coverage gaps — deferred
- Bugs #9, #10, #15, #16: Description/UX housekeeping — separate pass
- Improvements #12, #13: `get_context_for` token cost, `summarize_from_graph` auto-persist — separate pass

---

## Bug 1, 2, 3, 4, 11, 14 — Missing Method-Level IMPLEMENTS Edges

### Root Cause

The structural indexer writes class-level `(impl:Class)-[:IMPLEMENTS]->(iface)` edges but never writes method-level `(impl_method:Method)-[:IMPLEMENTS]->(iface_method:Method)` edges. All six bugs are downstream of this single gap:

| Bug | Symptom |
|-----|---------|
| #1 `find_callers` | via-interface query finds no edges to traverse |
| #2 `find_interface_contract` | Sibling MATCH collapses when only one implementation exists (separate query bug — see below) |
| #3 `trace_call_chain` | Cannot cross controller → service dispatch gap |
| #4 `find_entry_points` | Controller entry point not reachable |
| #11 `analyze_change_impact.transitive_callers` | Transitive traversal terminates at the interface boundary |
| #14 `summarize_from_graph.dependents` | Dependent traversal cannot cross interface boundary |

### Fix: Phase 1.5 — `MethodImplementsIndexer`

A new indexing phase runs after the structural pass completes (all class-level IMPLEMENTS edges exist) and before Phase 2 call indexing. This mirrors the existing `CallIndexer` pattern.

**New file:** `src/synapse/indexer/method_implements_indexer.py`

```
class MethodImplementsIndexer:
    def __init__(self, conn: GraphConnection) -> None: ...
    def index(self) -> None: ...
    def _get_impl_pairs(self) -> list[tuple[str, str]]: ...
    def _get_methods(self, class_full_name: str) -> dict[str, str]: ...  # name → full_name
```

**Algorithm:**

1. `_get_impl_pairs`: query all `(impl:Class)-[:IMPLEMENTS]->(iface) RETURN impl.full_name, iface.full_name`
2. For each pair, call `_get_methods` on both to get `{short_name: full_name}` maps
3. For each `name` present in both maps, call `upsert_method_implements(conn, impl_method_full_name, iface_method_full_name)`
4. Match by short `name` only (not signature — interface and concrete method names always agree; signature may diverge in parameter names from Roslyn's LSP output)

**New edge function in `edges.py`:**

```python
def upsert_method_implements(conn, impl_method: str, iface_method: str) -> None:
    conn.execute(
        "MATCH (impl:Method {full_name: $impl}), (iface:Method {full_name: $iface}) "
        "MERGE (impl)-[:IMPLEMENTS]->(iface)",
        {"impl": impl_method, "iface": iface_method},
    )
```

**Wiring in `indexer.py`:** After the structural pass loop completes, instantiate `MethodImplementsIndexer(self._conn).index()` before handing off to `CallIndexer`.

**Wiring in `service.py`:** Expose `index_method_implements()` on `SynapseService` for standalone re-runs (same pattern as `index_calls()`).

### Query Changes Required

**`find_callers` (lookups.py):** The existing `via_iface` query is logically correct — it will work once the edges exist. No query change needed.

**`trace_call_chain` (traversal.py):** The `end` parameter refers to the concrete method. Controllers call the *interface* method via DI. With IMPLEMENTS edges, the path terminates at the interface method node, not the concrete one. Expand the end condition:

```cypher
MATCH p=(s:Method)-[:CALLS*1..{depth}]->(e:Method)
WHERE s.full_name = $start
  AND (e.full_name = $end OR (:Method {full_name: $end})-[:IMPLEMENTS]->(e))
RETURN [n in nodes(p) | n.full_name] AS path
LIMIT 10
```

**`find_entry_points` (traversal.py):** Same pattern — target may be reached via its interface method:

```cypher
MATCH p=(entry:Method)-[:CALLS*1..{depth}]->(m:Method)
WHERE NOT ()-[:CALLS]->(entry)
  AND (m.full_name = $method OR (:Method {full_name: $method})-[:IMPLEMENTS]->(m))
RETURN [n in nodes(p) | n.full_name] AS path
LIMIT 20
```

**`analyze_change_impact` (analysis.py):** Transitive query follows the same pattern — also accept nodes that implement the target:

```cypher
MATCH (c:Method)-[:CALLS*2..4]->(m)
WHERE m.full_name = $method OR (:Method {full_name: $method})-[:IMPLEMENTS]->(m)
RETURN DISTINCT c.full_name, c.file_path
```

### `find_interface_contract` — Separate Query Bug (#2)

The current query requires at least one sibling via a mandatory `MATCH (sibling:Class)-[:IMPLEMENTS]->(i)`. When `MeetingService` is the only implementation of `IMeetingService`, this collapses the result to zero rows. Fix: use `OPTIONAL MATCH` for siblings and collect separately:

```python
# Find interface and contract method
rows = conn.query(
    "MATCH (impl:Class)-[:CONTAINS]->(m:Method) "
    "WHERE m.full_name = $full_name "
    "MATCH (impl)-[:IMPLEMENTS]->(i)-[:CONTAINS]->(contract:Method {name: $name}) "
    "RETURN i.full_name, contract.full_name, impl.full_name",
    {"name": simple_name, "full_name": method},
)
if not rows:
    return {"method": method, "interface": None, "contract_method": None, "sibling_implementations": []}

iface_full_name = rows[0][0]

# Siblings are optional — also return impl class full_name from first query for exclusion
# First query updated to also return impl.full_name:
#   RETURN i.full_name, contract.full_name, impl.full_name
impl_class_full_name = rows[0][2]

sibling_rows = conn.query(
    "MATCH (sibling:Class)-[:IMPLEMENTS]->(i {full_name: $iface}) "
    "WHERE sibling.full_name <> $impl_class "
    "RETURN sibling.name, sibling.file_path",
    {"iface": iface_full_name, "impl_class": impl_class_full_name},
)
```

---

## Bug 5 — `get_hierarchy` Ambiguity on Short Class Names

### Root Cause

`resolve_full_name` suffix-matches `".MeetingService"` and finds two nodes:
- `OneOnOne.API.Services.MeetingService` (Class)
- `OneOnOne.API.Services.MeetingService.MeetingService` (Method — the constructor)

Both match the `.MeetingService` suffix. The list of ambiguous matches is returned and `_resolve` raises a `ValueError` that lists both, which looks like two classes to the user.

### Fix

In `resolve_full_name`, when suffix matching returns multiple results, filter to prefer `:Class` or `:Interface` nodes over `:Method` nodes before deciding ambiguity:

```python
rows = conn.query(
    "MATCH (n) WHERE n.full_name ENDS WITH $suffix "
    "RETURN n.full_name, labels(n)",
    {"suffix": "." + name},
)
# Prefer Class/Interface over Method
type_nodes = [r for r in rows if any(l in ("Class", "Interface") for l in r[1])]
candidates = type_nodes if type_nodes else rows
if len(candidates) == 1:
    return candidates[0][0]
if len(candidates) > 1:
    return [r[0] for r in candidates]
return name
```

This resolves `"MeetingService"` to `OneOnOne.API.Services.MeetingService` unambiguously, while still surfacing a real ambiguity error when two *classes* share a short name.

**Files:** `src/synapse/graph/lookups.py`

---

## Bug 7 — `analyze_change_impact` Identical `direct_callers` and `test_coverage`

### Root Cause

The `direct` query has no filter on file path — it returns all callers including test methods. The `tests` query filters to `file_path CONTAINS 'Tests'`. When all callers are test methods (as with `CreateMeetingAsync` in the gap report), both lists are identical.

### Fix

Add `AND NOT c.file_path CONTAINS 'Tests'` to the direct callers query:

```python
direct = conn.query(
    "MATCH (c:Method)-[:CALLS]->(m {full_name: $method}) "
    "WHERE NOT c.file_path CONTAINS 'Tests' "
    "RETURN c.full_name, c.file_path",
    {"method": method},
)
```

**Files:** `src/synapse/graph/analysis.py`

---

## Bug 8 — `list_projects` Duplicate Entry

### Root Cause

`upsert_repository` uses `MERGE (n:Repository {path: $path})`. Indexing the same project twice — once as `/path/to/repo` and once as `/path/to/repo/` — creates two Repository nodes.

### Fix

Strip trailing slash from `path` before passing to `upsert_repository`:

```python
def upsert_repository(conn: GraphConnection, path: str, language: str) -> None:
    path = path.rstrip("/")
    conn.execute(
        "MERGE (n:Repository {path: $path}) SET n.language = $language, n.last_indexed = $ts",
        {"path": path, "language": language, "ts": _now()},
    )
```

**Files:** `src/synapse/graph/nodes.py`

---

## Files Affected

| File | Change |
|------|--------|
| `src/synapse/indexer/method_implements_indexer.py` | New class |
| `src/synapse/graph/edges.py` | Add `upsert_method_implements` |
| `src/synapse/indexer/indexer.py` | Wire Phase 1.5 |
| `src/synapse/service.py` | Expose `index_method_implements()` |
| `src/synapse/graph/traversal.py` | Update `trace_call_chain`, `find_entry_points` end conditions |
| `src/synapse/graph/analysis.py` | Fix `analyze_change_impact` direct filter and transitive query; fix `find_interface_contract` sibling query |
| `src/synapse/graph/lookups.py` | Fix `resolve_full_name` disambiguation |
| `src/synapse/graph/nodes.py` | Strip trailing slash in `upsert_repository` |

## Test Coverage

Each fix gets a unit test:
- `MethodImplementsIndexer`: mock conn returning two impl pairs, verify `upsert_method_implements` calls
- `resolve_full_name`: returns Class node when Class + Method share suffix
- `analyze_change_impact`: `direct_callers` excludes test files
- `analyze_change_impact`: `transitive_callers` includes callers that reach the target via interface dispatch
- `find_interface_contract`: returns result when no siblings exist
- `upsert_repository`: trailing slash stripped from stored path
- `trace_call_chain` / `find_entry_points`: query includes interface dispatch condition
