from unittest.mock import MagicMock
from synapse.graph.queries import (
    get_symbol, find_implementations, find_callers, find_callees,
    get_hierarchy, search_symbols, get_summary, list_summarized,
    list_projects, get_index_status,
)


def _conn(return_value: list) -> MagicMock:
    conn = MagicMock()
    conn.query.return_value = return_value
    return conn


def test_get_symbol_returns_none_when_not_found() -> None:
    conn = _conn([])
    result = get_symbol(conn, "MyNs.MyClass")
    assert result is None


def test_get_symbol_returns_first_row() -> None:
    conn = _conn([[{"full_name": "MyNs.MyClass", "kind": "class"}]])
    result = get_symbol(conn, "MyNs.MyClass")
    assert result == {"full_name": "MyNs.MyClass", "kind": "class"}


def test_find_implementations_returns_list() -> None:
    conn = _conn([[{"full_name": "MyNs.Impl"}], [{"full_name": "MyNs.Impl2"}]])
    results = find_implementations(conn, "MyNs.IService")
    assert len(results) == 2


def test_find_callers_passes_full_name() -> None:
    conn = _conn([])
    find_callers(conn, "MyNs.A.Run()")
    cypher, params = conn.query.call_args[0][0], conn.query.call_args[0][1]
    assert "CALLS" in cypher
    assert params["full_name"] == "MyNs.A.Run()"


def test_search_symbols_with_kind_filter() -> None:
    conn = _conn([])
    search_symbols(conn, "Service", kind="Class")
    cypher, params = conn.query.call_args[0][0], conn.query.call_args[0][1]
    assert "Class" in cypher
    assert params["query"] in ("*Service*", "Service")


def test_list_projects_queries_repository_nodes() -> None:
    conn = _conn([])
    list_projects(conn)
    cypher = conn.query.call_args[0][0]
    assert "Repository" in cypher
