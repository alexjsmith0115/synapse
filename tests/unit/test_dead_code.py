from __future__ import annotations

from unittest.mock import MagicMock

from synapps.graph.analysis import find_dead_code, find_untested, _build_base_exclusion_where, _EXCLUDED_METHOD_NAMES, _VENDORED_PATH_PATTERN
from synapps.graph.lookups import _TEST_PATH_PATTERN


def _conn_with_side_effects(*query_results):
    """Return a mock GraphConnection with sequential query side effects."""
    conn = MagicMock()
    conn.query.side_effect = list(query_results)
    return conn


# ---------------------------------------------------------------------------
# Test 1: Response shape — both top-level keys and stats keys present
# ---------------------------------------------------------------------------

def test_returns_methods_and_stats_keys():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    result = find_dead_code(conn)
    assert set(result.keys()) == {"methods", "stats"}
    assert set(result["stats"].keys()) == {"total_methods", "dead_count", "dead_ratio", "truncated", "limit", "offset"}


# ---------------------------------------------------------------------------
# Test 2: Empty graph returns empty methods and zero counts
# ---------------------------------------------------------------------------

def test_empty_graph_returns_empty_methods():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    result = find_dead_code(conn)
    assert result["methods"] == []
    assert result["stats"]["dead_count"] == 0


# ---------------------------------------------------------------------------
# Test 3: Dead method returned with correct shape
# ---------------------------------------------------------------------------

def test_dead_method_returned_with_correct_shape():
    conn = _conn_with_side_effects(
        [("Ns.Foo.Bar", "/src/Foo.cs", 10)],
        [(1,)],
        [(5,)],
    )
    result = find_dead_code(conn)
    assert len(result["methods"]) == 1
    m = result["methods"][0]
    assert set(m.keys()) == {"full_name", "file_path", "line", "inbound_call_count"}
    assert m["full_name"] == "Ns.Foo.Bar"
    assert m["file_path"] == "/src/Foo.cs"
    assert m["line"] == 10
    assert m["inbound_call_count"] == 0


# ---------------------------------------------------------------------------
# Test 4: inbound_call_count is always 0 for all returned methods
# ---------------------------------------------------------------------------

def test_inbound_call_count_always_zero():
    conn = _conn_with_side_effects(
        [("A.B", "/a.cs", 1), ("C.D", "/c.cs", 2)],
        [(2,)],
        [(10,)],
    )
    result = find_dead_code(conn)
    assert all(m["inbound_call_count"] == 0 for m in result["methods"])


# ---------------------------------------------------------------------------
# Test 5: Stats dead_ratio is computed correctly
# ---------------------------------------------------------------------------

def test_stats_dead_ratio():
    conn = _conn_with_side_effects(
        [("A.B", "/a.cs", 1)],
        [(1,)],
        [(4,)],
    )
    result = find_dead_code(conn)
    assert result["stats"]["total_methods"] == 4
    assert result["stats"]["dead_count"] == 1
    assert result["stats"]["dead_ratio"] == 0.25


# ---------------------------------------------------------------------------
# Test 6: Division by zero guard when total_methods is 0
# ---------------------------------------------------------------------------

def test_stats_dead_ratio_zero_division_guard():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    result = find_dead_code(conn)
    assert result["stats"]["dead_ratio"] == 0.0


# ---------------------------------------------------------------------------
# Test 7: Test methods excluded via NOT m.file_path =~ $test_pattern
# ---------------------------------------------------------------------------

def test_test_methods_excluded_via_cypher():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    find_dead_code(conn)
    cypher = conn.query.call_args_list[0].args[0]
    params = conn.query.call_args_list[0].args[1]
    assert "NOT m.file_path =~ $test_pattern" in cypher
    assert params["test_pattern"] == _TEST_PATH_PATTERN


# ---------------------------------------------------------------------------
# Test 8: HTTP handlers excluded via NOT (m)-[:SERVES]->()
# ---------------------------------------------------------------------------

def test_serves_edge_excluded_via_cypher():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    find_dead_code(conn)
    cypher = conn.query.call_args_list[0].args[0]
    assert "NOT (m)-[:SERVES]->()" in cypher


