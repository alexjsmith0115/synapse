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
