from unittest.mock import MagicMock, call
from synapps.graph.edges import delete_outgoing_edges_for_file


def _conn() -> MagicMock:
    return MagicMock()


def test_deletes_symbol_level_resolution_edges() -> None:
    """First query deletes CALLS, REFERENCES, INHERITS, IMPLEMENTS, DISPATCHES_TO, OVERRIDES from file's symbols."""
    conn = _conn()
    delete_outgoing_edges_for_file(conn, "/proj/src/Foo.cs")
    assert conn.execute.call_count == 2
    cypher, params = conn.execute.call_args_list[0][0]
    assert "CONTAINS" in cypher
    for edge_type in ["CALLS", "REFERENCES", "INHERITS", "IMPLEMENTS", "DISPATCHES_TO", "OVERRIDES"]:
        assert edge_type in cypher
    assert params["path"] == "/proj/src/Foo.cs"


def test_deletes_imports_from_file_node() -> None:
    """Second query deletes IMPORTS edges from the file node itself."""
    conn = _conn()
    delete_outgoing_edges_for_file(conn, "/proj/src/Bar.cs")
    assert conn.execute.call_count == 2
    cypher, params = conn.execute.call_args_list[1][0]
    assert "IMPORTS" in cypher
    assert params["path"] == "/proj/src/Bar.cs"


def test_does_not_delete_contains_edges() -> None:
    """CONTAINS edges are structural and must NOT be deleted."""
    conn = _conn()
    delete_outgoing_edges_for_file(conn, "/proj/src/Baz.cs")
    for c in conn.execute.call_args_list:
        cypher = c[0][0]
        # The first query mentions CONTAINS in the MATCH pattern (traversal),
        # but the DELETE should only target resolution edge types
        if "DELETE" in cypher and "IMPORTS" not in cypher:
            assert "CONTAINS" not in cypher.split("DELETE")[1]


