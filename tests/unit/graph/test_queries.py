import re

import pytest
from unittest.mock import MagicMock
from synapps.graph.lookups import (
    get_symbol, find_implementations, find_callers, find_callees,
    get_hierarchy, search_symbols, get_summary, list_summarized,
    list_projects, get_index_status, execute_readonly_query,
    get_method_symbol_map, get_symbol_source_info,
    find_type_references, find_dependencies,
    get_containing_type, get_members_overview, get_called_members,
    get_implemented_interfaces,
    resolve_full_name_with_labels,
    _TEST_PATH_PATTERN,
    _preprocess_query,
)
from conftest import _MockNode


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


def test_find_implementations_no_abc_fallback() -> None:
    """After ABC promotion, find_implementations should NOT traverse INHERITS
    for abstract :Class nodes — only IMPLEMENTS edges to :Interface nodes work."""
    conn = _conn([])
    # No IMPLEMENTS matches, no suffix matches, return empty
    result = find_implementations(conn, "pkg.AbstractBase")
    assert result == []
    # Verify only 2 queries were made (primary + suffix), not 3 (no ABC fallback)
    assert conn.query.call_count == 2


def test_find_callers_passes_full_name() -> None:
    conn = _conn([])
    find_callers(conn, "MyNs.A.Run()")
    cypher, params = conn.query.call_args[0][0], conn.query.call_args[0][1]
    assert "CALLS" in cypher
    assert params["full_name"] == "MyNs.A.Run()"


def test_find_callers_excludes_tests_by_default() -> None:
    """Default should filter test callers."""
    conn = _conn([])
    find_callers(conn, "MyNs.A.Run()")
    cypher = conn.query.call_args[0][0]
    params = conn.query.call_args[0][1]
    assert "test_pattern" in params
    assert params["test_pattern"] == _TEST_PATH_PATTERN
    assert "NOT caller.file_path =~" in cypher


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
    conn = MagicMock()
    conn.query_with_timeout.return_value = [[]]
    execute_readonly_query(conn, "MATCH (n) RETURN n")
    conn.query_with_timeout.assert_called_once()


def test_execute_readonly_query_propagates_timeout_error():
    """execute_readonly_query propagates TimeoutError from query_with_timeout."""
    conn = MagicMock()
    conn.query_with_timeout.side_effect = TimeoutError("Query exceeded 10s timeout. Add filters or a LIMIT clause.")

    with pytest.raises(TimeoutError, match="timeout"):
        execute_readonly_query(conn, "MATCH (n) RETURN n")


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


def test_execute_readonly_query_allows_create_in_string_literal() -> None:
    conn = MagicMock()
    conn.query_with_timeout.return_value = []
    execute_readonly_query(conn, "MATCH (m:Method) WHERE m.name CONTAINS 'create' RETURN m")
    conn.query_with_timeout.assert_called_once()


def test_execute_readonly_query_allows_uppercase_create_in_string_literal() -> None:
    conn = MagicMock()
    conn.query_with_timeout.return_value = []
    execute_readonly_query(conn, "MATCH (m:Method) WHERE m.full_name CONTAINS 'CREATE' RETURN m")
    conn.query_with_timeout.assert_called_once()


def test_execute_readonly_query_allows_double_quoted_mutation_keyword() -> None:
    conn = MagicMock()
    conn.query_with_timeout.return_value = []
    execute_readonly_query(conn, 'MATCH (m) WHERE m.name = "deleteOrder" RETURN m')
    conn.query_with_timeout.assert_called_once()


def test_execute_readonly_query_allows_property_named_set() -> None:
    """Property access like n.set must not be treated as a SET statement."""
    conn = MagicMock()
    conn.query_with_timeout.return_value = []
    execute_readonly_query(conn, "MATCH (n) WHERE n.set = 1 RETURN n")
    conn.query_with_timeout.assert_called_once()


def test_execute_readonly_query_allows_property_named_delete() -> None:
    """Property access like n.delete must not be treated as a DELETE statement."""
    conn = MagicMock()
    conn.query_with_timeout.return_value = []
    execute_readonly_query(conn, "MATCH (n) WHERE n.delete = true RETURN n")
    conn.query_with_timeout.assert_called_once()


