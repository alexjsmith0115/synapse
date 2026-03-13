# Design: FalkorDB → Memgraph Migration

**Date:** 2026-03-13
**Status:** Approved

## Motivation

FalkorDB does not support the `=~` Cypher regex operator, which is needed for pattern-based filtering (e.g. excluding test-path callers). Memgraph is a drop-in graph database that supports full Cypher including `=~`, speaks the Bolt protocol, and is compatible with the `neo4j` Python driver — the same driver that also supports Neo4j, enabling future backend flexibility.

---

## Architecture

Single `GraphConnection` class with internals swapped from the FalkorDB client to the `neo4j` Python Bolt driver. No backend abstraction is introduced at the connection layer — both Memgraph and Neo4j use the same driver and the same Cypher dialect. The only backend-specific surface is index creation syntax in `schema.py`, addressed via a `dialect` parameter.

---

## Component Changes

### `connection.py`

Replace the FalkorDB client with `neo4j.GraphDatabase.driver()`.

- **Protocol/port:** Bolt on port 7687 (was Redis on 6379)
- **Connection:** `GraphDatabase.driver("bolt://host:port", auth=("", ""))` — no auth by default
- **Database name:** Exposed as a `database` constructor parameter (default: `"memgraph"`). This replaces FalkorDB's named-graph concept (`select_graph("synapse")`).
- **`query(cypher, params) -> list[neo4j.Record]`:** Returns the records list from `driver.execute_query()`. Callers access values by column name: `record["n"]`, `record["full_name"]`, etc.
- **`execute(cypher, params) -> None`:** Calls `driver.execute_query()` and discards the result. Behaviour unchanged.
- **Driver lifecycle:** The driver is created once and held on the instance. A `close()` method is added to cleanly shut it down (important for tests and CLI teardown).

### `schema.py`

Index creation syntax differs between Memgraph and Neo4j:

| Backend  | Syntax |
|----------|--------|
| Memgraph | `CREATE INDEX ON :Label(property)` |
| Neo4j    | `CREATE INDEX FOR (n:Label) ON (n.property)` |

The schema setup function gains a `dialect: Literal["memgraph", "neo4j"] = "memgraph"` parameter and emits the correct index statements accordingly. All other schema Cypher (constraints, etc.) is identical between the two backends.

### Graph layer callers

All files in `src/synapse/graph/` that consume query results update their result access pattern:

- **Before (FalkorDB):** `result_set[i][j]` — positional access into a list-of-lists
- **After (neo4j):** `records[i]["column_name"]` — named access on `neo4j.Record` objects

Affected files: `lookups.py`, `analysis.py`, `traversal.py`, `queries.py`, `nodes.py`, `edges.py`.

FalkorDB returned `Node` objects with `.properties` dicts. The `neo4j` driver returns `Node` objects accessed directly as `node["property"]` or via `.get("property")`. Property access patterns in callers update accordingly.

### `pyproject.toml`

```toml
# Remove:
"falkordb>=1.0.0"

# Add:
"neo4j>=5.0.0"
```

### Test files

Two unit test files (`tests/unit/test_queries.py`, `tests/unit/test_service.py`) import `from falkordb.node import Node as FalkorNode` to construct mock graph nodes. These are replaced with `MagicMock` objects or plain objects with `__getitem__` stubbed to match the `neo4j.Record` / `neo4j.graph.Node` interface.

### Docker / documentation

Integration test setup command updates:

```bash
# Before
docker run -p 6379:6379 -it --rm falkordb/falkordb:latest

# After
docker run -p 7687:7687 -it --rm memgraph/memgraph:latest
```

`CLAUDE.md` and any other references to port 6379 or the FalkorDB image update accordingly.

---

## Data Flow

```
GraphConnection.create(host, port, database, dialect)
  → GraphDatabase.driver("bolt://host:port", auth=("",""))

GraphConnection.query(cypher, params)
  → driver.execute_query(cypher, params, database_=database)
  → list[neo4j.Record]   ← returned to callers

GraphConnection.execute(cypher, params)
  → driver.execute_query(cypher, params, database_=database)
  → None
```

---

## Error Handling

The `neo4j` driver raises structured exceptions (`ServiceUnavailable`, `CypherSyntaxError`, `ConstraintError`, etc.). The current graph layer has no explicit error handling — exceptions propagate to the service layer as before. No change needed.

---

## Future: Adding Neo4j Support

When Neo4j support is needed:

1. Pass `dialect="neo4j"` to the schema setup function — index syntax switches automatically.
2. Pass `database="neo4j"` (or the target database name) to `GraphConnection.create()`.
3. Update the connection URI to point at the Neo4j instance.

No code changes beyond configuration are required.

---

## Testing Strategy

**Unit tests:**
- Mock the `neo4j.Driver` at the boundary (`GraphConnection._driver`).
- Replace `falkordb.node.Node` mock construction with `MagicMock` objects that support `__getitem__` for property access.
- All existing test assertions remain valid; only mock setup changes.

**Integration tests:**
- Start Memgraph via Docker: `docker run -p 7687:7687 -it --rm memgraph/memgraph:latest`
- Run `pytest tests/integration/ -v -m integration` — all existing test scenarios remain valid.
- The `=~` operator now works, enabling direct Cypher-level regex filtering without Python post-processing.
