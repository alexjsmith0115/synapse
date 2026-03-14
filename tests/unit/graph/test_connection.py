import concurrent.futures
import pytest
from unittest.mock import MagicMock, patch
from synapse.graph.connection import GraphConnection


def test_create_returns_graph_connection():
    mock_driver = MagicMock()
    with patch("synapse.graph.connection.GraphDatabase") as mock_gdb:
        mock_gdb.driver.return_value = mock_driver
        conn = GraphConnection.create(host="localhost", port=7687)
    assert isinstance(conn, GraphConnection)
    mock_gdb.driver.assert_called_once_with("bolt://localhost:7687", auth=("", ""))


def test_query_returns_records():
    mock_driver = MagicMock()
    mock_records = [MagicMock(), MagicMock()]
    mock_driver.execute_query.return_value = (mock_records, MagicMock(), [])
    conn = GraphConnection(mock_driver, database="memgraph", dialect="memgraph")
    result = conn.query("MATCH (n) RETURN n")
    assert result == mock_records


def test_execute_returns_none():
    mock_driver = MagicMock()
    mock_driver.execute_query.return_value = ([], MagicMock(), [])
    conn = GraphConnection(mock_driver, database="memgraph", dialect="memgraph")
    result = conn.execute("MERGE (n:Foo {id: $id})", {"id": 1})
    assert result is None


def test_execute_implicit_uses_session_run():
    mock_driver = MagicMock()
    conn = GraphConnection(mock_driver, database="memgraph", dialect="memgraph")
    conn.execute_implicit("CREATE INDEX ON :Foo(bar)")
    mock_driver.session.assert_called_once_with(database="memgraph")
    session_ctx = mock_driver.session.return_value.__enter__.return_value
    session_ctx.run.assert_called_once_with("CREATE INDEX ON :Foo(bar)", {})


def test_close_calls_driver_close():
    mock_driver = MagicMock()
    conn = GraphConnection(mock_driver, database="memgraph", dialect="memgraph")
    conn.close()
    mock_driver.close.assert_called_once()


def test_dialect_stored_on_instance():
    mock_driver = MagicMock()
    conn = GraphConnection(mock_driver, database="memgraph", dialect="neo4j")
    assert conn.dialect == "neo4j"


def test_query_with_timeout_returns_records():
    """Returns query results normally when the query completes within the timeout."""
    mock_driver = MagicMock()
    records = [MagicMock(), MagicMock()]
    mock_driver.execute_query.return_value = (records, MagicMock(), [])
    conn = GraphConnection(mock_driver, database="memgraph", dialect="memgraph")

    result = conn.query_with_timeout("MATCH (n) RETURN n", timeout_s=10.0)

    assert result == records


def test_query_with_timeout_raises_timeout_error():
    """Raises TimeoutError when the query exceeds the timeout."""
    mock_driver = MagicMock()
    conn = GraphConnection(mock_driver, database="memgraph", dialect="memgraph")

    mock_future = MagicMock()
    mock_future.result.side_effect = concurrent.futures.TimeoutError()
    mock_executor = MagicMock()
    mock_executor.submit.return_value = mock_future

    with patch("synapse.graph.connection.concurrent.futures.ThreadPoolExecutor") as mock_tpe:
        mock_tpe.return_value = mock_executor
        with pytest.raises(TimeoutError, match="timeout"):
            conn.query_with_timeout("MATCH (n) RETURN n", timeout_s=0.001)


def test_query_with_timeout_shuts_down_executor_with_wait_on_success():
    """Executor is properly shut down (wait=True) on the success path, not abandoned to GC."""
    mock_driver = MagicMock()
    records = [MagicMock()]
    mock_driver.execute_query.return_value = (records, MagicMock(), [])
    conn = GraphConnection(mock_driver, database="memgraph", dialect="memgraph")

    mock_future = MagicMock()
    mock_future.result.return_value = records
    mock_executor = MagicMock()
    mock_executor.submit.return_value = mock_future

    with patch("synapse.graph.connection.concurrent.futures.ThreadPoolExecutor") as mock_tpe:
        mock_tpe.return_value = mock_executor
        conn.query_with_timeout("MATCH (n) RETURN n", timeout_s=10.0)

    mock_executor.shutdown.assert_called_once_with(wait=True)


def test_query_with_timeout_shuts_down_executor_with_no_wait_on_timeout():
    """Executor is shut down (wait=False) on the timeout path to avoid blocking the caller."""
    mock_driver = MagicMock()
    conn = GraphConnection(mock_driver, database="memgraph", dialect="memgraph")

    mock_future = MagicMock()
    mock_future.result.side_effect = concurrent.futures.TimeoutError()
    mock_executor = MagicMock()
    mock_executor.submit.return_value = mock_future

    with patch("synapse.graph.connection.concurrent.futures.ThreadPoolExecutor") as mock_tpe:
        mock_tpe.return_value = mock_executor
        with pytest.raises(TimeoutError):
            conn.query_with_timeout("MATCH (n) RETURN n", timeout_s=0.001)

    mock_executor.shutdown.assert_called_once_with(wait=False)