# ---------------------------------------------------------------------------
# Test 9: Interface impl targets excluded via NOT ()-[:IMPLEMENTS]->(m)
# ---------------------------------------------------------------------------

def test_implements_target_excluded_via_cypher():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    find_dead_code(conn)
    cypher = conn.query.call_args_list[0].args[0]
    assert "NOT ()-[:IMPLEMENTS]->(m)" in cypher


# ---------------------------------------------------------------------------
# Test 10: Dispatch targets excluded via NOT ()-[:DISPATCHES_TO]->(m)
# ---------------------------------------------------------------------------

def test_dispatches_to_target_excluded_via_cypher():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    find_dead_code(conn)
    cypher = conn.query.call_args_list[0].args[0]
    assert "NOT ()-[:DISPATCHES_TO]->(m)" in cypher


# ---------------------------------------------------------------------------
# Test 11: Override methods excluded via NOT (m)-[:OVERRIDES]->()
# ---------------------------------------------------------------------------

def test_overrides_excluded_via_cypher():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    find_dead_code(conn)
    cypher = conn.query.call_args_list[0].args[0]
    assert "NOT (m)-[:OVERRIDES]->()" in cypher


# ---------------------------------------------------------------------------
# Test 12: Constructors excluded via name check AND parent-name match
# ---------------------------------------------------------------------------

def test_constructors_excluded_via_cypher():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    find_dead_code(conn)
    cypher = conn.query.call_args_list[0].args[0]
    assert "'__init__'" in cypher
    assert "'constructor'" in cypher
    # EF Core migration methods excluded alongside constructors
    assert "'Up'" in cypher
    assert "'Down'" in cypher
    assert "'BuildTargetModel'" in cypher
    assert "p.name = m.name" in cypher


# ---------------------------------------------------------------------------
# Test 13: Zero-callers check present in first query
# ---------------------------------------------------------------------------

def test_no_callers_excluded_via_cypher():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    find_dead_code(conn)
    cypher = conn.query.call_args_list[0].args[0]
    assert "NOT ()-[:CALLS]->(m)" in cypher


# ---------------------------------------------------------------------------
# Test 14: Non-empty exclude_pattern is applied to the query
# ---------------------------------------------------------------------------

def test_exclude_pattern_passed_to_query():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    find_dead_code(conn, exclude_pattern=".*Generated.*")
    params = conn.query.call_args_list[0].args[1]
    cypher = conn.query.call_args_list[0].args[0]
    assert params["exclude_pattern"] == ".*Generated.*"
    assert "NOT m.full_name =~ $exclude_pattern" in cypher


# ---------------------------------------------------------------------------
# Test 15: Empty exclude_pattern (default) includes no-op guard
# ---------------------------------------------------------------------------

def test_empty_exclude_pattern_default():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    find_dead_code(conn)
    params = conn.query.call_args_list[0].args[1]
    cypher = conn.query.call_args_list[0].args[0]
    assert params["exclude_pattern"] == ""
    assert "$exclude_pattern = ''" in cypher


# ---------------------------------------------------------------------------
# Regression: exclude_pattern without .* anchors must be auto-wrapped
# so Cypher =~ (which is full-string match) works as substring match
# ---------------------------------------------------------------------------

def test_exclude_pattern_auto_wrapped_for_substring_match():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    find_dead_code(conn, exclude_pattern=r"Configuration\.Configure")
    params = conn.query.call_args_list[0].args[1]
    assert params["exclude_pattern"] == r".*Configuration\.Configure.*"


def test_exclude_pattern_already_anchored_not_double_wrapped():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    find_dead_code(conn, exclude_pattern=".*Generated.*")
    params = conn.query.call_args_list[0].args[1]
    assert params["exclude_pattern"] == ".*Generated.*"


# ---------------------------------------------------------------------------
# Regression: decorator-registered entry points excluded via attributes
# ---------------------------------------------------------------------------

