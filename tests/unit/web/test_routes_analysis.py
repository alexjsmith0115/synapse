from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from synapps.web.routes.analysis import router as analysis_router


def _make_client(service=None):
    svc = service or MagicMock()
    app = FastAPI()
    app.include_router(analysis_router(svc), prefix="/api")
    return TestClient(app), svc


def test_get_architecture_basic():
    client, svc = _make_client()
    svc.get_architecture_overview.return_value = {"packages": [], "stats": {}}
    response = client.get("/api/get_architecture?path=/foo")
    assert response.status_code == 200
    assert response.json() == {"packages": [], "stats": {}}
    svc.get_architecture_overview.assert_called_once_with(limit=10)


def test_find_dead_code_basic():
    client, svc = _make_client()
    svc.find_dead_code.return_value = {"methods": [], "total": 0}
    response = client.get("/api/find_dead_code?path=/foo")
    assert response.status_code == 200
    assert response.json() == {"methods": [], "total": 0}
    svc.find_dead_code.assert_called_once_with(exclude_pattern="", limit=15, offset=0)


def test_find_dead_code_with_limit_and_offset():
    client, svc = _make_client()
    svc.find_dead_code.return_value = {"methods": [], "total": 0}
    response = client.get("/api/find_dead_code?path=/foo&limit=5&offset=10")
    assert response.status_code == 200
    svc.find_dead_code.assert_called_once_with(exclude_pattern="", limit=5, offset=10)


def test_find_untested_basic():
    client, svc = _make_client()
    svc.find_untested.return_value = {"methods": [], "total": 0}
    response = client.get("/api/find_untested?path=/foo")
    assert response.status_code == 200
    assert response.json() == {"methods": [], "total": 0}
    svc.find_untested.assert_called_once_with(exclude_pattern="", limit=15, offset=0)


def test_get_architecture_value_error_returns_400():
    client, svc = _make_client()
    svc.get_architecture_overview.side_effect = ValueError("No project indexed")
    response = client.get("/api/get_architecture?path=/foo")
    assert response.status_code == 400
    assert response.json()["detail"] == "No project indexed"


def test_find_dead_code_value_error_returns_400():
    client, svc = _make_client()
    svc.find_dead_code.side_effect = ValueError("Not indexed")
    response = client.get("/api/find_dead_code?path=/foo")
    assert response.status_code == 400
    assert response.json()["detail"] == "Not indexed"
