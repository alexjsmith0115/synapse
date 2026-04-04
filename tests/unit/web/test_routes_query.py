from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from synapps.web.routes.query import router as query_router


def _make_client(service=None):
    svc = service or MagicMock()
    app = FastAPI()
    app.include_router(query_router(svc), prefix="/api")
    return TestClient(app), svc


def test_execute_query_basic():
    client, svc = _make_client()
    svc.execute_query.return_value = [{"n": {"name": "Foo"}}]
    response = client.post("/api/execute_query", json={"cypher": "MATCH (n) RETURN n LIMIT 5"})
    assert response.status_code == 200
    assert response.json() == [{"n": {"name": "Foo"}}]
    svc.execute_query.assert_called_once_with("MATCH (n) RETURN n LIMIT 5")


def test_find_http_endpoints_basic():
    client, svc = _make_client()
    svc.find_http_endpoints.return_value = [{"route": "/items", "method": "GET"}]
    response = client.get("/api/find_http_endpoints")
    assert response.status_code == 200
    assert response.json() == [{"route": "/items", "method": "GET"}]
    svc.find_http_endpoints.assert_called_once_with(None, None, None, limit=50)


def test_find_http_endpoints_with_params():
    client, svc = _make_client()
    svc.find_http_endpoints.return_value = [{"route": "/items", "method": "GET"}]
    response = client.get("/api/find_http_endpoints?route=items&http_method=GET")
    assert response.status_code == 200
    svc.find_http_endpoints.assert_called_once_with("items", "GET", None, limit=50)


def test_execute_query_value_error_returns_400():
    client, svc = _make_client()
    svc.execute_query.side_effect = ValueError("Invalid Cypher")
    response = client.post("/api/execute_query", json={"cypher": "INVALID"})
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid Cypher"


def test_execute_query_requires_json_body():
    client, _ = _make_client()
    response = client.post("/api/execute_query")
    assert response.status_code == 422


def test_find_http_endpoints_value_error_returns_400():
    client, svc = _make_client()
    svc.find_http_endpoints.side_effect = ValueError("Not indexed")
    response = client.get("/api/find_http_endpoints")
    assert response.status_code == 400
    assert response.json()["detail"] == "Not indexed"
