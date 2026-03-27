"""Unit tests for find_http_endpoints and trace_http_dependency (lookups + service)."""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from conftest import _MockNode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _node(labels, props, element_id=None):
    return _MockNode(labels, props, element_id=element_id)


def _ep(route, http_method):
    """Create a mock Endpoint node."""
    return _node(["Endpoint"], {"route": route, "http_method": http_method})


def _method(full_name, file_path="/src/Api.cs", line=10, language="csharp"):
    return _node(["Method"], {
        "full_name": full_name, "file_path": file_path, "line": line, "language": language,
    })


# ---------------------------------------------------------------------------
# lookups.find_http_endpoints
# ---------------------------------------------------------------------------

def test_find_http_endpoints_query_returns_rows_with_has_server():
    from synapse.graph.lookups import find_http_endpoints as q_find_http_endpoints

    ep = _ep("/api/items", "GET")
    handler = _method("ItemsController.GetAll")
    conn = MagicMock()
    # Each row: [ep_node, has_server_bool, handler_node_or_None]
    conn.query.return_value = [[ep, True, handler]]

    result = q_find_http_endpoints(conn)
    assert len(result) == 1
    row_ep, has_server, row_handler = result[0]
    assert has_server is True


def test_find_http_endpoints_query_with_route_param():
    from synapse.graph.lookups import find_http_endpoints as q_find_http_endpoints

    ep = _ep("/api/items", "GET")
    conn = MagicMock()
    conn.query.return_value = [[ep, False, None]]

    q_find_http_endpoints(conn, route="items")

    cypher = conn.query.call_args[0][0]
    params = conn.query.call_args[0][1]
    assert "CONTAINS" in cypher
    assert params.get("route") == "items"


def test_find_http_endpoints_query_with_no_filters_returns_all():
    from synapse.graph.lookups import find_http_endpoints as q_find_http_endpoints

    ep1 = _ep("/api/items", "GET")
    ep2 = _ep("/api/orders", "POST")
    conn = MagicMock()
    conn.query.return_value = [[ep1, True, None], [ep2, False, None]]

    result = q_find_http_endpoints(conn)
    assert len(result) == 2


def test_find_http_endpoints_query_with_language_filter():
    from synapse.graph.lookups import find_http_endpoints as q_find_http_endpoints

    ep = _ep("/api/items", "GET")
    handler = _method("ItemsController.GetAll", language="csharp")
    conn = MagicMock()
    conn.query.return_value = [[ep, True, handler]]

    q_find_http_endpoints(conn, language="csharp")

    cypher = conn.query.call_args[0][0]
    params = conn.query.call_args[0][1]
    assert "handler.language" in cypher
    assert params.get("language") == "csharp"


# ---------------------------------------------------------------------------
# lookups.find_http_dependency
# ---------------------------------------------------------------------------

def test_find_http_dependency_query_returns_handler_and_callers():
    from synapse.graph.lookups import find_http_dependency

    ep = _ep("/api/items", "GET")
    handler = _method("ItemsController.GetAll")
    caller = _method("FrontendService.fetchItems", language="typescript")
    conn = MagicMock()
    # First query: ep + handler (via SERVES). Second query: callers (via HTTP_CALLS)
    conn.query.side_effect = [
        [[ep, handler]],
        [[caller]],
    ]

    result = find_http_dependency(conn, "/api/items", "GET")
    assert result["ep"] is ep
    assert result["handler"] is handler
    assert len(result["callers"]) == 1
    assert result["callers"][0] is caller


def test_find_http_dependency_no_handler_returns_none_handler():
    from synapse.graph.lookups import find_http_dependency

    ep = _ep("/api/external", "GET")
    conn = MagicMock()
    # No handler SERVES edge — handler is None in row
    conn.query.side_effect = [
        [[ep, None]],
        [],
    ]

    result = find_http_dependency(conn, "/api/external", "GET")
    assert result["handler"] is None
    assert result["callers"] == []


def test_find_http_dependency_no_ep_returns_none():
    from synapse.graph.lookups import find_http_dependency

    conn = MagicMock()
    conn.query.side_effect = [[], []]

    result = find_http_dependency(conn, "/api/missing", "DELETE")
    assert result["ep"] is None
    assert result["handler"] is None
    assert result["callers"] == []


