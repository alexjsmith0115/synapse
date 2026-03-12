from unittest.mock import MagicMock

from synapse.graph.analysis import analyze_change_impact


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
