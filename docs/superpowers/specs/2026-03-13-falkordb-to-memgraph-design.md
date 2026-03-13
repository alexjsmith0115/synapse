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
- **`dialect` storage:** `GraphConnection` stores the `dialect` value and passes it to `ensure_schema()` when called, so callers do not need to supply it separately.

### `schema.py`

Index creation syntax differs between Memgraph and Neo4j:

| Backend  | Syntax |
|----------|--------|
| Memgraph | `CREATE INDEX ON :Label(property)` |
| Neo4j    | `CREATE INDEX FOR (n:Label) ON (n.property)` |

The `ensure_schema(conn, dialect)` function gains a `dialect: Literal["memgraph", "neo4j"] = "memgraph"` parameter and emits the correct index statements accordingly. All other schema Cypher is identical between the two backends.

**Important:** The existing `_INDICES` list in `schema.py` already uses Neo4j-style syntax (`CREATE INDEX FOR (n:Repository) ON (n.path)`). For `dialect="neo4j"` these strings require **no changes**. For `dialect="memgraph"` the implementation generates Memgraph-style strings (`CREATE INDEX ON :Repository(path)`) at runtime based on the dialect. Both forms are produced from the same label/property data — the `dialect` parameter controls which template is used.

The existing `from redis.exceptions import ResponseError` import and catch block (used to tolerate already-existing indices) is removed. On Memgraph, `CREATE INDEX ON` is idempotent — it does not raise if the index already exists. The try/except guard is dropped entirely.

### Graph layer callers

`neo4j.Record` supports **both** integer positional access (`record[0]`) and named key access (`record["column_name"]`). This means most scalar-column positional accesses (`r[0]`, `r[1]`, `r[2]`) will continue to work unchanged after the migration. Only two access patterns are genuinely broken and require updates:

1. **Node `.properties` attribute** — FalkorDB nodes expose `node.properties`; neo4j nodes do not. All callers that access `node.properties` must switch to `node["key"]` or `node.get("key")`.
2. **Node `.id` for deduplication** — `Node.id` is deprecated in the neo4j 5.x driver and will be removed in a future version. Replace with `node.element_id`.

Files that only call `conn.execute()` (write operations with no result rows) — `nodes.py` and `edges.py` — require **no changes** to result access.

**Special cases to address explicitly:**

- **`service.py` — `_p()` function:** This helper is called on every query result throughout the service layer. It currently guards with `hasattr(node, "properties")` — this evaluates to `False` for neo4j nodes, causing `_p()` to return the raw `Node` object instead of a dict. Two things must change: (a) update the guard condition (e.g. `isinstance(node, neo4j.graph.Node)`), and (b) replace the body's `node.properties` access with `dict(node)`. The `node.labels` access is unchanged — neo4j nodes also expose `.labels` as a frozenset. This is the widest-reaching fix in the codebase.

- **`analysis.py` — `audit_architecture()`:** Uses `dict(zip(range(len(r)), r))` to convert rows to integer-keyed dicts. Update to `dict(r)` — `neo4j.Record` supports this directly.

- **`lookups.py` — node deduplication:** `list_summarized` uses `node.id` unconditionally; `find_callers` and `find_callees` use `node.id if hasattr(node, "id") else node.get("full_name")`. Note that neo4j 5.x nodes do still expose a deprecated `.id` property, so `hasattr(node, "id")` returns `True` and the deprecated path is taken silently. Both patterns must be explicitly updated to `node.element_id`.

- **`lookups.py` — `get_index_status()`:** Accesses `repo.properties.get("last_indexed")` directly on the FalkorDB node. Update to `repo.get("last_indexed")`.

- **`traversal.py` — stale comment:** The comment "FalkorDB does not support parameterized variable-length relationship bounds, so the depth integer is inlined into the Cypher string after validation" remains technically correct for Memgraph too, but the FalkorDB attribution is wrong. Update to remove the FalkorDB reference while preserving the reason depth is inlined.

### `pyproject.toml`

```toml
# Remove:
"falkordb>=1.0.0"

# Add:
"neo4j>=5.0.0"
```

### Test files

Three unit test files require changes:

1. **`tests/unit/test_queries.py`** and **`tests/unit/test_service.py`** — import `from falkordb.node import Node as FalkorNode` to construct mock graph nodes. Replace with `MagicMock` objects with `__getitem__` stubbed to match the neo4j `graph.Node` interface.

2. **`tests/unit/graph/test_schema.py`** — imports `from redis.exceptions import ResponseError` and constructs `ResponseError` objects in test cases (mirroring the try/except in `schema.py`). Both the import and the test cases for duplicate-index handling are removed, since `CREATE INDEX ON` is idempotent on Memgraph.

### Docker / documentation

Integration test setup command updates:

```bash
# Before
docker run -p 6379:6379 -it --rm falkordb/falkordb:latest

# After
docker run -p 7687:7687 -it --rm memgraph/memgraph:latest
```

`CLAUDE.md` and any other references to port 6379 or the FalkorDB image update accordingly.

**Note on Memgraph persistence:** Memgraph runs in-memory by default and loses data on restart. This is fine for integration tests, which always re-index from scratch. No special persistence flags are needed for the test setup. Document this behaviour explicitly in `CLAUDE.md` so developers do not investigate phantom data-loss.

---

## Dialect Propagation

The `dialect` value flows from configuration into `GraphConnection` and then into schema setup:

```
GraphConnection.create(host, port, database, dialect)
  → stores dialect on instance

conn.ensure_schema()   ← called by SynapseService/Indexer
  → delegates to ensure_schema(self, self._dialect)
```

`SynapseService` and `Indexer` do not need to know about `dialect` — `GraphConnection` carries it.

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

The `neo4j` driver raises structured exceptions (`ServiceUnavailable`, `CypherSyntaxError`, `ConstraintError`, etc.). The current graph layer has no explicit error handling — exceptions propagate to the service layer as before. The `redis.exceptions.ResponseError` import in `schema.py` and `test_schema.py` is removed (see schema section above).

---

## Future: Adding Neo4j Support

When Neo4j support is needed:

1. Pass `dialect="neo4j"` to `GraphConnection.create()` — index syntax switches automatically.
2. Pass `database="neo4j"` (or the target database name) to `GraphConnection.create()`.
3. Update the connection URI to point at the Neo4j instance.

No code changes beyond configuration are required.

---

## Testing Strategy

**Unit tests:**
- Mock the `neo4j.Driver` at the boundary (`GraphConnection._driver`).
- Replace `falkordb.node.Node` mock construction with `MagicMock` objects that support `__getitem__` for property access, matching the neo4j `graph.Node` interface.
- Remove `redis.exceptions.ResponseError`-based test cases in `test_schema.py`.
- All existing test assertions remain valid; only mock setup changes.

**Integration tests:**
- Start Memgraph via Docker: `docker run -p 7687:7687 -it --rm memgraph/memgraph:latest`
- Run `pytest tests/integration/ -v -m integration` — all existing test scenarios remain valid.
- The `=~` operator now works, enabling direct Cypher-level regex filtering without Python post-processing.
