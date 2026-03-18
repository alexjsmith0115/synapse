from unittest.mock import MagicMock, call

from synapse.indexer.overrides_indexer import OverridesIndexer


def test_index_executes_inherits_traversal_query() -> None:
    conn = MagicMock()
    conn.query.return_value = [[0]]

    OverridesIndexer(conn).index()

    cypher_executed = conn.execute.call_args[0][0]
    assert "[:INHERITS*]" in cypher_executed


def test_index_creates_overrides_merge() -> None:
    conn = MagicMock()
    conn.query.return_value = [[0]]

    OverridesIndexer(conn).index()

    cypher_executed = conn.execute.call_args[0][0]
    assert "MERGE (child_method)-[:OVERRIDES]->(ancestor_method)" in cypher_executed


def test_index_excludes_self_overrides() -> None:
    conn = MagicMock()
    conn.query.return_value = [[0]]

    OverridesIndexer(conn).index()

    cypher_executed = conn.execute.call_args[0][0]
    assert "child_method.full_name <> ancestor_method.full_name" in cypher_executed


def test_index_matches_methods_by_name() -> None:
    conn = MagicMock()
    conn.query.return_value = [[0]]

    OverridesIndexer(conn).index()

    cypher_executed = conn.execute.call_args[0][0]
    assert "child_method.name = ancestor_method.name" in cypher_executed


def test_index_queries_edge_count_and_returns_it() -> None:
    conn = MagicMock()
    conn.query.return_value = [[7]]

    result = OverridesIndexer(conn).index()

    assert conn.query.called
    count_cypher = conn.query.call_args[0][0]
    assert "OVERRIDES" in count_cypher
    assert result == 7


def test_index_returns_zero_when_no_edges() -> None:
    conn = MagicMock()
    conn.query.return_value = [[0]]

    result = OverridesIndexer(conn).index()

    assert result == 0
