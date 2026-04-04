from unittest.mock import MagicMock

from synapps.graph.analysis import (
    analyze_change_impact,
    audit_architecture,
    find_interface_contract,
    find_type_impact,
)
from synapps.graph.lookups import _TEST_PATH_PATTERN
from conftest import _MockNode


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


def test_analyze_change_impact_returns_expected_sections() -> None:
    conn = MagicMock()
    conn.query.side_effect = [
        [["Direct.Caller", "/proj/D.cs"]],  # direct callers
        [["Trans.Caller", "/proj/T.cs"]],  # transitive callers
        [["Test.Method", "/tests/T.cs"]],  # test coverage
        [],  # callees (direct)
        [],  # callees (interface dispatch)
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
        [],  # callees (direct)
        [],  # callees (interface dispatch)
    ]
    result = analyze_change_impact(conn, "Svc.Method")
    assert result["total_affected"] == 1  # deduplicated


def test_analyze_change_impact_empty() -> None:
    conn = MagicMock()
    conn.query.side_effect = [[], [], [], [], []]
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


def test_find_interface_contract_via_overrides_chain() -> None:
    """Regression: Dog.speak → OVERRIDES → Animal.speak → IMPLEMENTS → IAnimal.speak.

    find_interface_contract must walk OVERRIDES edges at the method level
    to reach the IMPLEMENTS edge, not just look for a direct IMPLEMENTS.
    """
    conn = MagicMock()
    conn.query.side_effect = [
        # First query: now traverses OVERRIDES*0.. before IMPLEMENTS
        [["Ns.IAnimal", "Ns.IAnimal.speak", "Ns.Dog"]],
        # Second query: siblings
        [["Cat", "/proj/Cat.py"]],
    ]
    result = find_interface_contract(conn, "Ns.Dog.speak")
    assert result["interface"] == "Ns.IAnimal"
    assert result["contract_method"] == "Ns.IAnimal.speak"
    assert len(result["sibling_implementations"]) == 1
    # Verify the first query uses OVERRIDES traversal
    first_query = conn.query.call_args_list[0][0][0]
    assert "OVERRIDES" in first_query, (
        "Query must traverse OVERRIDES edges to find IMPLEMENTS"
    )


def test_find_interface_contract_no_interface() -> None:
    conn = _conn([])
    result = find_interface_contract(conn, "Standalone.Method")
    assert result["sibling_implementations"] == []


def test_find_type_impact_categorizes() -> None:
    conn = MagicMock()
    conn.query.side_effect = [
        [[None]],  # Query 1: no interfaces
        [
            ["Svc.Method", "/proj/Svc.cs", "prod"],
            ["Test.Verify", "/tests/Verify.cs", "test"],
        ],  # Query 2: references
    ]
    result = find_type_impact(conn, "Ns.MyModel")
    assert result["type"] == "Ns.MyModel"
    assert result["prod_count"] == 1
    assert result["test_count"] == 1
    assert len(result["references"]) == 2


def test_find_type_impact_empty() -> None:
    conn = MagicMock()
    conn.query.side_effect = [[[None]], []]
    result = find_type_impact(conn, "Unused.Type")
    assert result["references"] == []
    assert result["prod_count"] == 0
    assert result["test_count"] == 0


def test_find_type_impact_includes_interface_mediated_dependents() -> None:
    """Dependents that reference an interface the type implements are included."""
    conn = MagicMock()
    conn.query.side_effect = [
        [["Ns.IFooService"]],  # Query 1: target implements IFooService
        [
            ["FooService.Init", "/src/FooService.cs", "prod"],   # direct reference
            ["Controller.Action", "/src/Controller.cs", "prod"], # via IFooService
        ],  # Query 2: references to Ns.FooService or Ns.IFooService
    ]
    result = find_type_impact(conn, "Ns.FooService")
    assert result["prod_count"] == 2
    assert result["test_count"] == 0
    # Verify Query 2 was called with both type names
    q2_params = conn.query.call_args_list[1][0][1]
    assert "Ns.FooService" in q2_params["type_names"]
    assert "Ns.IFooService" in q2_params["type_names"]


def test_find_type_impact_no_interfaces_uses_direct_only() -> None:
    """When a type implements no interfaces, only direct REFERENCES are returned."""
    conn = MagicMock()
    conn.query.side_effect = [
        [[None]],  # Query 1: no interfaces (OPTIONAL MATCH returns None row)
        [["Direct.User", "/src/Direct.cs", "prod"]],
    ]
    result = find_type_impact(conn, "Ns.BarService")
    q2_params = conn.query.call_args_list[1][0][1]
    assert q2_params["type_names"] == ["Ns.BarService"]
    assert result["prod_count"] == 1


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
    conn.query.side_effect = [[], [], [], [], []]
    analyze_change_impact(conn, "Ns.Svc.Method")
    direct_cypher = conn.query.call_args_list[0][0][0]
    assert "NOT" in direct_cypher and "test_pattern" in direct_cypher, (
        "direct_callers query must filter out test files via regex"
    )


