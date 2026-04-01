"""Integration tests for HTTP endpoint extraction.

Requires Memgraph on localhost:7687 and .NET SDK.
Run with: pytest tests/integration/test_http_endpoints.py -v -m integration
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_endpoint_nodes_created(http_service) -> None:
    """Verify Endpoint nodes are created for each controller action."""
    _svc, conn = http_service
    result = conn.query(
        "MATCH (ep:Endpoint) RETURN ep.route, ep.http_method ORDER BY ep.route, ep.http_method"
    )
    routes = [(r[0], r[1]) for r in result]
    assert ("/api/task", "GET") in routes
    assert ("/api/task", "POST") in routes
    assert ("/api/task/{id}", "GET") in routes
    assert ("/api/task/{id}", "PUT") in routes
    assert ("/api/task/{id}", "DELETE") in routes
    assert ("/api/task/{id}/complete", "POST") in routes


def test_serves_edges_created(http_service) -> None:
    """Verify SERVES edges connect controller methods to their Endpoint nodes."""
    _svc, conn = http_service
    result = conn.query(
        "MATCH (m:Method)-[:SERVES]->(ep:Endpoint) "
        "RETURN m.full_name, ep.route, ep.http_method"
    )
    serves = [(r[0], r[1], r[2]) for r in result]
    assert len(serves) > 0
    assert any("Get" in s[0] and s[1] == "/api/task/{id}" and s[2] == "GET" for s in serves)
    assert any("Create" in s[0] and s[1] == "/api/task" and s[2] == "POST" for s in serves)


def test_endpoint_contained_by_repository(http_service) -> None:
    """Verify every Endpoint is reachable from its Repository via CONTAINS."""
    _svc, conn = http_service
    result = conn.query(
        "MATCH (r:Repository)-[:CONTAINS]->(ep:Endpoint) RETURN count(ep)"
    )
    assert result[0][0] > 0


def test_endpoint_name_formatted(http_service) -> None:
    """Verify the Endpoint.name property follows the 'METHOD /route' convention."""
    _svc, conn = http_service
    result = conn.query(
        "MATCH (ep:Endpoint) WHERE ep.route = '/api/task' AND ep.http_method = 'GET' "
        "RETURN ep.name"
    )
    assert len(result) > 0
    assert result[0][0] == "GET /api/task"


# FastEndpoints integration tests (Phase 25)


@pytest.mark.timeout(10)
def test_fastendpoints_endpoint_nodes(http_service) -> None:
    """FastEndpoints classes produce Endpoint nodes with correct routes and verbs."""
    _svc, conn = http_service
    result = conn.query(
        "MATCH (ep:Endpoint) WHERE ep.route STARTS WITH '/api/todos' OR ep.route = '/api/health' "
        "RETURN ep.route, ep.http_method ORDER BY ep.route, ep.http_method"
    )
    routes = [(r[0], r[1]) for r in result]
    assert ("/api/health", "GET") in routes
    assert ("/api/todos", "POST") in routes


@pytest.mark.timeout(10)
def test_fastendpoints_serves_edges(http_service) -> None:
    """SERVES edges connect TodoEndpoint.HandleAsync to its Endpoint node."""
    _svc, conn = http_service
    result = conn.query(
        "MATCH (m:Method)-[:SERVES]->(ep:Endpoint) "
        "WHERE m.full_name STARTS WITH 'SynappsTest.Endpoints.TodoEndpoint' "
        "RETURN m.full_name, ep.route, ep.http_method"
    )
    assert len(result) >= 1
    row = result[0]
    assert "HandleAsync" in row[0]
    assert row[1] == "/api/todos"
    assert row[2] == "POST"


@pytest.mark.timeout(10)
def test_fastendpoints_multi_declaration(http_service) -> None:
    """MultiEndpoint with Verbs() and Routes() produces 4 Endpoint nodes (2 verbs x 2 routes)."""
    _svc, conn = http_service
    result = conn.query(
        "MATCH (m:Method)-[:SERVES]->(ep:Endpoint) "
        "WHERE m.full_name = 'SynappsTest.Endpoints.MultiEndpoint.HandleAsync' "
        "RETURN ep.route, ep.http_method ORDER BY ep.route, ep.http_method"
    )
    assert len(result) == 4
    pairs = [(r[0], r[1]) for r in result]
    assert ("/api/items", "POST") in pairs
    assert ("/api/items", "PUT") in pairs
    assert ("/api/things", "POST") in pairs
    assert ("/api/things", "PUT") in pairs


# IEndpointGroup integration tests (Phase 25)


@pytest.mark.timeout(10)
def test_endpoint_group_nodes(http_service) -> None:
    """TodoItems IEndpointGroup produces SERVES edges for GetAllTodos (GET) and CreateTodo (POST)."""
    _svc, conn = http_service
    result = conn.query(
        "MATCH (m:Method)-[:SERVES]->(ep:Endpoint) "
        "WHERE m.full_name STARTS WITH 'SynappsTest.Endpoints.TodoItems' "
        "RETURN m.full_name, ep.route, ep.http_method ORDER BY ep.http_method"
    )
    assert len(result) == 2
    full_names = [r[0] for r in result]
    verbs = [r[2] for r in result]
    assert any("GetAllTodos" in fn for fn in full_names)
    assert any("CreateTodo" in fn for fn in full_names)
    assert "GET" in verbs
    assert "POST" in verbs


@pytest.mark.timeout(10)
def test_endpoint_group_base_class(http_service) -> None:
    """ItemGroup (EndpointGroupBase) produces a SERVES edge for DeleteItem (DELETE /items/{id})."""
    _svc, conn = http_service
    result = conn.query(
        "MATCH (m:Method)-[:SERVES]->(ep:Endpoint) "
        "WHERE m.full_name STARTS WITH 'SynappsTest.Endpoints.ItemGroup' "
        "RETURN m.full_name, ep.route, ep.http_method"
    )
    assert len(result) == 1
    row = result[0]
    assert "DeleteItem" in row[0]
    assert row[1] == "/items/{id}"
    assert row[2] == "DELETE"


# False-positive guard (Phase 25)


@pytest.mark.timeout(10)
def test_non_endpoint_class_produces_zero_endpoints(http_service) -> None:
    """FakeService.Post() and FakeService.Get() must not generate any Endpoint nodes."""
    _svc, conn = http_service

    result = conn.query(
        "MATCH (m:Method)-[:SERVES]->(ep:Endpoint) "
        "WHERE m.full_name STARTS WITH 'SynappsTest.Endpoints.FakeService' "
        "RETURN count(ep) AS cnt"
    )
    cnt = result[0][0] if result else 0
    assert cnt == 0

    result2 = conn.query(
        "MATCH (ep:Endpoint) WHERE ep.handler_full_name STARTS WITH 'SynappsTest.Endpoints.FakeService' "
        "RETURN count(ep) AS cnt"
    )
    cnt2 = result2[0][0] if result2 else 0
    assert cnt2 == 0


# Minimal API integration tests (Phase 29 / MA-01..MA-03)


@pytest.mark.timeout(10)
def test_minimal_api_endpoint_nodes(http_service) -> None:
    """Standalone MapGet/MapPost/MapDelete calls produce Endpoint nodes with SERVES edges. (MA-01)"""
    _svc, conn = http_service
    result = conn.query(
        "MATCH (m:Method)-[:SERVES]->(ep:Endpoint) "
        "WHERE m.full_name STARTS WITH 'SynappsTest.Endpoints.MinimalApiEndpoints' "
        "RETURN m.full_name, ep.route, ep.http_method ORDER BY ep.route, ep.http_method"
    )
    assert len(result) >= 3, f"Expected at least 3 endpoints, got {len(result)}: {result}"
    routes = [(r[1], r[2]) for r in result]
    # MA-02: method ref handler resolves to GetAllItems
    assert ("/minimal/items", "GET") in routes
    get_row = next(r for r in result if r[1] == "/minimal/items" and r[2] == "GET")
    assert "GetAllItems" in get_row[0], f"Expected GetAllItems in handler: {get_row[0]}"
    # MA-03: lambda handler produces endpoint (handler resolves to enclosing method)
    assert ("/minimal/items", "POST") in routes
    # MA-02: method ref handler resolves to DeleteItem
    assert ("/minimal/items/{id}", "DELETE") in routes
    delete_row = next(r for r in result if r[1] == "/minimal/items/{id}" and r[2] == "DELETE")
    assert "DeleteItem" in delete_row[0], f"Expected DeleteItem in handler: {delete_row[0]}"


@pytest.mark.timeout(10)
def test_minimal_api_no_iendpointgroup_duplicate(http_service) -> None:
    """TodoItems IEndpointGroup endpoints are not duplicated by Minimal API detection."""
    _svc, conn = http_service
    result = conn.query(
        "MATCH (ep:Endpoint) WHERE ep.route IN ['/', '/items/{id}'] "
        "WITH ep.route AS route, ep.http_method AS method "
        "RETURN route, method, count(*) AS cnt "
        "ORDER BY route, method"
    )
    # Each route+method combination must appear exactly once (no duplicates)
    for row in result:
        assert row[2] == 1, f"Duplicate endpoint detected: route={row[0]} method={row[1]} count={row[2]}"
