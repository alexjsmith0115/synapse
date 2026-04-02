from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

from synapps.graph.analysis import get_architecture_overview, _VENDORED_PATH_PATTERN
from synapps.graph.lookups import _TEST_PATH_PATTERN


def _conn_with_side_effects(*query_results):
    """Return a mock GraphConnection with sequential query side effects."""
    conn = MagicMock()
    conn.query.side_effect = list(query_results)
    return conn


def _empty_conn():
    """Return a mock GraphConnection where all queries return empty lists (8 queries)."""
    return _conn_with_side_effects([], [], [], [], [], [], [], [])


# ---------------------------------------------------------------------------
# Test 1: Response shape — all four top-level keys present
# ---------------------------------------------------------------------------

def test_returns_all_four_keys():
    conn = _empty_conn()
    result = get_architecture_overview(conn)
    assert set(result.keys()) == {"packages", "hotspots", "http_service_map", "stats"}


# ---------------------------------------------------------------------------
# Test 2: Empty sections return empty lists, never errors
# ---------------------------------------------------------------------------

def test_empty_sections_return_empty_lists():
    conn = _empty_conn()
    result = get_architecture_overview(conn)
    assert result["packages"] == []
    assert result["hotspots"] == []
    assert result["http_service_map"] == []


# ---------------------------------------------------------------------------
# Test 3: Stats keys present even on an empty graph
# ---------------------------------------------------------------------------

def test_stats_keys_on_empty_graph():
    conn = _empty_conn()
    result = get_architecture_overview(conn)
    stats = result["stats"]
    assert stats["total_files"] == 0
    assert stats["total_symbols"] == 0
    assert stats["total_packages"] == 0
    assert stats["total_endpoints"] == 0
    assert stats["files_by_language"] == {}


# ---------------------------------------------------------------------------
# Test 4: Hotspot query excludes test AND vendored methods
# ---------------------------------------------------------------------------

def test_hotspots_exclude_test_and_vendored_methods():
    conn = _empty_conn()
    get_architecture_overview(conn)
    hotspot_call = next(
        c for c in conn.query.call_args_list
        if "NOT m.file_path =~ $test_pattern" in (c.args[0] if c.args else "")
    )
    _, params = hotspot_call.args[0], hotspot_call.args[1]
    assert params.get("test_pattern") == _TEST_PATH_PATTERN
    assert params.get("vendor_pattern") == _VENDORED_PATH_PATTERN


# ---------------------------------------------------------------------------
# Test 5: limit=5 passed to hotspot query
# ---------------------------------------------------------------------------

def test_hotspots_limit_passed_to_query():
    conn = _conn_with_side_effects([], [], [], [], [], [], [], [])
    get_architecture_overview(conn, limit=5)
    hotspot_call = next(
        c for c in conn.query.call_args_list
        if "$limit" in (c.args[0] if c.args else "")
    )
    cypher, params = hotspot_call.args[0], hotspot_call.args[1]
    assert "LIMIT $limit" in cypher
    assert params.get("limit") == 5


# ---------------------------------------------------------------------------
# Test 6: Default limit is 10
# ---------------------------------------------------------------------------

def test_hotspot_default_limit_is_10():
    conn = _empty_conn()
    get_architecture_overview(conn)
    hotspot_call = next(
        c for c in conn.query.call_args_list
        if "$limit" in (c.args[0] if c.args else "")
    )
    _, params = hotspot_call.args[0], hotspot_call.args[1]
    assert params.get("limit") == 10


# ---------------------------------------------------------------------------
# Test 7: Populated packages query maps rows correctly
# ---------------------------------------------------------------------------

def test_packages_populated():
    # Rows: (name, file_count, symbol_count)
    pkg_rows = [("MyApp.Services", 3, 12), ("MyApp.Controllers", 5, 8)]
    # Query order: packages, total_pkg_count, hotspots, serves, calls, lang, symbols, endpoints
    conn = _conn_with_side_effects(pkg_rows, [[2]], [], [], [], [], [], [])
    result = get_architecture_overview(conn)
    assert len(result["packages"]) == 2
    first = result["packages"][0]
    assert "name" in first
    assert "file_count" in first
    assert "symbol_count" in first
    assert first["name"] == "MyApp.Services"
    assert first["file_count"] == 3
    assert first["symbol_count"] == 12


# ---------------------------------------------------------------------------
# Test 8: Populated hotspots query maps rows correctly
# ---------------------------------------------------------------------------