def test_analyze_change_impact_direct_callers_uses_regex_not_substring() -> None:
    """direct_callers filter must use _TEST_PATH_PATTERN regex, not CONTAINS 'Tests'."""
    conn = MagicMock()
    conn.query.side_effect = [[], [], [], [], []]
    analyze_change_impact(conn, "Ns.Svc.Method")
    direct_cypher = conn.query.call_args_list[0][0][0]
    params = conn.query.call_args_list[0][0][1]
    assert "CONTAINS" not in direct_cypher, "Should use regex, not CONTAINS"
    assert "test_pattern" in params
    assert params["test_pattern"] == _TEST_PATH_PATTERN


def test_find_type_impact_uses_regex_not_substring() -> None:
    """Prod/test categorization must use _TEST_PATH_PATTERN, not CONTAINS 'Tests'."""
    conn = MagicMock()
    conn.query.side_effect = [[[None]], []]
    find_type_impact(conn, "Ns.MyType")
    q2_cypher = conn.query.call_args_list[1][0][0]
    params = conn.query.call_args_list[1][0][1]
    assert "CONTAINS" not in q2_cypher, "Should use regex, not CONTAINS"
    assert "test_pattern" in params
    assert params["test_pattern"] == _TEST_PATH_PATTERN


def test_analyze_change_impact_transitive_includes_interface_dispatch() -> None:
    """Transitive query must cross the interface dispatch gap."""
    conn = MagicMock()
    conn.query.side_effect = [[], [], [], [], []]
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
    conn.query.side_effect = [[], [], [], [], []]
    analyze_change_impact(conn, "Ns.Svc.Method")
    direct_cypher = conn.query.call_args_list[0][0][0]
    assert "IMPLEMENTS" in direct_cypher, (
        "direct_callers query must accept callers that reach the method "
        "via its interface (IMPLEMENTS edge)"
    )


def test_analyze_change_impact_tests_includes_interface_dispatch() -> None:
    """test_coverage must capture tests that call through a controller→interface path."""
    conn = MagicMock()
    conn.query.side_effect = [[], [], [], [], []]
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


def test_analyze_change_impact_includes_direct_callees() -> None:
    """Result should include direct_callees from find_callees."""
    callee_node = _MockNode(["Method"], {"full_name": "Repo.Save", "file_path": "/proj/Repo.cs"})
    conn = MagicMock()
    conn.query.side_effect = [
        [],  # direct callers
        [],  # transitive callers
        [],  # test coverage
        [[callee_node]],  # callees (direct)
        [],  # callees (interface dispatch)
    ]
    result = analyze_change_impact(conn, "Svc.Method")
    assert "direct_callees" in result
    assert len(result["direct_callees"]) == 1
    assert result["direct_callees"][0] == {"full_name": "Repo.Save", "file_path": "/proj/Repo.cs"}


def test_analyze_change_impact_callees_not_in_total_affected() -> None:
    """Callees are downstream context, not 'affected' — total_affected stays upstream-only."""
    callee_node = _MockNode(["Method"], {"full_name": "Repo.Save", "file_path": "/proj/Repo.cs"})
    conn = MagicMock()
    conn.query.side_effect = [
        [["Direct.Caller", "/proj/D.cs"]],  # direct callers
        [],  # transitive
        [],  # tests
        [[callee_node]],  # callees (direct)
        [],  # callees (interface dispatch)
    ]
    result = analyze_change_impact(conn, "Svc.Method")
    assert result["total_affected"] == 1  # only the caller, not the callee


def test_audit_untested_services_uses_regex_pattern() -> None:
    """untested_services rule must use regex test_pattern, not CONTAINS 'Tests'."""
    conn = _conn([])
    audit_architecture(conn, "untested_services")
    cypher = conn.query.call_args[0][0]
    params = conn.query.call_args[0][1] if len(conn.query.call_args[0]) > 1 else {}
    assert "CONTAINS 'Tests'" not in cypher, "Should use regex, not CONTAINS"
    assert "test_pattern" in cypher


def test_analyze_change_impact_tests_uses_regex_not_contains() -> None:
    """test_coverage query must use regex pattern, not CONTAINS 'Tests'."""
    conn = MagicMock()
    conn.query.side_effect = [[], [], [], [], []]
    analyze_change_impact(conn, "Ns.Svc.Method")
    tests_cypher = conn.query.call_args_list[2][0][0]
    assert "CONTAINS" not in tests_cypher, "Should use regex, not CONTAINS"
    assert "test_pattern" in tests_cypher


def test_analyze_change_impact_transitive_excludes_tests() -> None:
    """transitive_callers must exclude test files via _TEST_PATH_PATTERN."""
    conn = MagicMock()
    conn.query.side_effect = [[], [], [], [], []]
    analyze_change_impact(conn, "Ns.Svc.Method")
    transitive_cypher = conn.query.call_args_list[1][0][0]
    params = conn.query.call_args_list[1][0][1]
    assert "NOT" in transitive_cypher and "test_pattern" in transitive_cypher, (
        "transitive_callers query must filter out test files via regex"
    )
    assert params["test_pattern"] == _TEST_PATH_PATTERN
