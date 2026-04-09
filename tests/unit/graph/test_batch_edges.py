from __future__ import annotations

from unittest.mock import MagicMock

from synapps.graph.edges import (
    batch_upsert_contains_symbol,
    batch_upsert_dir_contains,
    batch_upsert_file_contains_symbol,
    batch_upsert_symbol_imports,
)


def _conn() -> MagicMock:
    return MagicMock()


# ---------------------------------------------------------------------------
# batch_upsert_file_contains_symbol
# ---------------------------------------------------------------------------


def test_file_contains_symbol_empty_batch_does_nothing() -> None:
    conn = _conn()
    batch_upsert_file_contains_symbol(conn, [])
    conn.execute.assert_not_called()


def test_file_contains_symbol_uses_unwind_and_contains() -> None:
    conn = _conn()
    batch = [{"file": "/a/b.py", "sym": "mod.Foo"}]
    batch_upsert_file_contains_symbol(conn, batch)
    conn.execute.assert_called_once()
    cypher = conn.execute.call_args[0][0]
    assert "UNWIND $batch AS row" in cypher
    assert "MERGE (src)-[:CONTAINS]->(dst)" in cypher
    assert "File {path: row.file}" in cypher
    assert "full_name: row.sym" in cypher


def test_file_contains_symbol_passes_full_batch() -> None:
    conn = _conn()
    batch = [
        {"file": "/a/b.py", "sym": "mod.Foo"},
        {"file": "/a/c.py", "sym": "mod.Bar"},
    ]
    batch_upsert_file_contains_symbol(conn, batch)
    conn.execute.assert_called_once()
    params = conn.execute.call_args[0][1]
    assert params["batch"] == batch


# ---------------------------------------------------------------------------
# batch_upsert_contains_symbol
# ---------------------------------------------------------------------------


def test_contains_symbol_empty_batch_does_nothing() -> None:
    conn = _conn()
    batch_upsert_contains_symbol(conn, [])
    conn.execute.assert_not_called()


def test_contains_symbol_uses_unwind_and_contains() -> None:
    conn = _conn()
    batch = [{"from_id": "mod.Foo", "to_id": "mod.Foo.bar"}]
    batch_upsert_contains_symbol(conn, batch)
    conn.execute.assert_called_once()
    cypher = conn.execute.call_args[0][0]
    assert "UNWIND $batch AS row" in cypher
    assert "MERGE (src)-[:CONTAINS]->(dst)" in cypher
    assert "full_name: row.from_id" in cypher
    assert "full_name: row.to_id" in cypher


def test_contains_symbol_passes_full_batch() -> None:
    conn = _conn()
    batch = [
        {"from_id": "mod.Foo", "to_id": "mod.Foo.bar"},
        {"from_id": "mod.Baz", "to_id": "mod.Baz.qux"},
    ]
    batch_upsert_contains_symbol(conn, batch)
    conn.execute.assert_called_once()
    params = conn.execute.call_args[0][1]
    assert params["batch"] == batch


# ---------------------------------------------------------------------------
# batch_upsert_dir_contains
# ---------------------------------------------------------------------------


def test_dir_contains_empty_batch_does_nothing() -> None:
    conn = _conn()
    batch_upsert_dir_contains(conn, [])
    conn.execute.assert_not_called()


def test_dir_contains_uses_unwind_and_contains() -> None:
    conn = _conn()
    batch = [{"parent": "/a", "child": "/a/b"}]
    batch_upsert_dir_contains(conn, batch)
    conn.execute.assert_called_once()
    cypher = conn.execute.call_args[0][0]
    assert "UNWIND $batch AS row" in cypher
    assert "MERGE (src)-[:CONTAINS]->(dst)" in cypher
    assert "path: row.parent" in cypher
    assert "path: row.child" in cypher


def test_dir_contains_passes_full_batch() -> None:
    conn = _conn()
    batch = [
        {"parent": "/a", "child": "/a/b"},
        {"parent": "/a", "child": "/a/c"},
    ]
    batch_upsert_dir_contains(conn, batch)
    conn.execute.assert_called_once()
    params = conn.execute.call_args[0][1]
    assert params["batch"] == batch


# ---------------------------------------------------------------------------
# batch_upsert_symbol_imports
# ---------------------------------------------------------------------------


def test_symbol_imports_empty_batch_does_nothing() -> None:
    conn = _conn()
    batch_upsert_symbol_imports(conn, [])
    conn.execute.assert_not_called()


def test_symbol_imports_uses_unwind_and_imports() -> None:
    conn = _conn()
    batch = [{"file": "/a/b.py", "sym": "mod.Foo"}]
    batch_upsert_symbol_imports(conn, batch)
    conn.execute.assert_called_once()
    cypher = conn.execute.call_args[0][0]
    assert "UNWIND $batch AS row" in cypher
    assert "MERGE (src)-[:IMPORTS]->(dst)" in cypher
    assert "File {path: row.file}" in cypher
    assert "full_name: row.sym" in cypher


def test_symbol_imports_passes_full_batch() -> None:
    conn = _conn()
    batch = [
        {"file": "/a/b.py", "sym": "mod.Foo"},
        {"file": "/a/c.py", "sym": "mod.Bar"},
    ]
    batch_upsert_symbol_imports(conn, batch)
    conn.execute.assert_called_once()
    params = conn.execute.call_args[0][1]
    assert params["batch"] == batch
