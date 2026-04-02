from __future__ import annotations

from unittest.mock import MagicMock

from synapps.graph.analysis import find_dead_code
from synapps.graph.lookups import _TEST_PATH_PATTERN


def _conn_with_side_effects(*query_results):
    """Return a mock GraphConnection with sequential query side effects."""
    conn = MagicMock()
    conn.query.side_effect = list(query_results)
    return conn


# ---------------------------------------------------------------------------
# Test 1: Response shape — both top-level keys and stats keys present
# ---------------------------------------------------------------------------

def test_returns_methods_and_stats_keys():
    conn = _conn_with_side_effects([], [(0,)])
    result = find_dead_code(conn)
    assert set(result.keys()) == {"methods", "stats"}
    assert set(result["stats"].keys()) == {"total_methods", "dead_count", "dead_ratio", "truncated", "limit"}


# ---------------------------------------------------------------------------
# Test 2: Empty graph returns empty methods and zero counts
# ---------------------------------------------------------------------------

def test_empty_graph_returns_empty_methods():
    conn = _conn_with_side_effects([], [(0,)])
    result = find_dead_code(conn)
    assert result["methods"] == []
    assert result["stats"]["dead_count"] == 0


# ---------------------------------------------------------------------------
# Test 3: Dead method returned with correct shape
# ---------------------------------------------------------------------------

def test_dead_method_returned_with_correct_shape():
    conn = _conn_with_side_effects(
        [("Ns.Foo.Bar", "/src/Foo.cs", 10)],
        [(5,)],
    )
    result = find_dead_code(conn)
    assert len(result["methods"]) == 1
    m = result["methods"][0]
    assert set(m.keys()) == {"full_name", "file_path", "line", "inbound_call_count"}
    assert m["full_name"] == "Ns.Foo.Bar"
    assert m["file_path"] == "/src/Foo.cs"
    assert m["line"] == 10
    assert m["inbound_call_count"] == 0


# ---------------------------------------------------------------------------
# Test 4: inbound_call_count is always 0 for all returned methods
# ---------------------------------------------------------------------------

def test_inbound_call_count_always_zero():
    conn = _conn_with_side_effects(
        [("A.B", "/a.cs", 1), ("C.D", "/c.cs", 2)],
        [(10,)],
    )
    result = find_dead_code(conn)
    assert all(m["inbound_call_count"] == 0 for m in result["methods"])


# ---------------------------------------------------------------------------
# Test 5: Stats dead_ratio is computed correctly
# ---------------------------------------------------------------------------

def test_stats_dead_ratio():
    conn = _conn_with_side_effects(
        [("A.B", "/a.cs", 1)],
        [(4,)],
    )
    result = find_dead_code(conn)
    assert result["stats"]["total_methods"] == 4
    assert result["stats"]["dead_count"] == 1
    assert result["stats"]["dead_ratio"] == 0.25


# ---------------------------------------------------------------------------
# Test 6: Division by zero guard when total_methods is 0
# ---------------------------------------------------------------------------

def test_stats_dead_ratio_zero_division_guard():
    conn = _conn_with_side_effects([], [(0,)])
    result = find_dead_code(conn)
    assert result["stats"]["dead_ratio"] == 0.0


# ---------------------------------------------------------------------------
# Test 7: Test methods excluded via NOT m.file_path =~ $test_pattern
# ---------------------------------------------------------------------------

def test_test_methods_excluded_via_cypher():
    conn = _conn_with_side_effects([], [(0,)])
    find_dead_code(conn)
    cypher = conn.query.call_args_list[0].args[0]
    params = conn.query.call_args_list[0].args[1]
    assert "NOT m.file_path =~ $test_pattern" in cypher
    assert params["test_pattern"] == _TEST_PATH_PATTERN


# ---------------------------------------------------------------------------
# Test 8: HTTP handlers excluded via NOT (m)-[:SERVES]->()
# ---------------------------------------------------------------------------

def test_serves_edge_excluded_via_cypher():
    conn = _conn_with_side_effects([], [(0,)])
    find_dead_code(conn)
    cypher = conn.query.call_args_list[0].args[0]
    assert "NOT (m)-[:SERVES]->()" in cypher


