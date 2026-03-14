from unittest.mock import MagicMock

from synapse.graph.analysis import (
    analyze_change_impact,
    audit_architecture,
    find_interface_contract,
    find_type_impact,
)


def _conn(return_value: list) -> MagicMock:
    conn = MagicMock()
    conn.query.return_value = return_value
    return conn


def _record(keys: list[str], values: list) -> MagicMock:
    """Build a mock neo4j.Record so dict(r) produces a named-key dict."""
    data = dict(zip(keys, values))
    row = MagicMock()
    row.keys.return_value = keys
    row.__getitem__ = lambda self, k: data[k]
    return row


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
    conn = MagicMock()
    conn.query.side_effect = [
        # First query: contract found
        [["Ns.IService", "Ns.IService.Do", "Ns.MyImpl"]],
        # Second query: one sibling
        [["OtherImpl", "/proj/Other.cs"]],
    ]
    result = find_interface_contract(conn, "Ns.MyImpl.Do")
    assert result["method"] == "Ns.MyImpl.Do"
    assert result["interface"] == "Ns.IService"
    assert result["contract_method"] == "Ns.IService.Do"
    assert len(result["sibling_implementations"]) == 1


def test_find_interface_contract_no_siblings() -> None:
    """Returns the interface and contract even when there are no other implementations."""
    conn = MagicMock()
    conn.query.side_effect = [
        # First query: finds interface and contract method
        [["Ns.IService", "Ns.IService.Do", "Ns.MyImpl"]],
        # Second query: no siblings
        [],
    ]
    result = find_interface_contract(conn, "Ns.MyImpl.Do")
    assert result["interface"] == "Ns.IService"
    assert result["contract_method"] == "Ns.IService.Do"
    assert result["sibling_implementations"] == []


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


def test_audit_layering_violations() -> None:
    row = _record(
        ["ctrl.name", "m.name", "db.full_name"],
        ["UsersController", "GetAll", "AppDbContext.Users"],
    )
    conn = _conn([row])
    result = audit_architecture(conn, "layering_violations")
    assert result["rule"] == "layering_violations"
    assert result["count"] == 1
    assert len(result["violations"]) == 1


def test_audit_untested_services() -> None:
    row = _record(
        ["svc.name", "svc.file_path"],
        ["UserService", "/proj/Services/UserService.cs"],
    )
    conn = _conn([row])
    result = audit_architecture(conn, "untested_services")
    assert result["rule"] == "untested_services"
    assert result["count"] == 1



def test_audit_invalid_rule_raises() -> None:
    import pytest
    conn = _conn([])
    with pytest.raises(ValueError, match="Unknown rule"):
        audit_architecture(conn, "nonexistent_rule")


def test_audit_empty_results() -> None:
    conn = _conn([])
    result = audit_architecture(conn, "layering_violations")
    assert result["count"] == 0
    assert result["violations"] == []


def test_analyze_change_impact_direct_callers_excludes_tests() -> None:
    """direct_callers must not include test methods; test_coverage is the correct field."""
    conn = MagicMock()
    conn.query.side_effect = [[], [], []]
    analyze_change_impact(conn, "Ns.Svc.Method")
    direct_cypher = conn.query.call_args_list[0][0][0]
    assert "Tests" in direct_cypher and "NOT" in direct_cypher, (
        "direct_callers query must filter out test files"
    )


def test_analyze_change_impact_transitive_includes_interface_dispatch() -> None:
    """Transitive query must cross the interface dispatch gap."""
    conn = MagicMock()
    conn.query.side_effect = [[], [], []]
    analyze_change_impact(conn, "Ns.Svc.Method")
    transitive_cypher = conn.query.call_args_list[1][0][0]
    assert "IMPLEMENTS" in transitive_cypher, (
        "Transitive callers query must accept callers that reach the method "
        "via its interface (IMPLEMENTS edge)"
    )


def test_analyze_change_impact_direct_includes_interface_dispatch() -> None:
    """direct_callers must include callers that call through an interface method.

    In DI-heavy codebases a controller calls IService.Method, not the concrete
    ServiceImpl.Method directly.  The IMPLEMENTS edge links the concrete method
    to the interface method so the query must follow it.
    """
    conn = MagicMock()
    conn.query.side_effect = [[], [], []]
    analyze_change_impact(conn, "Ns.Svc.Method")
    direct_cypher = conn.query.call_args_list[0][0][0]
    assert "IMPLEMENTS" in direct_cypher, (
        "direct_callers query must accept callers that reach the method "
        "via its interface (IMPLEMENTS edge)"
    )


def test_analyze_change_impact_tests_includes_interface_dispatch() -> None:
    """test_coverage must capture tests that call through a controller→interface path."""
    conn = MagicMock()
    conn.query.side_effect = [[], [], []]
    analyze_change_impact(conn, "Ns.Svc.Method")
    tests_cypher = conn.query.call_args_list[2][0][0]
    assert "IMPLEMENTS" in tests_cypher, (
        "test_coverage query must accept tests that reach the method "
        "via its interface (IMPLEMENTS edge)"
    )


def test_audit_architecture_violations_have_named_keys():
    """Violations should use column names as keys, not integers."""
    # Simulate a neo4j.Record: dict() uses keys() + __getitem__, not __iter__
    mock_row = MagicMock()
    mock_row.keys.return_value = ["ctrl.name", "m.name", "db.full_name"]
    mock_row.__getitem__ = lambda self, k: {"ctrl.name": "MyCtrl", "m.name": "MyMethod", "db.full_name": "SomeDb.Save"}[k]

    conn = MagicMock()
    conn.query.return_value = [mock_row]

    result = audit_architecture(conn, "layering_violations")
    assert len(result["violations"]) == 1
    violation = result["violations"][0]
    assert 0 not in violation, "violations must not use integer keys"
    assert "ctrl.name" in violation, "violations must use column names as keys"
    assert violation["ctrl.name"] == "MyCtrl"
