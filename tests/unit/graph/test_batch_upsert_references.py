from __future__ import annotations

from unittest.mock import MagicMock, call

from synapps.graph.edges import batch_upsert_references


def _conn() -> MagicMock:
    return MagicMock()


def test_empty_batch_does_nothing() -> None:
    conn = _conn()
    batch_upsert_references(conn, [])
    conn.execute.assert_not_called()


def test_first_query_matches_existing_nodes() -> None:
    conn = _conn()
    batch = [{"source": "Ns.Foo", "target": "Ns.Bar", "kind": "field_type"}]
    batch_upsert_references(conn, batch)
    cypher = conn.execute.call_args_list[0][0][0]
    assert "MATCH (src {full_name: row.source})" in cypher
    assert "MATCH" in cypher.split("MERGE")[0]


def test_second_query_creates_library_stubs() -> None:
    conn = _conn()
    batch = [{"source": "Ns.Foo", "target": "RestTemplate", "kind": "field_type"}]
    batch_upsert_references(conn, batch)
    assert conn.execute.call_count == 2
    cypher = conn.execute.call_args_list[1][0][0]
    assert "MERGE (stub:Class {full_name: row.target})" in cypher
    assert "stub.library = true" in cypher


def test_both_queries_receive_batch() -> None:
    conn = _conn()
    batch = [
        {"source": "Ns.Foo", "target": "Ns.Bar", "kind": "parameter"},
        {"source": "Ns.Baz", "target": "RestTemplate", "kind": "field_type"},
    ]
    batch_upsert_references(conn, batch)
    for i in range(2):
        params = conn.execute.call_args_list[i][0][1]
        assert params["batch"] == batch
