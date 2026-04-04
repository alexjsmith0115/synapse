from unittest.mock import MagicMock

from synapps.graph.lookups import _TEST_PATH_PATTERN
from synapps.graph.traversal import find_entry_points, get_call_depth, trace_call_chain


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


def test_find_entry_points_returns_paths() -> None:
    conn = MagicMock()
    conn.query.side_effect = [
        [[["Controller.Action", "Svc.Do", "Repo.Save"]]],  # root query
        [],  # attributed query
    ]
    result = find_entry_points(conn, "Repo.Save")
    assert len(result["entry_points"]) == 1
    assert result["entry_points"][0]["entry"] == "Controller.Action"
    assert result["entry_points"][0]["path"] == ["Controller.Action", "Svc.Do", "Repo.Save"]
    assert result["target"] == "Repo.Save"


def test_find_entry_points_empty() -> None:
    conn = MagicMock()
    conn.query.side_effect = [[], []]
    result = find_entry_points(conn, "Orphan.Method")
    assert result["entry_points"] == []


def test_get_call_depth_returns_callees() -> None:
    conn = _conn([
        ["Svc.DoA", "/proj/Svc.cs", 1],
        ["Repo.Save", "/proj/Repo.cs", 2],
    ])
    result = get_call_depth(conn, "Controller.Action", depth=3)
    assert result["root"] == "Controller.Action"
    assert len(result["callees"]) == 2
    assert result["callees"][0] == {"full_name": "Svc.DoA", "file_path": "/proj/Svc.cs", "depth": 1}
    assert result["depth_limit"] == 3


def test_get_call_depth_empty() -> None:
    conn = _conn([])
    result = get_call_depth(conn, "Leaf.Method", depth=2)
    assert result["callees"] == []


def test_trace_call_chain_traverses_dispatches_to() -> None:
    """Query must traverse DISPATCHES_TO to cross interface dispatch boundaries mid-chain."""
    conn = _conn([])
    trace_call_chain(conn, "A.Controller.Create", "A.Service.CreateAsync")
    cypher = conn.query.call_args[0][0]
    assert "DISPATCHES_TO" in cypher, (
        "trace_call_chain must traverse DISPATCHES_TO edges so paths can cross "
        "interface dispatch boundaries (e.g. Controller→IService→ConcreteService→DB)"
    )


def test_find_entry_points_traverses_dispatches_to() -> None:
    """Query must traverse DISPATCHES_TO to find entry points that reach $method via an interface."""
    conn = MagicMock()
    conn.query.side_effect = [[], []]
    find_entry_points(conn, "A.Service.CreateAsync")
    cypher = conn.query.call_args_list[0][0][0]
    assert "DISPATCHES_TO" in cypher, (
        "find_entry_points must traverse DISPATCHES_TO edges so controller→interface→service "
        "paths are included"
    )


def test_find_entry_points_exclude_pattern_in_cypher() -> None:
    """exclude_pattern uses NOT EXISTS to filter callers, not a post-filter on roots."""
    conn = MagicMock()
    conn.query.side_effect = [[], []]
    find_entry_points(conn, "Svc.Do", exclude_pattern=".*\\.Tests\\..*")
    cypher = conn.query.call_args_list[0][0][0]
    params = conn.query.call_args_list[0][0][1]
    assert "NOT EXISTS" in cypher
    assert "$exclude_pattern" in cypher
    assert params["exclude_pattern"] == ".*\\.Tests\\..*"


def test_find_entry_points_no_exclude_clause_when_pattern_empty() -> None:
    """$exclude_pattern is always passed; empty string makes it a no-op."""
    conn = MagicMock()
    conn.query.side_effect = [[], []]
    find_entry_points(conn, "Svc.Do")
    params = conn.query.call_args_list[0][0][1]
    assert params["exclude_pattern"] == ""


def test_find_entry_points_exclude_promotes_callers_to_roots() -> None:
    """When a caller matches the exclude pattern, the Cypher uses NOT EXISTS so its
    own callers (e.g. controller actions) are evaluated as potential roots instead."""
    conn = MagicMock()
    conn.query.side_effect = [
        [[["Controller.Action", "Service.Method"]]],  # root query
        [],  # attributed query
    ]
    result = find_entry_points(conn, "Service.Method", exclude_pattern=".*Test.*")
    cypher = conn.query.call_args_list[0][0][0]
    # NOT EXISTS is the structural indicator that callers are filtered during traversal
    assert "NOT EXISTS" in cypher
    # r[0][0] is the entry point
    assert result["entry_points"][0]["entry"] == "Controller.Action"


def test_find_entry_points_deduplicates_by_entry() -> None:
    """Query uses ORDER BY + collect to return one path per entry (shortest first)."""
    conn = MagicMock()
    conn.query.side_effect = [[], []]
    find_entry_points(conn, "Repo.Save")
    cypher = conn.query.call_args_list[0][0][0]
    assert "ORDER BY size(path)" in cypher
    assert "collect(path)[0]" in cypher


def test_get_call_depth_traverses_dispatches_to() -> None:
    """get_call_depth must traverse DISPATCHES_TO so callees behind interface dispatch are included."""
    conn = _conn([])
    get_call_depth(conn, "A.Service.CreateAsync", depth=3)
    cypher = conn.query.call_args[0][0]
    assert "DISPATCHES_TO" in cypher


