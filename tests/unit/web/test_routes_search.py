from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from synapps.web.routes.search import router as search_router


def _make_client(service=None):
    svc = service or MagicMock()
    app = FastAPI()
    app.include_router(search_router(svc), prefix="/api")
    return TestClient(app), svc


def test_search_symbols_basic():
    client, svc = _make_client()
    svc.search_symbols.return_value = [{"name": "Foo", "kind": "Class"}]
    response = client.get("/api/search_symbols?query=Foo")
    assert response.status_code == 200
    assert response.json() == [{"name": "Foo", "kind": "Class"}]
    svc.search_symbols.assert_called_once_with("Foo", None, None, None, None, limit=50)


def test_search_symbols_with_kind_and_limit():
    client, svc = _make_client()
    svc.search_symbols.return_value = [{"name": "FooClass", "kind": "Class"}]
    response = client.get("/api/search_symbols?query=Foo&kind=Class&limit=10")
    assert response.status_code == 200
    svc.search_symbols.assert_called_once_with("Foo", "Class", None, None, None, limit=10)


def test_search_symbols_missing_query_returns_422():
    client, _ = _make_client()
    response = client.get("/api/search_symbols")
    assert response.status_code == 422


def test_search_symbols_value_error_returns_400():
    client, svc = _make_client()
    svc.search_symbols.side_effect = ValueError("Ambiguous name")
    response = client.get("/api/search_symbols?query=Foo")
    assert response.status_code == 400
    assert response.json()["detail"] == "Ambiguous name"
