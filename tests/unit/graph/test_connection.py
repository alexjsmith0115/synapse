from unittest.mock import MagicMock, patch
from synapse.graph.connection import GraphConnection


def test_query_returns_result_set() -> None:
    mock_graph = MagicMock()
    mock_result = MagicMock()
    mock_result.result_set = [["row1"], ["row2"]]
    mock_graph.query.return_value = mock_result

    conn = GraphConnection(mock_graph)
    result = conn.query("MATCH (n) RETURN n")

    assert result == [["row1"], ["row2"]]
    mock_graph.query.assert_called_once_with("MATCH (n) RETURN n", {})


def test_query_passes_params() -> None:
    mock_graph = MagicMock()
    mock_graph.query.return_value = MagicMock(result_set=[])

    conn = GraphConnection(mock_graph)
    conn.query("MATCH (n {path: $p}) RETURN n", {"p": "/foo"})

    mock_graph.query.assert_called_once_with("MATCH (n {path: $p}) RETURN n", {"p": "/foo"})


def test_execute_calls_graph_query() -> None:
    mock_graph = MagicMock()

    conn = GraphConnection(mock_graph)
    conn.execute("CREATE (n:File {path: $p})", {"p": "/foo"})

    mock_graph.query.assert_called_once_with("CREATE (n:File {path: $p})", {"p": "/foo"})