def test_decorator_entry_points_excluded_via_cypher():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    find_dead_code(conn)
    cypher = conn.query.call_args_list[0].args[0]
    assert 'CONTAINS \'"command"\'' in cypher
    assert 'CONTAINS \'"tool"\'' in cypher
    assert 'CONTAINS \'"callback"\'' in cypher


# ---------------------------------------------------------------------------
# Regression: Interface/Protocol definition methods excluded
# ---------------------------------------------------------------------------

def test_interface_member_methods_excluded_via_cypher():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    find_dead_code(conn)
    cypher = conn.query.call_args_list[0].args[0]
    assert "NOT (m)<-[:CONTAINS]-(:Interface)" in cypher


# ---------------------------------------------------------------------------
# Test 16: ORDER BY clause present in first query
# ---------------------------------------------------------------------------

def test_ordering_in_cypher():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    find_dead_code(conn)
    cypher = conn.query.call_args_list[0].args[0]
    assert "ORDER BY m.file_path, m.full_name" in cypher


# ---------------------------------------------------------------------------
# Test 17: Total methods query uses same exclusions and count(m)
# ---------------------------------------------------------------------------

def test_total_methods_query_has_same_exclusions():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    find_dead_code(conn)
    cypher = conn.query.call_args_list[2].args[0]
    assert "NOT m.file_path =~ $test_pattern" in cypher
    assert "count(m)" in cypher


# ---------------------------------------------------------------------------
# Regression: main() and Main() excluded as framework entry points
# ---------------------------------------------------------------------------

def test_main_methods_excluded_via_cypher():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    find_dead_code(conn)
    cypher = conn.query.call_args_list[0].args[0]
    assert "'main'" in cypher
    assert "'Main'" in cypher


# ---------------------------------------------------------------------------
# Regression: Spring framework attributes excluded (now lowercase)
# JavaAttributeExtractor stores annotations via .lower() so check must be lowercase.
# ---------------------------------------------------------------------------

def test_spring_attributes_excluded_via_cypher():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    find_dead_code(conn)
    cypher = conn.query.call_args_list[0].args[0]
    assert '"bean"' in cypher
    assert '"postconstruct"' in cypher
    assert '"requestmapping"' in cypher
    assert '"getmapping"' in cypher
    assert '"scheduled"' in cypher


# ---------------------------------------------------------------------------
# Regression: limit parameter truncates methods list
# ---------------------------------------------------------------------------

def test_limit_truncates_methods_list():
    page_rows = [(f"Ns.Foo{i}", f"/foo{i}.cs", i) for i in range(3)]
    conn = _conn_with_side_effects(page_rows, [(10,)], [(50,)])
    result = find_dead_code(conn, limit=3)
    assert len(result["methods"]) == 3
    assert result["stats"]["dead_count"] == 10
    assert result["stats"]["truncated"] is True
    assert result["stats"]["limit"] == 3


def test_limit_not_truncated_when_under():
    dead_rows = [("Ns.Foo", "/foo.cs", 1)]
    conn = _conn_with_side_effects(dead_rows, [(1,)], [(5,)])
    result = find_dead_code(conn, limit=100)
    assert len(result["methods"]) == 1
    assert result["stats"]["truncated"] is False


# ---------------------------------------------------------------------------
# Regression: Java framework annotations must be stored as lowercase
# (JavaAttributeExtractor stores annotations via .lower())
# ---------------------------------------------------------------------------

def test_framework_attributes_exclude_lowercase_java_annotations():
    """_build_base_exclusion_where must contain lowercase Java annotations.

    JavaAttributeExtractor stores attributes via .lower(), so the CONTAINS check
    must use lowercase strings to match Spring/JPA annotations.
    C# attributes remain PascalCase since the C# extractor does NOT lowercase.
    """
    where = _build_base_exclusion_where()
    # Java Spring annotations — must be lowercase
    assert '"bean"' in where
    assert '"getmapping"' in where
    assert '"postmapping"' in where
    assert '"requestmapping"' in where
    assert '"scheduled"' in where
    # C# attributes — must remain PascalCase
    assert '"ApiController"' in where