# ---------------------------------------------------------------------------
# Test 9: Interface impl targets excluded via NOT ()-[:IMPLEMENTS]->(m)
# ---------------------------------------------------------------------------

def test_implements_target_excluded_via_cypher():
    conn = _conn_with_side_effects([], [(0,)])
    find_dead_code(conn)
    cypher = conn.query.call_args_list[0].args[0]
    assert "NOT ()-[:IMPLEMENTS]->(m)" in cypher


# ---------------------------------------------------------------------------
# Test 10: Dispatch targets excluded via NOT ()-[:DISPATCHES_TO]->(m)
# ---------------------------------------------------------------------------

def test_dispatches_to_target_excluded_via_cypher():
    conn = _conn_with_side_effects([], [(0,)])
    find_dead_code(conn)
    cypher = conn.query.call_args_list[0].args[0]
    assert "NOT ()-[:DISPATCHES_TO]->(m)" in cypher


# ---------------------------------------------------------------------------
# Test 11: Override methods excluded via NOT (m)-[:OVERRIDES]->()
# ---------------------------------------------------------------------------

def test_overrides_excluded_via_cypher():
    conn = _conn_with_side_effects([], [(0,)])
    find_dead_code(conn)
    cypher = conn.query.call_args_list[0].args[0]
    assert "NOT (m)-[:OVERRIDES]->()" in cypher


# ---------------------------------------------------------------------------
# Test 12: Constructors excluded via name check AND parent-name match
# ---------------------------------------------------------------------------

def test_constructors_excluded_via_cypher():
    conn = _conn_with_side_effects([], [(0,)])
    find_dead_code(conn)
    cypher = conn.query.call_args_list[0].args[0]
    assert "'__init__'" in cypher
    assert "'constructor'" in cypher
    # EF Core migration methods excluded alongside constructors
    assert "'Up'" in cypher
    assert "'Down'" in cypher
    assert "'BuildTargetModel'" in cypher
    assert "parent.name = m.name" in cypher


# ---------------------------------------------------------------------------
# Test 13: Zero-callers check present in first query
# ---------------------------------------------------------------------------

def test_no_callers_excluded_via_cypher():
    conn = _conn_with_side_effects([], [(0,)])
    find_dead_code(conn)
    cypher = conn.query.call_args_list[0].args[0]
    assert "NOT EXISTS { MATCH ()-[:CALLS]->(m) }" in cypher


# ---------------------------------------------------------------------------
# Test 14: Non-empty exclude_pattern is applied to the query
# ---------------------------------------------------------------------------

def test_exclude_pattern_passed_to_query():
    conn = _conn_with_side_effects([], [(0,)])
    find_dead_code(conn, exclude_pattern=".*Generated.*")
    params = conn.query.call_args_list[0].args[1]
    cypher = conn.query.call_args_list[0].args[0]
    assert params["exclude_pattern"] == ".*Generated.*"
    assert "NOT m.full_name =~ $exclude_pattern" in cypher


# ---------------------------------------------------------------------------
# Test 15: Empty exclude_pattern (default) includes no-op guard
# ---------------------------------------------------------------------------

def test_empty_exclude_pattern_default():
    conn = _conn_with_side_effects([], [(0,)])
    find_dead_code(conn)
    params = conn.query.call_args_list[0].args[1]
    cypher = conn.query.call_args_list[0].args[0]
    assert params["exclude_pattern"] == ""
    assert "$exclude_pattern = ''" in cypher


# ---------------------------------------------------------------------------
# Regression: exclude_pattern without .* anchors must be auto-wrapped
# so Cypher =~ (which is full-string match) works as substring match
# ---------------------------------------------------------------------------

def test_exclude_pattern_auto_wrapped_for_substring_match():
    conn = _conn_with_side_effects([], [(0,)])
    find_dead_code(conn, exclude_pattern=r"Configuration\.Configure")
    params = conn.query.call_args_list[0].args[1]
    assert params["exclude_pattern"] == r".*Configuration\.Configure.*"


def test_exclude_pattern_already_anchored_not_double_wrapped():
    conn = _conn_with_side_effects([], [(0,)])
    find_dead_code(conn, exclude_pattern=".*Generated.*")
    params = conn.query.call_args_list[0].args[1]
    assert params["exclude_pattern"] == ".*Generated.*"