def test_execute_readonly_query_blocks_create_after_literal() -> None:
    """Mutation keyword after a string literal is still blocked."""
    conn = _conn([])
    with pytest.raises(ValueError):
        execute_readonly_query(conn, "MATCH (m) WHERE m.name = 'foo' CREATE (n:Fake)")


def test_execute_readonly_query_blocks_set_outside_literal() -> None:
    """Statement-level SET (not property access) must be blocked."""
    conn = _conn([])
    with pytest.raises(ValueError):
        execute_readonly_query(conn, "MATCH (n) SET n.name = 'test'")


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


def test_find_type_references_with_kind_filter() -> None:
    conn = _conn([[{"full_name": "Ns.C.M()", "name": "M"}, "parameter"]])
    results = find_type_references(conn, "Ns.UserDto", kind="parameter")
    assert len(results) == 1
    _, params = conn.query.call_args[0]
    assert params["kind"] == "parameter"


def test_find_type_references_without_kind_returns_all() -> None:
    conn = _conn([
        [{"full_name": "Ns.C.M()", "name": "M"}, "parameter"],
        [{"full_name": "Ns.C.P", "name": "P"}, "property_type"],
    ])
    results = find_type_references(conn, "Ns.UserDto")
    assert len(results) == 2


def test_find_type_references_kind_in_query() -> None:
    conn = _conn([])
    find_type_references(conn, "Ns.UserDto", kind="return_type")
    cypher = conn.query.call_args[0][0]
    assert "r.kind" in cypher


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


def test_get_called_members_returns_called_only() -> None:
    conn = _conn([
        [{"full_name": "Ns.Db.SaveChangesAsync", "name": "SaveChangesAsync", "signature": "Task SaveChangesAsync()"}],
        [{"full_name": "Ns.Db.MeetingNotes", "name": "MeetingNotes", "type_name": "DbSet<MeetingNote>"}],
    ])
    results = get_called_members(conn, "Ns.Svc.Create", "Ns.Db")
    assert len(results) == 2
    assert results[0]["full_name"] == "Ns.Db.SaveChangesAsync"


def test_get_called_members_returns_empty_for_no_calls() -> None:
    conn = _conn([])
    results = get_called_members(conn, "Ns.Svc.Create", "Ns.Db")
    assert results == []


def test_get_implemented_interfaces_returns_interfaces() -> None:
    conn = _conn([
        [{"full_name": "Ns.IFoo", "name": "IFoo"}],
        [{"full_name": "Ns.IBar", "name": "IBar"}],
    ])
    results = get_implemented_interfaces(conn, "Ns.MyClass")
    assert len(results) == 2


def test_get_index_status_returns_none_when_not_found() -> None:
    conn = MagicMock()
    conn.query.return_value = []
    assert get_index_status(conn, "/proj") is None


def test_get_index_status_strips_trailing_slash() -> None:
    repo_node = _MockNode(["Repository"], {"last_indexed": "2026-01-01", "languages": ["typescript"]})
    conn = MagicMock()
    conn.query.side_effect = [[[repo_node]], [[3]], [[42]], []]
    get_index_status(conn, "/proj/")
    path_arg = conn.query.call_args_list[0][0][1]["path"]
    assert path_arg == "/proj"


def test_get_index_status_returns_counts() -> None:
    repo_node = _MockNode(["Repository"], {"last_indexed": "2026-01-01", "languages": ["csharp"]})
    conn = MagicMock()
    conn.query.side_effect = [
        [[repo_node]],  # repo
        [[5]],          # file_count
        [[99]],         # symbol_count
        [["Class", 60], ["Method", 39]],  # breakdown
    ]
    result = get_index_status(conn, "/proj")
    assert result == {
        "path": "/proj",
        "languages": ["csharp"],
        "last_indexed": "2026-01-01",
        "file_count": 5,
        "symbol_count": 99,
        "symbol_breakdown": {"Class": 60, "Method": 39},
    }