# ---------------------------------------------------------------------------
# BUG-07: Default limit must be 15 (not 200)
# ---------------------------------------------------------------------------

def test_find_dead_code_default_limit_is_15():
    """find_dead_code default limit parameter must be 15."""
    import inspect
    sig = inspect.signature(find_dead_code)
    assert sig.parameters["limit"].default == 15, (
        f"Expected default limit=15, got {sig.parameters['limit'].default}"
    )


def test_find_untested_default_limit_is_15():
    """find_untested default limit parameter must be 15."""
    import inspect
    sig = inspect.signature(find_untested)
    assert sig.parameters["limit"].default == 15, (
        f"Expected default limit=15, got {sig.parameters['limit'].default}"
    )


# ---------------------------------------------------------------------------
# BUG-07: offset parameter for pagination
# ---------------------------------------------------------------------------

def _dead_rows(count: int):
    """Generate count fake dead method rows."""
    return [(f"Ns.Method{i}", f"/src/file{i}.cs", i) for i in range(count)]


def test_find_dead_code_offset_paginates():
    """With offset=5, limit=5, DB returns items 5-9 via SKIP/LIMIT."""
    page_rows = [(f"Ns.Method{i}", f"/src/file{i}.cs", i) for i in range(5, 10)]
    conn = _conn_with_side_effects(page_rows, [(20,)], [(50,)])
    result = find_dead_code(conn, offset=5, limit=5)
    returned_names = [m["full_name"] for m in result["methods"]]
    expected_names = [f"Ns.Method{i}" for i in range(5, 10)]
    assert returned_names == expected_names


def test_find_dead_code_offset_in_stats():
    """Stats dict must contain 'offset' key reflecting the requested offset."""
    conn = _conn_with_side_effects(_dead_rows(3), [(5,)], [(10,)])
    result = find_dead_code(conn, offset=2, limit=3)
    assert "offset" in result["stats"], "Stats dict missing 'offset' key"
    assert result["stats"]["offset"] == 2


def test_find_dead_code_offset_zero_is_default():
    """Default offset=0 means first page."""
    import inspect
    sig = inspect.signature(find_dead_code)
    assert "offset" in sig.parameters, "find_dead_code missing 'offset' parameter"
    assert sig.parameters["offset"].default == 0


def test_find_untested_offset_paginates():
    """With offset=5, limit=5, DB returns items 5-9 via SKIP/LIMIT."""
    page_rows = [(f"Ns.Method{i}", f"/src/file{i}.cs", i) for i in range(5, 10)]
    conn = _conn_with_side_effects(page_rows, [(20,)], [(50,)])
    result = find_untested(conn, offset=5, limit=5)
    returned_names = [m["full_name"] for m in result["methods"]]
    expected_names = [f"Ns.Method{i}" for i in range(5, 10)]
    assert returned_names == expected_names


def test_find_untested_offset_in_stats():
    """find_untested stats dict must contain 'offset' key."""
    rows = [(f"Ns.M{i}", f"/f{i}.cs", i) for i in range(2)]
    conn = _conn_with_side_effects(rows, [(3,)], [(10,)])
    result = find_untested(conn, offset=1, limit=2)
    assert "offset" in result["stats"], "Stats dict missing 'offset' key"
    assert result["stats"]["offset"] == 1


# ---------------------------------------------------------------------------
# Regression: .NET / Java lifecycle methods excluded (D-04, D-05, D-06)
# IDisposable.Dispose() and similar are always framework-invoked.
# ---------------------------------------------------------------------------

def test_contains_dispose() -> None:
    assert "Dispose" in _EXCLUDED_METHOD_NAMES


def test_contains_dispose_async() -> None:
    assert "DisposeAsync" in _EXCLUDED_METHOD_NAMES


def test_contains_close() -> None:
    assert "Close" in _EXCLUDED_METHOD_NAMES


def test_contains_finalize() -> None:
    assert "Finalize" in _EXCLUDED_METHOD_NAMES


def test_contains_on_navigated_to() -> None:
    assert "OnNavigatedTo" in _EXCLUDED_METHOD_NAMES


