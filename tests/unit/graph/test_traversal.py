from unittest.mock import MagicMock

from synapse.graph.lookups import _TEST_PATH_PATTERN
from synapse.graph.traversal import find_entry_points, get_call_depth, trace_call_chain


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
    conn = _conn([[["Controller.Action", "Svc.Do", "Repo.Save"]]])
    result = find_entry_points(conn, "Repo.Save")
    assert len(result["entry_points"]) == 1
    assert result["entry_points"][0]["entry"] == "Controller.Action"
    assert result["entry_points"][0]["path"] == ["Controller.Action", "Svc.Do", "Repo.Save"]
    assert result["target"] == "Repo.Save"


def test_find_entry_points_empty() -> None:
    conn = _conn([])
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
    conn = _conn([])
    find_entry_points(conn, "A.Service.CreateAsync")
    cypher = conn.query.call_args[0][0]
    assert "DISPATCHES_TO" in cypher, (
        "find_entry_points must traverse DISPATCHES_TO edges so controller→interface→service "
        "paths are included"
    )


def test_find_entry_points_exclude_pattern_in_cypher() -> None:
    """exclude_pattern uses NOT EXISTS to filter callers, not a post-filter on roots."""
    conn = _conn([])
    find_entry_points(conn, "Svc.Do", exclude_pattern=".*\\.Tests\\..*")
    cypher = conn.query.call_args[0][0]
    params = conn.query.call_args[0][1]
    assert "NOT EXISTS" in cypher
    assert "$exclude_pattern" in cypher
    assert params["exclude_pattern"] == ".*\\.Tests\\..*"


def test_find_entry_points_no_exclude_clause_when_pattern_empty() -> None:
    """$exclude_pattern is always passed; empty string makes it a no-op."""
    conn = _conn([])
    find_entry_points(conn, "Svc.Do")
    params = conn.query.call_args[0][1]
    assert params["exclude_pattern"] == ""


def test_find_entry_points_exclude_promotes_callers_to_roots() -> None:
    """When a caller matches the exclude pattern, the Cypher uses NOT EXISTS so its
    own callers (e.g. controller actions) are evaluated as potential roots instead."""
    conn = _conn([[["Controller.Action", "Service.Method"]]])
    result = find_entry_points(conn, "Service.Method", exclude_pattern=".*Test.*")
    cypher = conn.query.call_args[0][0]
    # NOT EXISTS is the structural indicator that callers are filtered during traversal
    assert "NOT EXISTS" in cypher
    # r[0][0] is the entry point
    assert result["entry_points"][0]["entry"] == "Controller.Action"


def test_find_entry_points_deduplicates_by_entry() -> None:
    """Query uses ORDER BY + collect to return one path per entry (shortest first)."""
    conn = _conn([])
    find_entry_points(conn, "Repo.Save")
    cypher = conn.query.call_args[0][0]
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
    conn = _conn([])
    find_entry_points(conn, "Svc.Do")
    params = conn.query.call_args[0][1]
    cypher = conn.query.call_args[0][0]
    assert params["test_pattern"] == _TEST_PATH_PATTERN
    assert "$test_pattern" in cypher


def test_find_entry_points_include_tests_when_requested() -> None:
    """When exclude_test_callers=False, test_pattern is empty and no test filtering occurs."""
    conn = _conn([])
    find_entry_points(conn, "Svc.Do", exclude_test_callers=False)
    params = conn.query.call_args[0][1]
    assert params["test_pattern"] == ""


def test_find_entry_points_exclude_tests_composes_with_exclude_pattern() -> None:
    """Both exclude_pattern and test_pattern can be active simultaneously."""
    conn = _conn([])
    find_entry_points(conn, "Svc.Do", exclude_pattern=".*\\.Tests\\..*", exclude_test_callers=True)
    params = conn.query.call_args[0][1]
    assert params["exclude_pattern"] == ".*\\.Tests\\..*"
    assert params["test_pattern"] == _TEST_PATH_PATTERN


def test_find_entry_points_test_pattern_filters_callers_in_not_exists() -> None:
    """When exclude_test_callers=True, the NOT EXISTS clause must also filter
    callers by $test_pattern so methods whose only callers are in test paths
    are recognized as roots."""
    conn = _conn([])
    find_entry_points(conn, "Svc.Do", exclude_test_callers=True)
    cypher = conn.query.call_args[0][0]
    # Extract the NOT EXISTS block
    not_exists_start = cypher.index("NOT EXISTS")
    brace_depth = 0
    not_exists_block = ""
    for i, ch in enumerate(cypher[not_exists_start:]):
        if ch == "{":
            brace_depth += 1
        elif ch == "}":
            brace_depth -= 1
            if brace_depth == 0:
                not_exists_block = cypher[not_exists_start:not_exists_start + i + 1]
                break
    assert "$test_pattern" in not_exists_block, (
        "NOT EXISTS block must filter callers by $test_pattern so test callers "
        "don't prevent non-test methods from being recognized as roots. "
        f"Got NOT EXISTS block: {not_exists_block}"
    )


def test_find_entry_points_no_test_pattern_in_not_exists_when_disabled() -> None:
    """When exclude_test_callers=False, test_pattern is empty so the clause is a no-op."""
    conn = _conn([])
    find_entry_points(conn, "Svc.Do", exclude_test_callers=False)
    params = conn.query.call_args[0][1]
    assert params["test_pattern"] == ""