def test_get_index_status_includes_symbol_breakdown() -> None:
    repo_node = _MockNode(["Repository"], {"path": "/proj", "last_indexed": "2026-01-01", "languages": ["csharp"]})
    conn = MagicMock()
    conn.query.side_effect = [
        [[repo_node]],       # repo query
        [[42]],              # file_count
        [[100]],             # symbol_count
        [                    # breakdown query
            ["Class", 40],
            ["Method", 50],
            ["Property", 10],
        ],
    ]
    result = get_index_status(conn, "/proj")
    assert result is not None
    assert "symbol_breakdown" in result
    assert result["symbol_breakdown"] == {"Class": 40, "Method": 50, "Property": 10}


def test_get_hierarchy_interface_returns_implementors_as_children() -> None:
    """get_hierarchy should find implementors via IMPLEMENTS for Interface nodes."""
    impl = _MockNode(["Class"], {"full_name": "Ns.Impl"})
    conn = MagicMock()
    conn.query.side_effect = [
        [],              # parents query
        [[impl]],        # children query (UNION result)
        [],              # implements query
    ]
    result = get_hierarchy(conn, "Ns.IFoo")
    assert len(result["children"]) == 1
    assert result["children"][0]["full_name"] == "Ns.Impl"


def test_resolve_with_labels_exact_match() -> None:
    conn = _conn([["Ns.TaskService"]])
    result = resolve_full_name_with_labels(conn, "Ns.TaskService")
    assert result == "Ns.TaskService"


def test_resolve_with_labels_suffix_match_single() -> None:
    conn = MagicMock()
    conn.query.side_effect = [[], [["Ns.TaskService", ["Class"]]]]
    result = resolve_full_name_with_labels(conn, "TaskService")
    assert result == "Ns.TaskService"


def test_resolve_with_labels_suffix_match_ambiguous() -> None:
    conn = MagicMock()
    conn.query.side_effect = [[], [["Ns.ITaskService", ["Interface"]], ["Ns.TaskService", ["Class"]]]]
    result = resolve_full_name_with_labels(conn, "TaskService")
    assert isinstance(result, list)
    assert len(result) == 2


class TestTestPathPattern:
    """Verify _TEST_PATH_PATTERN matches all common test file conventions."""

    @pytest.fixture
    def pattern(self):
        return re.compile(_TEST_PATH_PATTERN)

    # --- Must match ---
    def test_matches_csharp_tests_dir(self, pattern):
        assert pattern.match("/app/MyApp.Tests/FooTest.cs")

    def test_matches_python_tests_dir(self, pattern):
        assert pattern.match("/app/tests/test_foo.py")

    def test_matches_jest_dunder_tests_dir(self, pattern):
        assert pattern.match("/app/src/__tests__/status.test.ts")

    def test_matches_test_suffix_ts(self, pattern):
        assert pattern.match("/app/src/hooks/useMeetings.test.ts")

    def test_matches_spec_suffix_tsx(self, pattern):
        assert pattern.match("/app/src/hooks/useMeetings.spec.tsx")

    def test_matches_test_suffix_js(self, pattern):
        assert pattern.match("/app/src/utils/helpers.test.js")

    def test_matches_spec_suffix_jsx(self, pattern):
        assert pattern.match("/app/src/components/Button.spec.jsx")

    def test_matches_python_unit_tests_dir(self, pattern):
        assert pattern.match("/app/tests/unit/test_cli.py")

    def test_matches_underscore_test_py(self, pattern):
        assert pattern.match("/app/src/foo_test.py")

    def test_matches_underscore_test_go(self, pattern):
        assert pattern.match("/app/src/foo_test.go")

    # --- Must NOT match ---
    def test_no_match_regular_ts_file(self, pattern):
        assert not pattern.match("/app/src/hooks/useMeetings.ts")

    def test_no_match_regular_cs_file(self, pattern):
        assert not pattern.match("/app/src/services/MeetingService.cs")

    def test_no_match_testimonial_card(self, pattern):
        assert not pattern.match("/app/src/components/TestimonialCard.tsx")

    def test_no_match_testing_utils(self, pattern):
        assert not pattern.match("/app/src/testing-utils.ts")

    def test_no_match_contest_py(self, pattern):
        assert not pattern.match("/app/src/contest.py")


