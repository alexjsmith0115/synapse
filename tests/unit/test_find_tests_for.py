from __future__ import annotations

from unittest.mock import MagicMock

from synapps.graph.lookups import find_tests_for


def _conn_with_side_effects(*query_results):
    conn = MagicMock()
    conn.query.side_effect = list(query_results)
    return conn


def test_returns_list_of_dicts_with_correct_keys():
    conn = _conn_with_side_effects(
        [("tests.test_foo.test_bar", "/tests/test_foo.py", 10)]
    )
    result = find_tests_for(conn, "Ns.Foo.bar")
    assert len(result) == 1
    assert set(result[0].keys()) == {"full_name", "file_path", "line"}


def test_returns_correct_values():
    conn = _conn_with_side_effects(
        [("tests.test_foo.test_bar", "/tests/test_foo.py", 10)]
    )
    result = find_tests_for(conn, "Ns.Foo.bar")
    assert result[0]["full_name"] == "tests.test_foo.test_bar"
    assert result[0]["file_path"] == "/tests/test_foo.py"
    assert result[0]["line"] == 10


def test_returns_empty_list_when_no_tests():
    conn = _conn_with_side_effects([])
    result = find_tests_for(conn, "Ns.Foo.bar")
    assert result == []


def test_cypher_queries_tests_edge_direction():
    conn = _conn_with_side_effects([])
    find_tests_for(conn, "Ns.Foo.bar")
    cypher = conn.query.call_args_list[0].args[0]
    assert "(t:Method)-[:TESTS]->(m:Method" in cypher


def test_cypher_uses_fn_parameter():
    conn = _conn_with_side_effects([])
    find_tests_for(conn, "Ns.Foo.bar")
    params = conn.query.call_args_list[0].args[1]
    assert params["fn"] == "Ns.Foo.bar"
