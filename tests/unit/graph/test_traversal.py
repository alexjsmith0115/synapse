from unittest.mock import MagicMock

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