@pytest.mark.parametrize("query,expected", [
    # Language keyword prefix with syntax — extracts identifier
    ("def my_function(", "my_function"),
    ("class MyService {", "MyService"),
    # Multi-keyword prefix with return type — longest token wins
    ("public void myMethod(int x)", "myMethod"),
    # async function prefix
    ("async function fetchData()", "fetchData"),
    # Clean symbol name — unchanged
    ("MyClass", "MyClass"),
    ("Service", "Service"),
    # All-keyword/syntax result — falls back to original query
    ("class {", "class {"),
    # Single keyword alone — preserved (Pitfall 3)
    ("static", "static"),
    ("def", "def"),
    # Syntax-only prefix (@ decorator) — strips @, keeps remainder
    ("@Override", "Override"),
    # Colon syntax — strips colon, strips keyword
    ("class:MyClass", "MyClass"),
    # Qualified name — dots preserved, returned unchanged
    ("MyNs.MyClass", "MyNs.MyClass"),
])
def test_preprocess_query(query: str, expected: str) -> None:
    assert _preprocess_query(query) == expected


# --- search_symbols preprocessing integration ---

def test_search_symbols_preprocesses_grep_style_query() -> None:
    """search_symbols must strip keyword prefix before querying."""
    conn = _conn([])
    search_symbols(conn, "def my_function(")
    _, params = conn.query.call_args[0][0], conn.query.call_args[0][1]
    assert params["query"] == "my_function"


def test_search_symbols_passes_clean_query_unchanged() -> None:
    """A plain symbol name must not be altered."""
    conn = _conn([])
    search_symbols(conn, "Service")
    _, params = conn.query.call_args[0][0], conn.query.call_args[0][1]
    assert params["query"] == "Service"


# --- search_symbols case-insensitive fallback ---

def test_search_symbols_no_fallback_when_exact_match_returns_results() -> None:
    """conn.query must be called exactly once when exact match returns results."""
    result_row = [{"full_name": "Ns.MyFunction", "name": "MyFunction"}]
    conn = _conn([result_row])
    search_symbols(conn, "MyFunction")
    assert conn.query.call_count == 1


def test_search_symbols_fallback_fires_when_exact_match_empty() -> None:
    """conn.query must be called twice when exact match returns nothing."""
    result_row = [{"full_name": "Ns.MyFunction", "name": "MyFunction"}]
    conn = MagicMock()
    conn.query.side_effect = [[], [result_row]]
    search_symbols(conn, "myfunction")
    assert conn.query.call_count == 2


def test_search_symbols_fallback_uses_toLower_not_regex() -> None:
    """Fallback query must use toLower CONTAINS, not =~ regex."""
    conn = MagicMock()
    conn.query.side_effect = [[], []]
    search_symbols(conn, "myfunction")
    fallback_cypher = conn.query.call_args_list[1][0][0]
    assert "toLower" in fallback_cypher
    assert "=~" not in fallback_cypher


def test_search_symbols_fallback_preserves_kind_filter() -> None:
    """Both exact and fallback queries must include the kind filter."""
    conn = MagicMock()
    conn.query.side_effect = [[], []]
    search_symbols(conn, "myservice", kind="Class")
    exact_cypher = conn.query.call_args_list[0][0][0]
    fallback_cypher = conn.query.call_args_list[1][0][0]
    assert "Class" in exact_cypher
    assert "Class" in fallback_cypher


def test_search_symbols_fallback_preserves_namespace_filter() -> None:
    """Both queries must include namespace filter when provided."""
    conn = MagicMock()
    conn.query.side_effect = [[], []]
    search_symbols(conn, "myservice", namespace="MyNs")
    exact_params = conn.query.call_args_list[0][0][1]
    fallback_params = conn.query.call_args_list[1][0][1]
    assert exact_params.get("namespace") == "MyNs"
    assert fallback_params.get("namespace") == "MyNs"