# ---------------------------------------------------------------------------
# service.find_http_endpoints
# ---------------------------------------------------------------------------

def _make_service(conn):
    """Create a SynapseService backed by a mock connection with an empty project list."""
    from synapse.service import SynapseService
    service = SynapseService(conn)
    # Stub out project roots so _rel_path doesn't need DB
    service._project_roots = []
    return service


def test_service_find_http_endpoints_returns_d02_shape():
    ep = _ep("/api/items", "GET")
    handler = _method("ItemsController.GetAll", file_path="/repo/src/Api.cs", line=15)

    conn = MagicMock()
    service = _make_service(conn)

    with patch("synapse.service.query_find_http_endpoints", return_value=[[ep, True, handler]]):
        result = service.find_http_endpoints()

    assert isinstance(result, list)
    assert len(result) == 1
    item = result[0]
    assert item["route"] == "/api/items"
    assert item["http_method"] == "GET"
    assert item["has_server_handler"] is True
    assert item["handler_full_name"] == "ItemsController.GetAll"
    assert item["line"] == 15
    assert item["language"] == "csharp"


def test_service_find_http_endpoints_no_handler_fields_are_none():
    ep = _ep("/api/unknown", "POST")

    conn = MagicMock()
    service = _make_service(conn)

    with patch("synapse.service.query_find_http_endpoints", return_value=[[ep, False, None]]):
        result = service.find_http_endpoints()

    item = result[0]
    assert item["has_server_handler"] is False
    assert item["handler_full_name"] is None
    assert item["file_path"] is None
    assert item["line"] is None
    assert item["language"] is None


def test_service_find_http_endpoints_passes_language_filter():
    conn = MagicMock()
    service = _make_service(conn)

    with patch("synapse.service.query_find_http_endpoints", return_value=[]) as mock_lookup:
        service.find_http_endpoints(language="python")
        _, call_kwargs = mock_lookup.call_args
        assert call_kwargs.get("language") == "python"


# ---------------------------------------------------------------------------
# service.trace_http_dependency
# ---------------------------------------------------------------------------

def test_service_trace_http_dependency_returns_d03_shape():
    ep = _ep("/api/items", "GET")
    handler = _method("ItemsController.GetAll", file_path="/repo/src/Api.cs", line=15)
    caller = _method("FrontendService.fetchItems", file_path="/repo/src/fe.ts", line=42, language="typescript")

    conn = MagicMock()
    service = _make_service(conn)

    mock_dep_data = {"ep": ep, "handler": handler, "callers": [caller]}
    with patch("synapse.service.query_find_http_dependency", return_value=mock_dep_data):
        result = service.trace_http_dependency("/api/items", "GET")

    assert result["route"] == "/api/items"
    assert result["http_method"] == "GET"
    assert result["has_server_handler"] is True
    assert result["server_handler"] is not None
    assert result["server_handler"]["full_name"] == "ItemsController.GetAll"
    assert result["server_handler"]["line"] == 15
    assert result["server_handler"]["language"] == "csharp"
    assert len(result["client_callers"]) == 1
    assert result["client_callers"][0]["full_name"] == "FrontendService.fetchItems"


def test_service_trace_http_dependency_no_server_handler():
    ep = _ep("/api/external", "GET")
    caller = _method("FrontendService.fetchData", file_path="/repo/src/fe.ts", line=99, language="typescript")

    conn = MagicMock()
    service = _make_service(conn)

    mock_dep_data = {"ep": ep, "handler": None, "callers": [caller]}
    with patch("synapse.service.query_find_http_dependency", return_value=mock_dep_data):
        result = service.trace_http_dependency("/api/external", "GET")

    assert result["has_server_handler"] is False
    assert result["server_handler"] is None
    assert len(result["client_callers"]) == 1


def test_service_trace_http_dependency_no_ep_returns_false():
    conn = MagicMock()
    service = _make_service(conn)

    mock_dep_data = {"ep": None, "handler": None, "callers": []}
    with patch("synapse.service.query_find_http_dependency", return_value=mock_dep_data):
        result = service.trace_http_dependency("/api/missing", "DELETE")

    assert result["has_server_handler"] is False
    assert result["server_handler"] is None
    assert result["client_callers"] == []
