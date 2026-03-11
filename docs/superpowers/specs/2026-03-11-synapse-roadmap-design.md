# Synapse Roadmap Implementation Design

**Date:** 2026-03-11
**Scope:** Full roadmap from `docs/plans/synapse-roadmap.md`, phased as quick wins then by priority.
**Prerequisite:** All 4 bug fixes from `tool-bug-remediation.md` are already implemented.

---

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Tool granularity | Dedicated named tools for multi-hop and impact analysis; one parameterized `audit_architecture(rule)` for policy queries | Named tools are self-documenting for agents. Architectural rules are opinionated/project-specific — one tool with an enum keeps count down |
| Staleness scope | Metadata + warnings only (no dependent re-indexing) | Ships the trust-building feature first. Dependent re-indexing adds complexity (cycles, depth limits, LSP lifetime) — layer on later |
| Summary scope | Auto-surface in `get_context_for` + `summarize_from_graph` | Activates existing data. Tiers and `annotate` add schema complexity for unproven value |
| Short-name resolution | All read tools via shared `resolve_full_name` helper. Write tools (`set_summary`) require full name | Agents shouldn't need full namespaces to explore. Writes need precision |
| Return format | Structured data (dicts/lists) | Agent-optimized. Agents can format; they can't un-format markdown |
| Query layer organization | Rename `queries.py` → `lookups.py`; new `traversal.py` and `analysis.py` | Domain-split keeps each file focused. Service/tool layers are thin enough to stay as-is |

---

## Phasing

### Phase 0 — Foundations

Unblocks all subsequent phases.

**0.1 Rename `graph/queries.py` → `graph/lookups.py`**

Pure rename. Update all imports: `service.py`, `cli/app.py`, test files, `__init__.py` if applicable. No logic changes.

**0.2 Add `resolve_full_name` helper**

New function in `graph/lookups.py`:

```python
def resolve_full_name(conn: GraphConnection, name: str) -> str | list[str]:
```

Logic:
1. If `name` contains a `.`, try exact match: `MATCH (n {full_name: $name}) RETURN n.full_name LIMIT 1`
2. If no exact match (or `name` has no `.`), suffix match: `MATCH (n) WHERE n.full_name ENDS WITH $suffix RETURN n.full_name` where `suffix = "." + name`
3. Exactly one result → return the string
4. Multiple results → return the list (caller surfaces "did you mean?")
5. No results → return original `name` unchanged (let downstream queries fail naturally with empty results)

**0.3 Wire into service layer**