def test_trace_call_chain_crosses_interface_boundary() -> None:
    """Path crossing an interface dispatch node is returned correctly."""
    # Simulates: Controller.Create -[CALLS]-> IService.CreateAsync
    #            -[DISPATCHES_TO]-> Service.CreateAsync
    conn = _conn([[["A.Controller.Create", "A.IService.CreateAsync", "A.Service.CreateAsync"]]])
    result = trace_call_chain(conn, "A.Controller.Create", "A.Service.CreateAsync")
    assert result["paths"] == [
        ["A.Controller.Create", "A.IService.CreateAsync", "A.Service.CreateAsync"]
    ]


def test_find_entry_points_excludes_tests_by_default() -> None:
    """By default, entry points whose file_path matches the test path pattern are excluded."""
    conn = MagicMock()
    conn.query.side_effect = [[], []]
    find_entry_points(conn, "Svc.Do")
    params = conn.query.call_args_list[0][0][1]
    cypher = conn.query.call_args_list[0][0][0]
    assert params["test_pattern"] == _TEST_PATH_PATTERN
    assert "$test_pattern" in cypher


def test_find_entry_points_include_tests_when_requested() -> None:
    """When exclude_test_callers=False, test_pattern is empty and no test filtering occurs."""
    conn = MagicMock()
    conn.query.side_effect = [[], []]
    find_entry_points(conn, "Svc.Do", exclude_test_callers=False)
    params = conn.query.call_args_list[0][0][1]
    assert params["test_pattern"] == ""


def test_find_entry_points_accepts_both_exclude_pattern_and_test_pattern() -> None:
    """Both exclude_pattern and test_pattern can be active simultaneously."""
    conn = MagicMock()
    conn.query.side_effect = [[], []]
    find_entry_points(conn, "Svc.Do", exclude_pattern=".*\\.Tests\\..*", exclude_test_callers=True)
    params = conn.query.call_args_list[0][0][1]
    assert params["exclude_pattern"] == ".*\\.Tests\\..*"
    assert params["test_pattern"] == _TEST_PATH_PATTERN


def test_find_entry_points_test_pattern_filters_callers_in_not_exists() -> None:
    """When exclude_test_callers=True, the NOT EXISTS clause must also filter
    callers by $test_pattern so methods whose only callers are in test paths
    are recognized as roots."""
    conn = MagicMock()
    conn.query.side_effect = [[], []]
    find_entry_points(conn, "Svc.Do", exclude_test_callers=True)
    cypher = conn.query.call_args_list[0][0][0]
    # Both NOT EXISTS and $test_pattern must appear, and test_pattern must come
    # after NOT EXISTS (i.e., it's used inside the existence check)
    assert "NOT EXISTS" in cypher
    assert "$test_pattern" in cypher
    assert cypher.index("NOT EXISTS") < cypher.index("$test_pattern"), (
        "NOT EXISTS block must reference $test_pattern so test callers "
        "don't prevent non-test methods from being recognized as roots."
    )


def test_find_entry_points_test_pattern_is_empty_when_disabled() -> None:
    """When exclude_test_callers=False, test_pattern is empty string, making all test-path clauses no-ops."""
    conn = MagicMock()
    conn.query.side_effect = [[], []]
    find_entry_points(conn, "Svc.Do", exclude_test_callers=False)
    params = conn.query.call_args_list[0][0][1]
    assert params["test_pattern"] == ""


def test_find_entry_points_attributed_controller() -> None:
    """Controller methods with [ApiController] attribute are entry points even with callers."""
    conn = MagicMock()
    conn.query.side_effect = [
        [],  # First query (root callers) returns nothing
        [[["Ns.Controller.Action", "Ns.Svc.Do"]]],  # Second query (attributed) returns a path
    ]
    result = find_entry_points(conn, "Ns.Svc.Do")
    assert len(result["entry_points"]) == 1
    assert result["entry_points"][0]["entry"] == "Ns.Controller.Action"


def test_find_entry_points_attributed_deduplicates_with_roots() -> None:
    """If a method appears in both root and attributed results, keep shortest path."""
    conn = MagicMock()
    conn.query.side_effect = [
        [[["Ns.Controller.Action", "Ns.Svc.Do"]]],  # Root query
        [[["Ns.Controller.Action", "Ns.Mid.Call", "Ns.Svc.Do"]]],  # Attributed query (longer path)
    ]
    result = find_entry_points(conn, "Ns.Svc.Do")
    assert len(result["entry_points"]) == 1
    assert result["entry_points"][0]["path"] == ["Ns.Controller.Action", "Ns.Svc.Do"]


def test_find_entry_points_attributed_query_checks_attributes() -> None:
    """The attributed query must check for controller/HTTP verb attributes."""
    conn = MagicMock()
    conn.query.side_effect = [[], []]
    find_entry_points(conn, "Ns.Svc.Do")
    assert conn.query.call_count == 2
    attributed_cypher = conn.query.call_args_list[1][0][0]
    assert "attributes" in attributed_cypher
    assert "ApiController" in attributed_cypher
