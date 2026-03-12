from unittest.mock import MagicMock

from synapse.graph.lookups import resolve_full_name


def _conn(return_value: list) -> MagicMock:
    conn = MagicMock()
    conn.query.return_value = return_value
    return conn


def test_exact_match_returns_string() -> None:
    conn = _conn([["Ns.MyClass"]])
    result = resolve_full_name(conn, "Ns.MyClass")
    assert result == "Ns.MyClass"


def test_exact_match_without_dot() -> None:
    """Symbols without namespaces (e.g. 'Animal') should exact-match first."""
    conn = _conn([["Animal"]])
    result = resolve_full_name(conn, "Animal")
    assert result == "Animal"
    # Should have tried exact match, not just suffix
    cypher = conn.query.call_args_list[0][0][0]
    assert "full_name" in cypher


def test_suffix_fallback_single_match() -> None:
    conn = MagicMock()
    conn.query.side_effect = [[], [["Ns.Sub.MyClass", ["Class"]]]]
    result = resolve_full_name(conn, "MyClass")
    assert result == "Ns.Sub.MyClass"


def test_suffix_fallback_multiple_matches() -> None:
    conn = MagicMock()
    conn.query.side_effect = [[], [["A.MyClass", ["Class"]], ["B.MyClass", ["Class"]]]]
    result = resolve_full_name(conn, "MyClass")
    assert result == ["A.MyClass", "B.MyClass"]


def test_no_match_returns_original() -> None:
    conn = MagicMock()
    conn.query.side_effect = [[], []]
    result = resolve_full_name(conn, "NoSuchThing")
    assert result == "NoSuchThing"


def test_exact_match_skips_suffix() -> None:
    """If exact match succeeds, suffix match should not be attempted."""
    conn = _conn([["Ns.MyClass"]])
    resolve_full_name(conn, "Ns.MyClass")
    assert conn.query.call_count == 1


def test_suffix_fallback_prefers_class_over_method() -> None:
    """When suffix matches both a Class and a Method, return the Class unambiguously."""
    conn = MagicMock()
    conn.query.side_effect = [
        [],  # exact match: nothing
        [   # suffix match: Class node + constructor Method node
            ["Ns.Services.MeetingService", ["Class"]],
            ["Ns.Services.MeetingService.MeetingService", ["Method"]],
        ],
    ]
    result = resolve_full_name(conn, "MeetingService")
    assert result == "Ns.Services.MeetingService", (
        "Should resolve to the Class node, not raise an ambiguity error"
    )