`SynapseService` gets a private `_resolve(name)` method that calls `resolve_full_name`. Each read method calls `self._resolve(full_name)` before delegating to the query function. This keeps resolution out of both the query layer (queries always receive resolved full names) and the tool layer (tools don't know about resolution).

Excluded from resolution: `set_summary` (write operation — ambiguity is dangerous).

---

### Phase 1 — Quick Wins

**1.1 Auto-surface summaries in `get_context_for`**

After assembling existing sections (source, containing type, interfaces, callees, dependencies), query for summaries on:
- The symbol itself
- Its containing class/interface (if symbol is a method/property/field)
- Its implemented interfaces (if symbol is a class)

Add a `summaries` key to the returned dict: `[{full_name, summary}]`. Only included when summaries exist.

Service-layer change only. No new queries — `get_summary` in `lookups.py` already works.

**1.2 Staleness metadata**

**Storage:** Add `last_indexed: float` property (Unix timestamp) to `:File` nodes. Set during indexing in `indexer.py` when upserting File nodes via `nodes.upsert_file`.

**Detection:** New function in `lookups.py`:

```python
def check_staleness(conn: GraphConnection, file_path: str) -> dict | None:
```

Returns `{file_path, last_indexed, last_modified, is_stale}` by comparing stored `last_indexed` against `os.path.getmtime(file_path)`. Returns `None` if file isn't in graph.

**Surfacing:** In the service layer, tools that return symbol data append a `_staleness_warning: str` field when the queried symbol's file is stale:
> "Warning: {file_path} was modified after last indexing. Results may be outdated. Run watch_project or re-index to refresh."

Only the queried symbol's file is checked — not every result's file.

**Documentation (in code):** A comment on `check_staleness` explaining the tradeoff:
> This checks only the queried symbol's file. Dependent files (files that IMPORT this one) may also be stale if the queried file's exports changed. Full dependent re-indexing is a future enhancement — see docs/plans/synapse-roadmap.md section 4. The watcher would need to: (1) query IMPORTS edges to find dependents, (2) re-index those files, (3) handle cycles and depth limits. The current approach prioritizes fast, local staleness detection over transitive correctness.

---

### Phase 2 — Multi-Hop Call Chain Tools

New file: `graph/traversal.py`. Three new tools.

**Note on FalkorDB parameterized depth:** FalkorDB may not support `$depth` as a variable-length relationship bound in `[:CALLS*1..$depth]`. If not, the depth integer is inlined into the Cypher string after validation (must be `int`, clamped 1-10). This is the same pattern `find_dependencies` already uses.

**2.1 `trace_call_chain(start, end, max_depth=6)`**

Find all call paths between two methods.

```cypher
MATCH p=(s:Method)-[:CALLS*1..$depth]->(e:Method)
WHERE s.full_name = $start AND e.full_name = $end
RETURN [n in nodes(p) | n.full_name] AS path
LIMIT 10
```

Returns:
```python
{"paths": [[str]], "start": str, "end": str, "max_depth": int}
```

Each path is a list of full names from start to end. Capped at 10 paths. Both `start` and `end` go through `resolve_full_name`.

**2.2 `find_entry_points(method, max_depth=8)`**

Walk backwards to find all root callers — methods with no incoming CALLS edges.

```cypher
MATCH p=(entry:Method)-[:CALLS*1..$depth]->(target:Method {full_name: $method})
WHERE NOT ()-[:CALLS]->(entry)
RETURN [n in nodes(p) | n.full_name] AS path
LIMIT 20
```

Returns:
```python
{"entry_points": [{"entry": str, "path": [str]}], "target": str, "max_depth": int}
```

**2.3 `get_call_depth(method, depth)`**

Recursive fanout — all methods reachable from a starting method up to N levels.

```cypher
MATCH p=(m:Method {full_name: $method})-[:CALLS*1..$depth]->(callee:Method)
RETURN DISTINCT callee.full_name, callee.file_path, length(p) AS depth
ORDER BY depth
```

Returns:
```python
{"root": str, "callees": [{"full_name": str, "file_path": str, "depth": int}], "depth_limit": int}
```

---

### Phase 3 — Impact Analysis Tools

New file: `graph/analysis.py`. Three new tools.

**3.1 `analyze_change_impact(method)`**

Structured report: "If I change this method, what breaks?"

Composes three queries:
1. Direct callers: `MATCH (c:Method)-[:CALLS]->(m {full_name: $method}) RETURN c.full_name, c.file_path`
2. Transitive callers (2-4 hops): `MATCH (c:Method)-[:CALLS*2..4]->(m {full_name: $method}) RETURN DISTINCT c.full_name, c.file_path`
3. Test coverage: `MATCH (t:Method)-[:CALLS*1..4]->(m {full_name: $method}) WHERE t.file_path CONTAINS 'Tests' RETURN DISTINCT t.full_name, t.file_path`

Returns:
```python
{
    "target": str,
    "direct_callers": [{"full_name": str, "file_path": str}],
    "transitive_callers": [{"full_name": str, "file_path": str}],
    "test_coverage": [{"full_name": str, "file_path": str}],
    "total_affected": int  # deduplicated count across all three
}
```

**3.2 `find_interface_contract(method)`**

Given an implementation method, find the interface contract and sibling implementations.

```cypher
MATCH (impl:Class)-[:CONTAINS]->(m:Method {name: $name})
MATCH (impl)-[:IMPLEMENTS]->(i)-[:CONTAINS]->(contract:Method {name: $name})
MATCH (sibling:Class)-[:IMPLEMENTS]->(i)
WHERE sibling <> impl
RETURN i.full_name AS interface, contract.full_name AS contract_method,
       sibling.name AS sibling_class, sibling.file_path
```

Note: matches on simple `name`, not `full_name`, because interface contract and implementation have different full names. The `method` parameter goes through `resolve_full_name` to find the target, then extracts the simple name for the contract match.

Returns:
```python
{
    "method": str,
    "interface": str,
    "contract_method": str,
    "sibling_implementations": [{"class_name": str, "file_path": str}]
}
```

**3.3 `find_type_impact(type)`**

If a model/DTO changes shape, what code is affected?

```cypher
MATCH (m:Method)-[:REFERENCES]->(t {full_name: $type})
RETURN m.full_name, m.file_path,
  CASE WHEN m.file_path CONTAINS 'Tests' THEN 'test' ELSE 'prod' END AS context
```

Returns:
```python
{
    "type": str,
    "references": [{"full_name": str, "file_path": str, "context": str}],
    "prod_count": int,
    "test_count": int
}
```

---

### Phase 4 — Architectural Audit

One tool in `graph/analysis.py`.

**4.1 `audit_architecture(rule)`**

`rule` is a string enum. Invalid values return the list of valid rules.

**Rules:**

**`layering_violations`** — controllers bypassing service layer:
```cypher
MATCH (ctrl:Class)-[:CONTAINS]->(m:Method)-[:CALLS]->(db:Method)
WHERE ctrl.file_path CONTAINS 'Controllers'
  AND db.full_name CONTAINS 'DbContext'
RETURN ctrl.name, m.name, db.full_name
```

**`untested_services`** — service classes with no test coverage:
```cypher
MATCH (svc:Class)-[:IMPLEMENTS]->(i)
WHERE svc.file_path CONTAINS '/Services/'
  AND NOT EXISTS {
    MATCH (t:Method)-[:CALLS*1..3]->(:Method)<-[:CONTAINS]-(svc)
    WHERE t.file_path CONTAINS 'Tests'
  }
RETURN svc.name, svc.file_path
```

**`repeated_db_writes`** — methods calling SaveChangesAsync multiple times:
```cypher
MATCH (m:Method)-[:CALLS]->(save:Method)
WHERE save.name = 'SaveChangesAsync'
WITH m, count(save) AS save_count
WHERE save_count > 1
RETURN m.full_name, save_count ORDER BY save_count DESC
```

Returns (all rules):
```python
{
    "rule": str,
    "description": str,  # human-readable explanation of what the rule checks
    "violations": [dict],  # shape varies by rule
    "count": int
}
```

Each rule is a function in `analysis.py` that takes `conn` and returns `list[dict]`. The service method dispatches by rule name.

**These queries are C#/.NET-specific.** A code comment will note this: if Synapse later supports other languages, these rules need language-aware variants or should be skipped for non-C# projects.

---

### Phase 5 — Summary Generation

Service-layer method (not a query-layer function — it orchestrates multiple queries).

**5.1 `summarize_from_graph(class_name)`**

Assembles from existing queries:
1. Class metadata: name, kind, file_path, interfaces (from `lookups.py`)
2. Method count (from `lookups.py` — `get_members_overview`)
3. Dependencies: field-type REFERENCES (from `lookups.py` — `find_dependencies`)
4. Dependents: classes that reference or call into it (from `analysis.py` — reuses `find_type_impact` logic)
5. Test coverage: test methods calling into any of its methods (from `analysis.py`)

Returns:
```python
{
    "full_name": str,
    "summary": str,
    "data": {
        "kind": str,
        "interfaces": [str],
        "method_count": int,
        "dependencies": [str],
        "dependents": [str],
        "test_classes": [str]
    }
}
```

Generated summary format (example):
```
MeetingService: implements IMeetingService (10 methods).
Dependencies: ApplicationDbContext, IRecurringCadenceService, ICalendarEventService.
Depended on by: MeetingsController (5 methods), 7 test classes.
Has 2 methods calling SaveChangesAsync multiple times (CreateMeetingAsync, UpsertMeetingNoteAsync).
```

The summary is returned but **not stored automatically**. The agent reviews it and calls `set_summary` to persist if it looks right. This avoids polluting the graph with auto-generated summaries that might be wrong.

---

## New Files

| File | Purpose |
|------|---------|
| `src/synapse/graph/traversal.py` | Multi-hop call chain queries (Phase 2) |
| `src/synapse/graph/analysis.py` | Impact analysis + architectural audit queries (Phases 3-4) |
| `tests/unit/graph/test_traversal.py` | Unit tests for traversal queries |
| `tests/unit/graph/test_analysis.py` | Unit tests for analysis queries |

## Modified Files

| File | Changes |
|------|---------|
| `src/synapse/graph/queries.py` | Renamed to `lookups.py` |
| `src/synapse/graph/lookups.py` | Add `resolve_full_name`, `check_staleness` |
| `src/synapse/graph/nodes.py` | Add `last_indexed` to `upsert_file` |
| `src/synapse/indexer/indexer.py` | Pass `last_indexed=time.time()` when upserting File nodes |
| `src/synapse/service.py` | Add `_resolve` helper; wire resolution into read methods; add staleness checks; add new tool methods; update `get_context_for` for summaries |
| `src/synapse/mcp/tools.py` | Register 7 new tools: `trace_call_chain`, `find_entry_points`, `get_call_depth`, `analyze_change_impact`, `find_interface_contract`, `find_type_impact`, `audit_architecture`, `summarize_from_graph` |
| `src/synapse/cli/app.py` | Add CLI commands for new tools |
| All files importing `graph.queries` | Update import to `graph.lookups` |

## New Tool Count

Current: 20 tools. After: 28 tools (+8).

| Tool | Phase | Category |
|------|-------|----------|
| `trace_call_chain` | 2 | Multi-hop |
| `find_entry_points` | 2 | Multi-hop |
| `get_call_depth` | 2 | Multi-hop |
| `analyze_change_impact` | 3 | Impact |
| `find_interface_contract` | 3 | Impact |
| `find_type_impact` | 3 | Impact |
| `audit_architecture` | 4 | Architectural |
| `summarize_from_graph` | 5 | Summary |
