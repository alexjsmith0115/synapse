from __future__ import annotations

from unittest.mock import MagicMock

from synapse.graph.nodes import upsert_endpoint
from synapse.graph.edges import (
    upsert_serves,
    upsert_http_calls,
    batch_upsert_serves,
    batch_upsert_http_calls,
    delete_orphan_endpoints,
)


def _mock_conn() -> MagicMock:
    return MagicMock()


def test_upsert_endpoint_executes_merge() -> None:
    conn = _mock_conn()
    upsert_endpoint(conn, route="/api/items/{id}", http_method="GET", name="GET /api/items/{id}")
    conn.execute.assert_called_once()
    cypher = conn.execute.call_args[0][0]
    assert "MERGE" in cypher
    assert "Endpoint" in cypher


def test_upsert_serves_executes_merge() -> None:
    conn = _mock_conn()
    upsert_serves(conn, handler_full_name="Ctrl.Get", route="/api/items", http_method="GET")
    conn.execute.assert_called_once()
    cypher = conn.execute.call_args[0][0]
    assert "SERVES" in cypher
    assert "Method" in cypher
    assert "Endpoint" in cypher


def test_upsert_http_calls_with_call_site() -> None:
    conn = _mock_conn()
    upsert_http_calls(conn, caller_full_name="svc.get", route="/api/items", http_method="GET", line=10, col=4)
    conn.execute.assert_called_once()
    cypher = conn.execute.call_args[0][0]
    assert "HTTP_CALLS" in cypher
    assert "call_sites" in cypher


def test_batch_upsert_serves_skips_empty() -> None:
    conn = _mock_conn()
    batch_upsert_serves(conn, [])
    conn.execute.assert_not_called()


def test_batch_upsert_http_calls_skips_empty() -> None:
    conn = _mock_conn()
    batch_upsert_http_calls(conn, [])
    conn.execute.assert_not_called()


def test_batch_upsert_serves_executes_unwind() -> None:
    conn = _mock_conn()
    batch_upsert_serves(conn, [{"handler": "Ctrl.Get", "route": "/api/items", "http_method": "GET"}])
    conn.execute.assert_called_once()
    cypher = conn.execute.call_args[0][0]
    assert "UNWIND" in cypher
    assert "SERVES" in cypher


def test_batch_upsert_http_calls_executes_unwind() -> None:
    conn = _mock_conn()
    batch_upsert_http_calls(conn, [{"caller": "svc.get", "route": "/api/items", "http_method": "GET", "line": 10, "col": 4}])
    conn.execute.assert_called_once()
    cypher = conn.execute.call_args[0][0]
    assert "UNWIND" in cypher
    assert "HTTP_CALLS" in cypher


def test_delete_orphan_endpoints() -> None:
    conn = _mock_conn()
    delete_orphan_endpoints(conn, "/repo/path")
    # Two-step cleanup: remove CONTAINS edge, then delete fully orphaned nodes
    assert conn.execute.call_count == 2
    first_cypher = conn.execute.call_args_list[0][0][0]
    second_cypher = conn.execute.call_args_list[1][0][0]
    assert "Endpoint" in first_cypher
    assert "DELETE c" in first_cypher
    assert "Endpoint" in second_cypher
    assert "DELETE ep" in second_cypher
