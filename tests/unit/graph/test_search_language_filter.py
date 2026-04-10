"""Unit tests for the language filter parameter on search_symbols."""
import pytest
from unittest.mock import MagicMock, call

from synapps.graph.lookups import search_symbols


def _conn(return_value: list) -> MagicMock:
    conn = MagicMock()
    conn.query.return_value = return_value
    return conn


def test_search_symbols_with_language_adds_where_condition() -> None:
    """When language is provided, WHERE clause must filter by n.language = $language."""
    conn = _conn([])
    search_symbols(conn, "Animal", language="python")

    # Check the first (exact-match) call includes the language filter.
    first_cypher, first_params = conn.query.call_args_list[0].args
    assert "n.language = $language" in first_cypher
    assert first_params.get("language") == "python"


def test_search_symbols_without_language_omits_condition() -> None:
    """When language is None, the query must NOT add a language filter."""
    conn = _conn([])
    search_symbols(conn, "Animal", language=None)

    first_cypher, first_params = conn.query.call_args_list[0].args
    assert "n.language" not in first_cypher
    assert "language" not in first_params


def test_search_symbols_kind_and_language_combined() -> None:
    """kind label and language filter must both appear in the query when combined."""
    conn = _conn([])
    search_symbols(conn, "Animal", kind="Class", language="python")

    first_cypher, first_params = conn.query.call_args_list[0].args
    assert ":Class" in first_cypher
    assert "n.language = $language" in first_cypher
    assert first_params.get("language") == "python"
    assert first_params.get("query") == "Animal"


def test_search_symbols_default_language_is_none() -> None:
    """Calling search_symbols without the language keyword omits the filter (backward compat)."""
    conn = _conn([])
    search_symbols(conn, "Dog")

    cypher, params = conn.query.call_args.args
    assert "n.language" not in cypher


def test_search_symbols_language_filter_csharp() -> None:
    """language='csharp' must produce a language condition, not just python."""
    conn = _conn([])
    search_symbols(conn, "Service", language="csharp")

    cypher, params = conn.query.call_args.args
    assert "n.language = $language" in cypher
    assert params.get("language") == "csharp"
