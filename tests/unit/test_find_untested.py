from __future__ import annotations

from unittest.mock import MagicMock

from synapps.graph.analysis import find_untested
from synapps.graph.lookups import _TEST_PATH_PATTERN


def _conn_with_side_effects(*query_results):
    """Return a mock GraphConnection with sequential query side effects."""
    conn = MagicMock()
    conn.query.side_effect = list(query_results)
    return conn


# ---------------------------------------------------------------------------
# Test 1: Response shape — both top-level keys present
# ---------------------------------------------------------------------------

def test_returns_methods_and_stats_keys():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    result = find_untested(conn)
    assert {"methods", "stats"} <= set(result.keys())


# ---------------------------------------------------------------------------
# Test 2: Stats keys use untested_count/untested_ratio (not dead_count)
# ---------------------------------------------------------------------------

def test_stats_keys_are_untested_not_dead():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    result = find_untested(conn)
    assert set(result["stats"].keys()) == {"total_methods", "untested_count", "untested_ratio", "truncated", "limit", "offset"}


# ---------------------------------------------------------------------------
# Test 3: Empty graph returns empty methods and zero counts
# ---------------------------------------------------------------------------

def test_empty_graph_returns_empty_methods():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    result = find_untested(conn)
    assert result["methods"] == []
    assert result["stats"]["untested_count"] == 0


# ---------------------------------------------------------------------------
# Test 4: Untested method returned with correct shape (no inbound_call_count)
# ---------------------------------------------------------------------------

def test_untested_method_returned_with_correct_shape():
    conn = _conn_with_side_effects(
        [("Ns.Foo.bar", "/src/Foo.py", 10)],
        [(1,)],
        [(5,)],
    )
    result = find_untested(conn)
    assert len(result["methods"]) == 1
    m = result["methods"][0]
    assert set(m.keys()) == {"full_name", "file_path", "line"}
    assert m["full_name"] == "Ns.Foo.bar"
    assert m["file_path"] == "/src/Foo.py"
    assert m["line"] == 10


# ---------------------------------------------------------------------------
# Test 5: untested_ratio computed correctly
# ---------------------------------------------------------------------------

def test_untested_ratio_computed_correctly():
    conn = _conn_with_side_effects(
        [("A.B", "/a.py", 1)],
        [(1,)],
        [(4,)],
    )
    result = find_untested(conn)
    assert result["stats"]["total_methods"] == 4
    assert result["stats"]["untested_count"] == 1
    assert result["stats"]["untested_ratio"] == 0.25


# ---------------------------------------------------------------------------
# Test 6: Division by zero guard when total_methods is 0
# ---------------------------------------------------------------------------

def test_ratio_zero_division_guard():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    result = find_untested(conn)
    assert result["stats"]["untested_ratio"] == 0.0


# ---------------------------------------------------------------------------
# Test 7: Test methods excluded via NOT m.file_path =~ $test_pattern
# ---------------------------------------------------------------------------

def test_test_methods_excluded_via_cypher():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    find_untested(conn)
    cypher = conn.query.call_args_list[0].args[0]
    params = conn.query.call_args_list[0].args[1]
    assert "NOT m.file_path =~ $test_pattern" in cypher
    assert params["test_pattern"] == _TEST_PATH_PATTERN


# ---------------------------------------------------------------------------
# Test 8: HTTP handlers excluded via NOT (m)-[:SERVES]->()
# ---------------------------------------------------------------------------

def test_serves_excluded_via_cypher():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    find_untested(conn)
    cypher = conn.query.call_args_list[0].args[0]
    assert "NOT (m)-[:SERVES]->()" in cypher


# ---------------------------------------------------------------------------
# Test 9: Interface impl targets excluded via NOT ()-[:IMPLEMENTS]->(m)
# ---------------------------------------------------------------------------

def test_implements_target_excluded_via_cypher():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    find_untested(conn)
    cypher = conn.query.call_args_list[0].args[0]
    assert "NOT ()-[:IMPLEMENTS]->(m)" in cypher


# ---------------------------------------------------------------------------
# Test 10: Dispatch targets excluded via NOT ()-[:DISPATCHES_TO]->(m)
# ---------------------------------------------------------------------------

def test_dispatches_to_excluded_via_cypher():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    find_untested(conn)
    cypher = conn.query.call_args_list[0].args[0]
    assert "NOT ()-[:DISPATCHES_TO]->(m)" in cypher


# ---------------------------------------------------------------------------
# Test 11: Override methods excluded via NOT (m)-[:OVERRIDES]->()
# ---------------------------------------------------------------------------

def test_overrides_excluded_via_cypher():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    find_untested(conn)
    cypher = conn.query.call_args_list[0].args[0]
    assert "NOT (m)-[:OVERRIDES]->()" in cypher


# ---------------------------------------------------------------------------
# Test 12: Constructors excluded via name check AND parent-name match
# ---------------------------------------------------------------------------

