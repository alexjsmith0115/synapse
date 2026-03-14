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


def test_close_calls_driver_close():
    mock_driver = MagicMock()
    conn = GraphConnection(mock_driver, database="memgraph", dialect="memgraph")
    conn.close()
    mock_driver.close.assert_called_once()


def test_dialect_stored_on_instance():
    mock_driver = MagicMock()
    conn = GraphConnection(mock_driver, database="memgraph", dialect="neo4j")
    assert conn.dialect == "neo4j"
