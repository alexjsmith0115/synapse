from unittest.mock import MagicMock

from synapse.graph.traversal import trace_call_chain


def _conn(return_value: list) -> MagicMock:
    conn = MagicMock()
    conn.query.return_value = return_value
    return conn


def test_trace_call_chain_returns_paths() -> None:
    conn = _conn([[["A.M1", "A.M2", "A.M3"]]])
    result = trace_call_chain(conn, "A.M1", "A.M3")
    assert result["paths"] == [["A.M1", "A.M2", "A.M3"]]
    assert result["start"] == "A.M1"
    assert result["end"] == "A.M3"


def test_trace_call_chain_no_path() -> None:
    conn = _conn([])
    result = trace_call_chain(conn, "A.M1", "B.M2")
    assert result["paths"] == []


def test_trace_call_chain_depth_clamped() -> None:
    conn = _conn([])
    result = trace_call_chain(conn, "A.M1", "A.M2", max_depth=20)
    cypher = conn.query.call_args[0][0]
    assert "*1..10" in cypher


def test_trace_call_chain_depth_in_cypher() -> None:
    conn = _conn([])
    trace_call_chain(conn, "A.M1", "A.M2", max_depth=4)
    cypher = conn.query.call_args[0][0]
    assert "*1..4" in cypher