def test_hotspots_populated():
    # Rows: (full_name, file_path, line, inbound_callers)
    hotspot_rows = [
        ("MyApp.Services.FooService.DoWork", "/src/FooService.cs", 42, 15),
        ("MyApp.Services.BarService.Run", "/src/BarService.cs", 10, 9),
    ]
    conn = _conn_with_side_effects([], [], hotspot_rows, [], [], [], [], [])
    result = get_architecture_overview(conn)
    assert len(result["hotspots"]) == 2
    first = result["hotspots"][0]
    assert first["full_name"] == "MyApp.Services.FooService.DoWork"
    assert first["file_path"] == "/src/FooService.cs"
    assert first["line"] == 42
    assert first["inbound_callers"] == 15


# ---------------------------------------------------------------------------
# Test 9: HTTP service map SERVES entries have direction="serves"
# ---------------------------------------------------------------------------

def test_http_service_map_serves_direction():
    # Rows: (route, http_method, handler_full_name, file_path)
    serves_rows = [("GET /api/items", "GET", "MyApp.ItemsController.GetAll", "/src/ItemsController.cs")]
    conn = _conn_with_side_effects([], [], [], serves_rows, [], [], [], [])
    result = get_architecture_overview(conn)
    serves_entries = [e for e in result["http_service_map"] if e["direction"] == "serves"]
    assert len(serves_entries) == 1
    entry = serves_entries[0]
    assert entry["route"] == "GET /api/items"
    assert entry["direction"] == "serves"


# ---------------------------------------------------------------------------
# Test 10: HTTP service map HTTP_CALLS entries have direction="calls"
# ---------------------------------------------------------------------------

def test_http_service_map_calls_direction():
    # Rows for calls query: (route, http_method, caller_full_name, file_path)
    calls_rows = [("POST /external/api", "POST", "MyApp.HttpClient.Post", "/src/Client.cs")]
    conn = _conn_with_side_effects([], [], [], [], calls_rows, [], [], [])
    result = get_architecture_overview(conn)
    calls_entries = [e for e in result["http_service_map"] if e["direction"] == "calls"]
    assert len(calls_entries) == 1
    entry = calls_entries[0]
    assert entry["direction"] == "calls"
    assert entry["route"] == "POST /external/api"


# ---------------------------------------------------------------------------
# Test 11: files_by_language derived from query results
# ---------------------------------------------------------------------------

def test_stats_files_by_language():
    # Query 6 (files by language): rows are (language, count)
    lang_rows = [("csharp", 10), ("python", 5)]
    conn = _conn_with_side_effects([], [], [], [], [], lang_rows, [], [])
    result = get_architecture_overview(conn)
    assert result["stats"]["files_by_language"] == {"csharp": 10, "python": 5}
    assert result["stats"]["total_files"] == 15


# ---------------------------------------------------------------------------
# Test 12: packages_shown and total_packages in stats
# ---------------------------------------------------------------------------

def test_stats_packages_shown_vs_total():
    pkg_rows = [("Pkg1", 1, 10)]
    total_pkg = [[5]]  # 5 total packages, but only 1 shown due to LIMIT
    conn = _conn_with_side_effects(pkg_rows, total_pkg, [], [], [], [], [], [])
    result = get_architecture_overview(conn, max_packages=1)
    assert result["stats"]["total_packages"] == 5
    assert result["stats"]["packages_shown"] == 1


# ---------------------------------------------------------------------------
# Regression: file_count derived from symbol file_path, not IMPORTS edges
# ---------------------------------------------------------------------------

def test_package_file_count_uses_symbol_file_path():
    """Query 1 must count files via Class/Interface file_path, not IMPORTS edges."""
    conn = _empty_conn()
    get_architecture_overview(conn)
    pkg_cypher = conn.query.call_args_list[0].args[0]
    # Must NOT use the broken IMPORTS-based approach
    assert "IMPORTS" not in pkg_cypher
    # Must derive file_count from symbol file_path
    assert "s.file_path" in pkg_cypher or "file_path" in pkg_cypher


# ---------------------------------------------------------------------------
# Regression: total_symbols must include Package nodes to match list_projects
# ---------------------------------------------------------------------------

def test_stats_symbol_count_includes_packages():
    """Query 6 must count Package nodes alongside Class/Interface/Method/Property/Field."""
    conn = _empty_conn()
    get_architecture_overview(conn)
    # Query 6 is the symbol count query — find it by checking for "count(s)"
    symbol_query = next(
        c for c in conn.query.call_args_list
        if "count(s)" in (c.args[0] if c.args else "")
    )
    cypher = symbol_query.args[0]
    assert "s:Package" in cypher
