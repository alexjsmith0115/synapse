from unittest.mock import MagicMock

from synapse.graph.analysis import (
    analyze_change_impact,
    find_interface_contract,
    find_type_impact,
)


def _conn(return_value: list) -> MagicMock:
    conn = MagicMock()
    conn.query.return_value = return_value
    return conn


def test_analyze_change_impact_aggregates() -> None:
    conn = MagicMock()
    conn.query.side_effect = [
        [["Direct.Caller", "/proj/D.cs"]],  # direct callers
        [["Trans.Caller", "/proj/T.cs"]],  # transitive callers
        [["Test.Method", "/tests/T.cs"]],  # test coverage
    ]
    result = analyze_change_impact(conn, "Svc.Method")
    assert result["target"] == "Svc.Method"
    assert len(result["direct_callers"]) == 1
    assert len(result["transitive_callers"]) == 1
    assert len(result["test_coverage"]) == 1
    assert result["total_affected"] == 3


def test_analyze_change_impact_deduplicates_total() -> None:
    conn = MagicMock()
    conn.query.side_effect = [
        [["Shared.Caller", "/proj/S.cs"]],  # direct
        [["Shared.Caller", "/proj/S.cs"]],  # also in transitive
        [],  # no tests
    ]
    result = analyze_change_impact(conn, "Svc.Method")
    assert result["total_affected"] == 1  # deduplicated


def test_analyze_change_impact_empty() -> None:
    conn = MagicMock()
    conn.query.side_effect = [[], [], []]
    result = analyze_change_impact(conn, "Isolated.Method")
    assert result["direct_callers"] == []
    assert result["total_affected"] == 0


def test_find_interface_contract_returns_siblings() -> None:
    conn = _conn([
        ["Ns.IService", "Ns.IService.Do", "OtherImpl", "/proj/Other.cs"],
    ])
    result = find_interface_contract(conn, "Ns.MyImpl.Do")
    assert result["method"] == "Ns.MyImpl.Do"
    assert result["interface"] == "Ns.IService"
    assert result["contract_method"] == "Ns.IService.Do"
    assert len(result["sibling_implementations"]) == 1


def test_find_interface_contract_no_interface() -> None:
    conn = _conn([])
    result = find_interface_contract(conn, "Standalone.Method")
    assert result["sibling_implementations"] == []


def test_find_type_impact_categorizes() -> None:
    conn = _conn([
        ["Svc.Method", "/proj/Svc.cs", "prod"],
        ["Test.Verify", "/tests/Verify.cs", "test"],
    ])
    result = find_type_impact(conn, "Ns.MyModel")
    assert result["type"] == "Ns.MyModel"
    assert result["prod_count"] == 1
    assert result["test_count"] == 1
    assert len(result["references"]) == 2


def test_find_type_impact_empty() -> None:
    conn = _conn([])
    result = find_type_impact(conn, "Unused.Type")
    assert result["references"] == []
    assert result["prod_count"] == 0
    assert result["test_count"] == 0
