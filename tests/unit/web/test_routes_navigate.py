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
    svc._resolve.return_value = "A.B"
    svc.get_symbol_kind.return_value = "Class"
    svc.find_usages.return_value = "Found 3 usages"
    response = client.get("/api/find_usages?full_name=A.B")
    assert response.status_code == 200
    data = response.json()
    assert data["usages"] == "Found 3 usages"
    assert data["queried_kind"] == "Class"


def test_find_usages_returns_structured_json():
    """D-02: Web route passes structured=True, returns list of dicts with queried_kind."""
    client, svc = _make_client()
    svc._resolve.return_value = "A.B"
    svc.get_symbol_kind.return_value = "Class"
    svc.find_usages.return_value = [
        {"full_name": "A.Caller1", "kind": "Method", "file_path": "/src/a.cs", "line": 10},
        {"full_name": "B.Caller2", "kind": "Method", "file_path": "/src/b.cs", "line": 20},
    ]
    response = client.get("/api/find_usages?full_name=A.B")
    assert response.status_code == 200
    data = response.json()
    assert data["queried_kind"] == "Class"
    assert isinstance(data["usages"], list)
    assert len(data["usages"]) == 2
    assert data["usages"][0]["full_name"] == "A.Caller1"


def test_find_usages_structured_empty_list():
    """D-02: Structured mode returns empty list for symbols with no callers."""
    client, svc = _make_client()
    svc._resolve.return_value = "A.B"
    svc.get_symbol_kind.return_value = "Method"
    svc.find_usages.return_value = []
    response = client.get("/api/find_usages?full_name=A.B")
    assert response.status_code == 200
    data = response.json()
    assert data["usages"] == []
    assert data["queried_kind"] == "Method"


def test_find_callees_basic():
    client, svc = _make_client()
    svc._resolve.return_value = "A.B"
    svc.get_symbol_kind.return_value = "Method"
    svc.find_callees.return_value = [{"callee": "A.C"}]
    response = client.get("/api/find_callees?full_name=A.B")
    assert response.status_code == 200
    data = response.json()
    assert data["callees"] == [{"callee": "A.C"}]
    assert data["queried_kind"] == "Method"


def test_find_callees_with_depth_calls_get_call_depth():
    client, svc = _make_client()
    svc._resolve.return_value = "A.B"
    svc.get_symbol_kind.return_value = "Method"
    svc.get_call_depth.return_value = {"depth": 3, "calls": []}
    response = client.get("/api/find_callees?full_name=A.B&depth=3")
    assert response.status_code == 200
    data = response.json()
    assert data["queried_kind"] == "Method"
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
    svc._resolve.side_effect = ValueError("Symbol not found")
    response = client.get("/api/find_usages?full_name=X.Y")
    assert response.status_code == 400
    assert response.json()["detail"] == "Symbol not found"


def test_find_callees_value_error_returns_400():
    client, svc = _make_client()
    svc._resolve.side_effect = ValueError("Ambiguous name")
    response = client.get("/api/find_callees?full_name=A.B")
    assert response.status_code == 400
    assert response.json()["detail"] == "Ambiguous name"


def test_get_hierarchy_value_error_returns_400():
    client, svc = _make_client()
    svc.get_hierarchy.side_effect = ValueError("Not found")
    response = client.get("/api/get_hierarchy?full_name=A.B")
    assert response.status_code == 400
    assert response.json()["detail"] == "Not found"


def test_get_context_for_basic():
    client, svc = _make_client()
    svc.get_context_for.return_value = "## Target: A.B\n..."
    response = client.get("/api/get_context_for?full_name=A.B")
    assert response.status_code == 200
    assert response.json() == "## Target: A.B\n..."
    svc.get_context_for.assert_called_once_with("A.B", scope=None, max_lines=-1)


def test_get_context_for_with_scope():
    client, svc = _make_client()
    svc.get_context_for.return_value = "scoped"
    response = client.get("/api/get_context_for?full_name=A.B&scope=edit")
    assert response.status_code == 200
    svc.get_context_for.assert_called_once_with("A.B", scope="edit", max_lines=-1)


def test_get_context_for_value_error_returns_400():
    client, svc = _make_client()
    svc.get_context_for.side_effect = ValueError("Ambiguous")
    response = client.get("/api/get_context_for?full_name=X.Y")
    assert response.status_code == 400
    assert response.json()["detail"] == "Ambiguous"


def test_get_context_for_none_returns_404():
    client, svc = _make_client()
    svc.get_context_for.return_value = None
    response = client.get("/api/get_context_for?full_name=X.Y")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