def test_constructors_excluded_via_cypher():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    find_untested(conn)
    cypher = conn.query.call_args_list[0].args[0]
    assert "'__init__'" in cypher
    assert "'constructor'" in cypher
    assert "'Up'" in cypher
    assert "'Down'" in cypher
    assert "'BuildTargetModel'" in cypher
    assert "p.name = m.name" in cypher


# ---------------------------------------------------------------------------
# Test 13: TESTS edge check (not CALLS) used for untested condition
# ---------------------------------------------------------------------------

def test_no_tests_condition_in_cypher():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    find_untested(conn)
    cypher = conn.query.call_args_list[0].args[0]
    assert "NOT ()-[:TESTS]->(m)" in cypher
    assert "[:CALLS]->(m)" not in cypher


# ---------------------------------------------------------------------------
# Test 14: Non-empty exclude_pattern is applied to the query
# ---------------------------------------------------------------------------

def test_exclude_pattern_passed_to_query():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    find_untested(conn, exclude_pattern=".*Gen.*")
    params = conn.query.call_args_list[0].args[1]
    cypher = conn.query.call_args_list[0].args[0]
    assert params["exclude_pattern"] == ".*Gen.*"
    assert "NOT m.full_name =~ $exclude_pattern" in cypher


# ---------------------------------------------------------------------------
# Test 15: Empty exclude_pattern (default) includes no-op guard
# ---------------------------------------------------------------------------

def test_empty_exclude_pattern_default():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    find_untested(conn)
    params = conn.query.call_args_list[0].args[1]
    cypher = conn.query.call_args_list[0].args[0]
    assert params["exclude_pattern"] == ""
    assert "$exclude_pattern = ''" in cypher


# ---------------------------------------------------------------------------
# Regression: exclude_pattern without .* anchors must be auto-wrapped
# so Cypher =~ (which is full-string match) works as substring match
# ---------------------------------------------------------------------------

def test_exclude_pattern_auto_wrapped_for_substring_match():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    find_untested(conn, exclude_pattern=r"Configuration\.Configure")
    params = conn.query.call_args_list[0].args[1]
    assert params["exclude_pattern"] == r".*Configuration\.Configure.*"


def test_exclude_pattern_already_anchored_not_double_wrapped():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    find_untested(conn, exclude_pattern=".*Generated.*")
    params = conn.query.call_args_list[0].args[1]
    assert params["exclude_pattern"] == ".*Generated.*"


# ---------------------------------------------------------------------------
# Regression: decorator-registered entry points excluded via attributes
# ---------------------------------------------------------------------------

def test_decorator_entry_points_excluded_via_cypher():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    find_untested(conn)
    cypher = conn.query.call_args_list[0].args[0]
    assert 'CONTAINS \'"command"\'' in cypher
    assert 'CONTAINS \'"tool"\'' in cypher
    assert 'CONTAINS \'"callback"\'' in cypher


# ---------------------------------------------------------------------------
# Regression: Interface/Protocol definition methods excluded
# ---------------------------------------------------------------------------

def test_interface_member_methods_excluded_via_cypher():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    find_untested(conn)
    cypher = conn.query.call_args_list[0].args[0]
    assert "NOT (m)<-[:CONTAINS]-(:Interface)" in cypher


# ---------------------------------------------------------------------------
# Test 16: ORDER BY clause present in first query
# ---------------------------------------------------------------------------

def test_ordering_in_cypher():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    find_untested(conn)
    cypher = conn.query.call_args_list[0].args[0]
    assert "ORDER BY m.file_path, m.full_name" in cypher


# ---------------------------------------------------------------------------
# Test 17: Total methods query has same exclusions and uses count(m)
# ---------------------------------------------------------------------------

def test_total_methods_query_has_same_exclusions():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    find_untested(conn)
    cypher = conn.query.call_args_list[2].args[0]
    assert "NOT m.file_path =~ $test_pattern" in cypher
    assert "count(m)" in cypher


# ---------------------------------------------------------------------------
# Test 18: limit parameter truncates methods list and sets _truncated flag
# ---------------------------------------------------------------------------

def test_limit_truncates_methods_and_sets_flag():
    page_rows = [(f"Ns.Foo.M{i}", f"/src/Foo.cs", i) for i in range(3)]
    conn = _conn_with_side_effects(page_rows, [(5,)], [(10,)])
    result = find_untested(conn, limit=3)
    assert len(result["methods"]) == 3
    assert result["stats"]["truncated"] is True
    assert result["stats"]["limit"] == 3
    # stats still reflect the full count
    assert result["stats"]["untested_count"] == 5


# ---------------------------------------------------------------------------
# Test 19: limit not exceeded — truncated is False
# ---------------------------------------------------------------------------

def test_limit_not_exceeded_truncated_false():
    rows = [("Ns.Foo.M1", "/src/Foo.cs", 1)]
    conn = _conn_with_side_effects(rows, [(1,)], [(5,)])
    result = find_untested(conn, limit=50)
    assert len(result["methods"]) == 1
    assert result["stats"]["truncated"] is False
