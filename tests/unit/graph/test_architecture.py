"""Unit tests for get_architecture_overview in analysis.py.

Tests cover:
- Stats query includes Package and Endpoint nodes (BUG-05)
- http_service_map contains only serves-direction entries, not client calls (BUG-06)
"""
from __future__ import annotations

from unittest.mock import MagicMock, call

from synapps.graph.analysis import get_architecture_overview


def _make_conn(*query_results):
    """Return a mock GraphConnection that returns sequential query results.

    After the explicit results are exhausted, further calls return [].
    This prevents StopIteration errors when query count varies between
    code versions (e.g., before vs. after BUG-06 fix).
    """
    conn = MagicMock()
    results = list(query_results)

    def _side_effect(*args, **kwargs):
        if results:
            return results.pop(0)
        return []

    conn.query.side_effect = _side_effect
    return conn


def _arch_conn(
    pkg_rows=None,
    total_pkg=None,
    hotspot_rows=None,
    serves_rows=None,
    lang_rows=None,
    symbol_count=None,
    endpoint_count=None,
):
    """Build a mock conn for get_architecture_overview with controlled per-query results.

    Query order in get_architecture_overview:
      1. pkg_rows       (packages)
      2. total_pkg      (total package count)
      3. hotspot_rows   (hotspots)
      4. serves_rows    (HTTP served endpoints)
      5. lang_rows      (files by language)
      6. symbol_count   (total symbols)
      7. endpoint_count (total endpoints)

    Note: After the fix (BUG-06), Query 4 (client calls) is removed, so only
    7 queries run. Before the fix, an 8th query (client calls) ran when
    remaining > 0. The helper always provides enough side effects.
    """
    return _make_conn(
        pkg_rows or [],
        total_pkg or [(0,)],
        hotspot_rows or [],
        serves_rows or [],
        lang_rows or [],
        symbol_count or [(0,)],
        endpoint_count or [(0,)],
    )


# ---------------------------------------------------------------------------
# BUG-05: Stats query must include Package and Endpoint labels
# ---------------------------------------------------------------------------

def test_get_architecture_stats_include_package_and_endpoint():
    """The Cypher query for total_symbols must include Package and Endpoint nodes.

    Previously the query only counted Class/Interface/Method/Property/Field,
    causing a mismatch with list_projects symbol counts.
    """
    conn = _arch_conn()
    get_architecture_overview(conn)

    # Query 6 (0-indexed: index 5) is the symbol count query
    all_calls = conn.query.call_args_list
    # Find the query that includes "count(s)" — that's the symbol count query
    symbol_query_call = None
    for c in all_calls:
        cypher = c.args[0]
        if "count(s)" in cypher:
            symbol_query_call = cypher
            break

    assert symbol_query_call is not None, "Symbol count query not found in conn.query calls"
    assert "s:Package" in symbol_query_call, "Package nodes missing from symbol count query"
    assert "s:Endpoint" in symbol_query_call, "Endpoint nodes missing from symbol count query"


# ---------------------------------------------------------------------------
# BUG-06: http_service_map must be serves-only (no client call entries)
# ---------------------------------------------------------------------------

def test_get_architecture_http_map_serves_only():
    """http_service_map must only contain server-side (serves direction) entries.

    Previously serves + calls was returned, including test client HTTP calls
    that add noise to the architectural view.
    """
    serves_rows = [
        ("/api/foo", "GET", "MyApp.FooHandler.Get", "/src/Foo.cs"),
        ("/api/bar", "POST", "MyApp.BarHandler.Post", "/src/Bar.cs"),
    ]
    conn = _arch_conn(serves_rows=serves_rows)
    result = get_architecture_overview(conn)

    assert all(
        entry["direction"] == "serves" for entry in result["http_service_map"]
    ), "http_service_map contains non-serves entries"
    assert len(result["http_service_map"]) == 2


def test_get_architecture_http_map_empty_when_no_serves():
    """http_service_map must be empty when there are no served endpoints."""
    conn = _arch_conn(serves_rows=[])
    result = get_architecture_overview(conn)
    assert result["http_service_map"] == []


def test_get_architecture_endpoints_shown_equals_len_serves():
    """endpoints_shown stat must equal number of serves entries only."""
    serves_rows = [
        ("/api/x", "GET", "App.X.Get", "/src/X.cs"),
    ]
    conn = _arch_conn(serves_rows=serves_rows)
    result = get_architecture_overview(conn)

    assert result["stats"]["endpoints_shown"] == len(serves_rows)


def test_get_architecture_http_map_does_not_include_client_calls():
    """No client-side HTTP_CALLS entries must appear in http_service_map.

    The calls (direction='calls') entries were noisy because integration test
    HTTP clients polluted the architecture map with test-originated URLs.
    """
    serves_rows = [("/api/items", "GET", "App.Items.List", "/src/Items.cs")]
    conn = _arch_conn(serves_rows=serves_rows)
    result = get_architecture_overview(conn)

    directions = {entry["direction"] for entry in result["http_service_map"]}
    assert "calls" not in directions, "Client-side 'calls' entries found in http_service_map"
