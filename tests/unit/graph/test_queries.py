import pytest
from unittest.mock import MagicMock
from synapse.graph.lookups import (
    get_symbol, find_implementations, find_callers, find_callees,
    get_hierarchy, search_symbols, get_summary, list_summarized,
    list_projects, get_index_status, execute_readonly_query,
    get_method_symbol_map, get_symbol_source_info,
    find_type_references, find_dependencies,
    get_containing_type, get_members_overview,
    get_implemented_interfaces,
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



def test_find_implementations_does_not_require_interface_label() -> None:
    """Query must work even if interface node is stored as :Class (Roslyn fallback)."""
    conn = _conn([])
    find_implementations(conn, "Ns.IService")
    cypher = conn.query.call_args[0][0]
    # The interface node match must not enforce :Interface label
    assert "i:Interface" not in cypher, (
        "Must not constrain interface node to :Interface label — "
        "Roslyn may return non-interface SymbolKind for some interfaces"
    )


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


def test_execute_readonly_query_allows_match() -> None:
    conn = _conn([[]])
    execute_readonly_query(conn, "MATCH (n) RETURN n")
    conn.query.assert_called_once()


def test_execute_readonly_query_blocks_create() -> None:
    conn = _conn([])
    with pytest.raises(ValueError):
        execute_readonly_query(conn, "CREATE (n:Fake) RETURN n")


def test_execute_readonly_query_blocks_trailing_delete() -> None:
    conn = _conn([])
    with pytest.raises(ValueError):
        execute_readonly_query(conn, "MATCH (n) DELETE n")


def test_execute_readonly_query_blocks_multiline_merge() -> None:
    conn = _conn([])
    with pytest.raises(ValueError):
        execute_readonly_query(conn, "MATCH (n)\nMERGE (n)-[:X]->(m)")


def test_search_symbols_rejects_invalid_kind() -> None:
    conn = _conn([])
    with pytest.raises(ValueError):
        search_symbols(conn, "Foo", kind="'; DROP TABLE users; --")


def test_get_method_symbol_map_returns_correct_dict() -> None:
    conn = MagicMock()
    conn.query.return_value = [["Ns.C.M", 5, "/proj/C.cs"]]
    result = get_method_symbol_map(conn)
    assert result == {("/proj/C.cs", 5): "Ns.C.M"}


def test_get_symbol_source_info_returns_location() -> None:
    conn = _conn([["/proj/Foo.cs", 10, 25]])
    result = get_symbol_source_info(conn, "Ns.C.MyMethod")
    assert result == {"file_path": "/proj/Foo.cs", "line": 10, "end_line": 25}


def test_get_symbol_source_info_returns_none_when_not_found() -> None:
    conn = _conn([])
    result = get_symbol_source_info(conn, "Ns.Missing")
    assert result is None


def test_get_symbol_source_info_uses_stored_file_path() -> None:
    """Query must read n.file_path, not traverse CONTAINS* from File."""
    conn = _conn([["/proj/Actual.cs", 5, 20]])
    result = get_symbol_source_info(conn, "Ns.MyClass")
    assert result == {"file_path": "/proj/Actual.cs", "line": 5, "end_line": 20}
    # Verify the Cypher does NOT do a CONTAINS* traversal from File
    cypher = conn.query.call_args[0][0]
    assert "CONTAINS" not in cypher, "Must not traverse CONTAINS — use n.file_path property"


def test_find_type_references_returns_referencing_symbols() -> None:
    conn = _conn([[{"full_name": "Ns.C.M()", "name": "M"}, "parameter"]])
    results = find_type_references(conn, "Ns.UserDto")
    assert len(results) == 1
    assert results[0]["symbol"]["full_name"] == "Ns.C.M()"
    assert results[0]["kind"] == "parameter"


def test_find_type_references_returns_empty_for_no_refs() -> None:
    conn = _conn([])
    results = find_type_references(conn, "Ns.Orphan")
    assert results == []


def test_find_dependencies_returns_referenced_types() -> None:
    conn = _conn([[{"full_name": "Ns.UserDto", "name": "UserDto"}, 1]])
    results = find_dependencies(conn, "Ns.C.M()")
    assert len(results) == 1
    assert results[0]["type"]["full_name"] == "Ns.UserDto"
    assert results[0]["depth"] == 1


def test_get_containing_type_returns_parent() -> None:
    conn = _conn([[{"full_name": "Ns.MyClass", "name": "MyClass", "kind": "class", "line": 5, "end_line": 50}]])
    result = get_containing_type(conn, "Ns.MyClass.MyMethod")
    assert result["full_name"] == "Ns.MyClass"


def test_get_containing_type_returns_none_for_top_level() -> None:
    conn = _conn([])
    result = get_containing_type(conn, "Ns.MyClass")
    assert result is None


def test_get_members_overview_returns_children() -> None:
    conn = _conn([
        [{"full_name": "Ns.C.M()", "name": "M", "signature": "void M()"}],
        [{"full_name": "Ns.C.P", "name": "P", "type_name": "string"}],
    ])
    results = get_members_overview(conn, "Ns.C")
    assert len(results) == 2


def test_get_implemented_interfaces_returns_interfaces() -> None:
    conn = _conn([
        [{"full_name": "Ns.IFoo", "name": "IFoo"}],
        [{"full_name": "Ns.IBar", "name": "IBar"}],
    ])
    results = get_implemented_interfaces(conn, "Ns.MyClass")
    assert len(results) == 2
