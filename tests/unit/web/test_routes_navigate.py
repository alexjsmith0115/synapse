from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from synapps.web.routes.navigate import router as navigate_router


def _make_client(service=None):
    svc = service or MagicMock()
    app = FastAPI()
    app.include_router(navigate_router(svc), prefix="/api")
    return TestClient(app), svc


def test_find_usages_basic():
    client, svc = _make_client()
    svc.find_usages.return_value = "Found 3 usages"
    response = client.get("/api/find_usages?full_name=A.B")
    assert response.status_code == 200
    assert response.json() == "Found 3 usages"
    svc.find_usages.assert_called_once_with("A.B", True, limit=20)


def test_find_callees_basic():
    client, svc = _make_client()
    svc.find_callees.return_value = [{"callee": "A.C"}]
    response = client.get("/api/find_callees?full_name=A.B")
    assert response.status_code == 200
    assert response.json() == [{"callee": "A.C"}]
    svc.find_callees.assert_called_once_with("A.B", True, limit=50)


def test_find_callees_with_depth_calls_get_call_depth():
    client, svc = _make_client()
    svc.get_call_depth.return_value = {"depth": 3, "calls": []}
    response = client.get("/api/find_callees?full_name=A.B&depth=3")
    assert response.status_code == 200
    svc.get_call_depth.assert_called_once_with("A.B", 3)
    svc.find_callees.assert_not_called()


def test_get_hierarchy_basic():
    client, svc = _make_client()
    svc.get_hierarchy.return_value = {"base": "object", "children": []}
    response = client.get("/api/get_hierarchy?full_name=A.B")
    assert response.status_code == 200
    assert response.json() == {"base": "object", "children": []}
    svc.get_hierarchy.assert_called_once_with("A.B")


def test_find_usages_value_error_returns_400():
    client, svc = _make_client()
    svc.find_usages.side_effect = ValueError("Symbol not found")
    response = client.get("/api/find_usages?full_name=X.Y")
    assert response.status_code == 400
    assert response.json()["detail"] == "Symbol not found"


def test_find_callees_value_error_returns_400():
    client, svc = _make_client()
    svc.find_callees.side_effect = ValueError("Ambiguous name")
    response = client.get("/api/find_callees?full_name=A.B")
    assert response.status_code == 400
    assert response.json()["detail"] == "Ambiguous name"


def test_get_hierarchy_value_error_returns_400():
    client, svc = _make_client()
    svc.get_hierarchy.side_effect = ValueError("Not found")
    response = client.get("/api/get_hierarchy?full_name=A.B")
    assert response.status_code == 400
    assert response.json()["detail"] == "Not found"
