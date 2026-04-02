from unittest.mock import MagicMock

import pytest

from synapps.graph.lookups import resolve_full_name, suggest_similar_names
from synapps.service import SynappsService


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


def test_no_match_returns_none() -> None:
    conn = MagicMock()
    conn.query.side_effect = [[], []]
    result = resolve_full_name(conn, "NoSuchThing")
    assert result is None


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


# ---------------------------------------------------------------------------
# suggest_similar_names
# ---------------------------------------------------------------------------

def test_suggest_similar_names_returns_matches() -> None:
    conn = MagicMock()
    conn.query.return_value = [["order.service.OrderServiceImpl.create"]]
    result = suggest_similar_names(conn, "createOrder")
    assert len(result) == 1
    assert "create" in result[0]


def test_suggest_similar_names_empty_when_no_match() -> None:
    conn = MagicMock()
    conn.query.return_value = []
    result = suggest_similar_names(conn, "xyzNonexistent")
    assert result == []


# ---------------------------------------------------------------------------
# _resolve raises ValueError with suggestions for not-found symbols
# ---------------------------------------------------------------------------

def test_resolve_not_found_raises_with_suggestions() -> None:
    conn = MagicMock()
    # resolve_full_name: exact match → nothing, suffix match → nothing (returns None)
    # suggest_similar_names: returns suggestions
    conn.query.side_effect = [
        [],  # exact match
        [],  # suffix match
        [["order.service.OrderServiceImpl.create"]],  # suggest_similar_names
    ]
    svc = SynappsService(conn)
    with pytest.raises(ValueError, match="Did you mean"):
        svc._resolve("createOrder")


def test_resolve_not_found_raises_without_suggestions() -> None:
    conn = MagicMock()
    conn.query.side_effect = [
        [],  # exact match
        [],  # suffix match
        [],  # suggest_similar_names (no results)
    ]
    svc = SynappsService(conn)
    with pytest.raises(ValueError, match="Symbol not found"):
        svc._resolve("createOrder")


def test_suggest_similar_names_filters_none_full_names() -> None:
    """Regression: suggest_similar_names query must include n.full_name IS NOT NULL guard.

    Repository/Directory/File nodes have a name but no full_name property.
    Without this guard those nodes can return NULL rows that break the caller's join().
    """
    conn = MagicMock()
    # Simulate a node with null full_name sneaking through (pre-fix behaviour)
    conn.query.return_value = [[None], ["com.example.Foo"]]
    result = suggest_similar_names(conn, "Foo")
    # Verify the query-level guard is present
    cypher = conn.query.call_args[0][0]
    assert "n.full_name IS NOT NULL" in cypher
    # The returned list must contain no None entries (belt-and-suspenders)
    assert None not in result