def test_contains_on_initialized() -> None:
    assert "OnInitialized" in _EXCLUDED_METHOD_NAMES


def test_contains_on_initialized_async() -> None:
    assert "OnInitializedAsync" in _EXCLUDED_METHOD_NAMES


def test_build_exclusion_where_excludes_dispose() -> None:
    where = _build_base_exclusion_where()
    assert "'Dispose'" in where


# ---------------------------------------------------------------------------
# Regression: .NET Startup/Program convention methods excluded
# ---------------------------------------------------------------------------

def test_dotnet_startup_configure_services_excluded_via_cypher():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    find_dead_code(conn)
    cypher = conn.query.call_args_list[0].args[0]
    assert "'ConfigureServices'" in cypher


def test_dotnet_startup_class_name_excluded_via_cypher():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    find_dead_code(conn)
    cypher = conn.query.call_args_list[0].args[0]
    assert "cfg.name = 'Startup'" in cypher


def test_dotnet_program_class_name_excluded_via_cypher():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    find_dead_code(conn)
    cypher = conn.query.call_args_list[0].args[0]
    assert "cfg.name = 'Program'" in cypher


def test_dotnet_framework_attributes_excluded_via_cypher():
    where = _build_base_exclusion_where()
    assert '"Authorize"' in where
    assert '"AllowAnonymous"' in where
    assert '"GlobalSetup"' in where
    assert '"GlobalCleanup"' in where


def test_dotnet_convention_method_names_excluded():
    assert "ConfigureWebHost" in _EXCLUDED_METHOD_NAMES
    assert "CreateHostBuilder" in _EXCLUDED_METHOD_NAMES
    assert "CreateWebHostBuilder" in _EXCLUDED_METHOD_NAMES


# ---------------------------------------------------------------------------
# Regression: subdirectory filter adds CONTAINS clause to all three queries
# ---------------------------------------------------------------------------

def test_subdirectory_filter_adds_contains_clause():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    find_dead_code(conn, subdirectory="src/api")
    for i in range(3):
        cypher = conn.query.call_args_list[i].args[0]
        params = conn.query.call_args_list[i].args[1]
        assert "m.file_path CONTAINS $subdirectory" in cypher
        assert params["subdirectory"] == "src/api"


def test_subdirectory_empty_string_no_contains_clause():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    find_dead_code(conn, subdirectory="")
    cypher = conn.query.call_args_list[0].args[0]
    assert "CONTAINS $subdirectory" not in cypher


def test_subdirectory_default_no_contains_clause():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    find_dead_code(conn)
    cypher = conn.query.call_args_list[0].args[0]
    assert "CONTAINS $subdirectory" not in cypher


def test_find_untested_subdirectory_filter():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    find_untested(conn, subdirectory="src/services")
    for i in range(3):
        cypher = conn.query.call_args_list[i].args[0]
        params = conn.query.call_args_list[i].args[1]
        assert "m.file_path CONTAINS $subdirectory" in cypher
        assert params["subdirectory"] == "src/services"


def test_find_untested_no_subdirectory_no_contains():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    find_untested(conn)
    cypher = conn.query.call_args_list[0].args[0]
    assert "CONTAINS $subdirectory" not in cypher


# --- VEND-01/02: Vendored path exclusion in dead code and untested queries ---

def test_find_dead_code_passes_vendor_pattern_in_params():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    find_dead_code(conn)
    params = conn.query.call_args_list[0].args[1]
    assert "vendor_pattern" in params
    assert params["vendor_pattern"] == _VENDORED_PATH_PATTERN


def test_find_untested_passes_vendor_pattern_in_params():
    conn = _conn_with_side_effects([], [(0,)], [(0,)])
    find_untested(conn)
    params = conn.query.call_args_list[0].args[1]
    assert "vendor_pattern" in params
    assert params["vendor_pattern"] == _VENDORED_PATH_PATTERN


def test_vendor_pattern_exclusion_in_where_clause():
    clause = _build_base_exclusion_where()
    assert "NOT m.file_path =~ $vendor_pattern" in clause
