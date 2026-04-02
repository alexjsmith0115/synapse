from __future__ import annotations

import re
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
    """Return a mock GraphConnection where all queries return empty lists (7 queries).

    Query order after BUG-06 fix (client calls query removed):
      1. packages
      2. total package count
      3. hotspots
      4. serves (HTTP server-side endpoints)
      5. files by language
      6. total symbol count
      7. total endpoint count
    """
    return _conn_with_side_effects([], [], [], [], [], [], [])


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
# Test 10: HTTP service map does NOT include client-side HTTP_CALLS entries
# (BUG-06 fix: client calls query removed to avoid noise from test HTTP clients)
# ---------------------------------------------------------------------------

def test_http_service_map_calls_direction():
    """After BUG-06 fix, http_service_map must not include direction='calls' entries.

    The old Query 4 (HTTP_CALLS client-side lookup) was removed because test
    HTTP clients populated the architecture map with integration-test originated URLs.
    """
    conn = _empty_conn()
    result = get_architecture_overview(conn)
    calls_entries = [e for e in result["http_service_map"] if e["direction"] == "calls"]
    assert len(calls_entries) == 0, (
        "http_service_map must not contain direction='calls' entries after BUG-06 fix"
    )


# ---------------------------------------------------------------------------
# Test 11: files_by_language derived from query results
# ---------------------------------------------------------------------------

def test_stats_files_by_language():
    # Query 5 (files by language, after BUG-06 removed Query 4 client calls):
    # rows are (language, count)
    lang_rows = [("csharp", 10), ("python", 5)]
    conn = _conn_with_side_effects([], [], [], [], lang_rows, [], [])
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
# Regression: _VENDORED_PATH_PATTERN must match CDN library files
# ---------------------------------------------------------------------------

def test_vendored_pattern_matches_cdn_libraries():
    """_VENDORED_PATH_PATTERN must catch popular CDN library files like angular.js."""
    # Named CDN library files in static directories
    assert re.match(_VENDORED_PATH_PATTERN, "/app/static/js/angular.js")
    assert re.match(_VENDORED_PATH_PATTERN, "/app/src/main/resources/static/lib/vue.js")
    # Minified files already covered
    assert re.match(_VENDORED_PATH_PATTERN, "/app/resources/static/jquery-3.6.0.min.js")
    # static/js/ directory path
    assert re.match(_VENDORED_PATH_PATTERN, "/project/static/js/some-lib.js")
    # Non-vendored file should NOT match
    assert not re.match(_VENDORED_PATH_PATTERN, "/app/src/main/java/com/example/MyClass.java")


# ---------------------------------------------------------------------------
# Regression: packages list must use full_name, not simple name
# ---------------------------------------------------------------------------

def test_packages_use_full_name():
    """Package query must return p.full_name so agents see fully-qualified package names."""
    pkg_rows = [("com.example.orderservice.service", 3, 15)]
    conn = _conn_with_side_effects(pkg_rows, [[1]], [], [], [], [], [], [])
    result = get_architecture_overview(conn)
    assert result["packages"][0]["name"] == "com.example.orderservice.service"


def test_package_query_uses_contains_edge():
    """Package query must traverse [:CONTAINS] edges, not STARTS WITH string matching.

    STARTS WITH fails for Java because Package nodes lack a '.' prefix convention;
    CONTAINS edges are written at indexing time and are always correct.
    """
    conn = _conn_with_side_effects([], [], [], [], [], [], [], [])
    get_architecture_overview(conn)
    # First query call is the package query
    pkg_cypher = conn.query.call_args_list[0].args[0]
    assert "[:CONTAINS]" in pkg_cypher
    assert "STARTS WITH" not in pkg_cypher
    assert "p.full_name" in pkg_cypher