# ---------------------------------------------------------------------------
# Regression: decorator-registered entry points excluded via attributes
# ---------------------------------------------------------------------------

def test_decorator_entry_points_excluded_via_cypher():
    conn = _conn_with_side_effects([], [(0,)])
    find_dead_code(conn)
    cypher = conn.query.call_args_list[0].args[0]
    assert 'CONTAINS \'"command"\'' in cypher
    assert 'CONTAINS \'"tool"\'' in cypher
    assert 'CONTAINS \'"callback"\'' in cypher


# ---------------------------------------------------------------------------
# Regression: Interface/Protocol definition methods excluded
# ---------------------------------------------------------------------------

def test_interface_member_methods_excluded_via_cypher():
    conn = _conn_with_side_effects([], [(0,)])
    find_dead_code(conn)
    cypher = conn.query.call_args_list[0].args[0]
    assert "NOT (m)<-[:CONTAINS]-(:Interface)" in cypher


# ---------------------------------------------------------------------------
# Test 16: ORDER BY clause present in first query
# ---------------------------------------------------------------------------

def test_ordering_in_cypher():
    conn = _conn_with_side_effects([], [(0,)])
    find_dead_code(conn)
    cypher = conn.query.call_args_list[0].args[0]
    assert "ORDER BY m.file_path, m.full_name" in cypher


# ---------------------------------------------------------------------------
# Test 17: Total methods query uses same exclusions and count(m)
# ---------------------------------------------------------------------------

def test_total_methods_query_has_same_exclusions():
    conn = _conn_with_side_effects([], [(0,)])
    find_dead_code(conn)
    cypher = conn.query.call_args_list[1].args[0]
    assert "NOT m.file_path =~ $test_pattern" in cypher
    assert "count(m)" in cypher


# ---------------------------------------------------------------------------
# Regression: main() and Main() excluded as framework entry points
# ---------------------------------------------------------------------------

def test_main_methods_excluded_via_cypher():
    conn = _conn_with_side_effects([], [(0,)])
    find_dead_code(conn)
    cypher = conn.query.call_args_list[0].args[0]
    assert "'main'" in cypher
    assert "'Main'" in cypher


# ---------------------------------------------------------------------------
# Regression: Spring framework attributes excluded
# ---------------------------------------------------------------------------

def test_spring_attributes_excluded_via_cypher():
    conn = _conn_with_side_effects([], [(0,)])
    find_dead_code(conn)
    cypher = conn.query.call_args_list[0].args[0]
    assert '"Bean"' in cypher
    assert '"PostConstruct"' in cypher
    assert '"RequestMapping"' in cypher
    assert '"GetMapping"' in cypher
    assert '"Scheduled"' in cypher


# ---------------------------------------------------------------------------
# Regression: limit parameter truncates methods list
# ---------------------------------------------------------------------------

def test_limit_truncates_methods_list():
    dead_rows = [(f"Ns.Foo{i}", f"/foo{i}.cs", i) for i in range(10)]
    conn = _conn_with_side_effects(dead_rows, [(50,)])
    result = find_dead_code(conn, limit=3)
    assert len(result["methods"]) == 3
    assert result["stats"]["dead_count"] == 10
    assert result["stats"]["truncated"] is True
    assert result["stats"]["limit"] == 3


def test_limit_not_truncated_when_under():
    dead_rows = [("Ns.Foo", "/foo.cs", 1)]
    conn = _conn_with_side_effects(dead_rows, [(5,)])
    result = find_dead_code(conn, limit=100)
    assert len(result["methods"]) == 1
    assert result["stats"]["truncated"] is False


# ---------------------------------------------------------------------------
# Regression: C# override methods excluded via attributes check
# (gRPC service methods override unindexed generated base classes,
# so they have no OVERRIDES edge — the "override" keyword in
# m.attributes must catch them instead)
# ---------------------------------------------------------------------------

def test_override_attribute_excluded_via_cypher():
    conn = _conn_with_side_effects([], [(0,)])
    find_dead_code(conn)
    cypher = conn.query.call_args_list[0].args[0]
    assert 'CONTAINS \'"override"\'' in cypher
