from __future__ import annotations

import tree_sitter_python
from tree_sitter import Language, Parser

from synapse.indexer.python.python_http_extractor import PythonHttpExtractor
from synapse.lsp.interface import IndexSymbol, SymbolKind

_lang = Language(tree_sitter_python.language())
_parser = Parser(_lang)


def _parse(source: str):
    return _parser.parse(bytes(source, "utf-8"))


def _symbols(pairs: list[tuple[str, str, int, int]]) -> list[IndexSymbol]:
    """Build IndexSymbol list from (name, full_name, line, end_line) tuples."""
    return [
        IndexSymbol(name=n, full_name=fn, kind=SymbolKind.METHOD, file_path="test.py", line=ln, end_line=el)
        for n, fn, ln, el in pairs
    ]


# ──────────────────────────────────────────────
# FastAPI endpoint extraction
# ──────────────────────────────────────────────


def test_fastapi_get_decorator() -> None:
    source = """\
from fastapi import FastAPI
app = FastAPI()

@app.get("/items")
async def list_items():
    pass
"""
    extractor = PythonHttpExtractor()
    result = extractor.extract("test.py", _parse(source), _symbols([("list_items", "api.list_items", 5, 6)]))
    assert len(result.endpoint_defs) == 1
    ep = result.endpoint_defs[0]
    assert ep.route == "/items"
    assert ep.http_method == "GET"
    assert ep.handler_full_name == "api.list_items"


def test_fastapi_post_decorator() -> None:
    source = """\
from fastapi import FastAPI
app = FastAPI()

@app.post("/items")
async def create_item():
    pass
"""
    extractor = PythonHttpExtractor()
    result = extractor.extract("test.py", _parse(source), _symbols([("create_item", "api.create_item", 5, 6)]))
    assert len(result.endpoint_defs) == 1
    assert result.endpoint_defs[0].http_method == "POST"


def test_fastapi_path_param_preserved() -> None:
    source = """\
@app.get("/items/{item_id}")
async def get_item(item_id: int):
    pass
"""
    extractor = PythonHttpExtractor()
    result = extractor.extract("test.py", _parse(source), _symbols([("get_item", "api.get_item", 2, 3)]))
    assert len(result.endpoint_defs) == 1
    assert result.endpoint_defs[0].route == "/items/{item_id}"


def test_fastapi_router_decorator() -> None:
    source = """\
from fastapi import APIRouter
router = APIRouter()

@router.post("/items")
async def create_item():
    pass
"""
    extractor = PythonHttpExtractor()
    result = extractor.extract("test.py", _parse(source), _symbols([("create_item", "api.create_item", 5, 6)]))
    assert len(result.endpoint_defs) == 1
    assert result.endpoint_defs[0].http_method == "POST"
    assert result.endpoint_defs[0].route == "/items"


def test_fastapi_all_verbs() -> None:
    source = """\
@app.get("/x")
def fn_get(): pass

@app.post("/x")
def fn_post(): pass

@app.put("/x")
def fn_put(): pass

@app.delete("/x")
def fn_delete(): pass

@app.patch("/x")
def fn_patch(): pass
"""
    extractor = PythonHttpExtractor()
    syms = _symbols([
        ("fn_get", "mod.fn_get", 2, 2),
        ("fn_post", "mod.fn_post", 5, 5),
        ("fn_put", "mod.fn_put", 8, 8),
        ("fn_delete", "mod.fn_delete", 11, 11),
        ("fn_patch", "mod.fn_patch", 14, 14),
    ])
    result = extractor.extract("test.py", _parse(source), syms)
    methods = {ep.http_method for ep in result.endpoint_defs}
    assert methods == {"GET", "POST", "PUT", "DELETE", "PATCH"}


# ──────────────────────────────────────────────
# Flask endpoint extraction
# ──────────────────────────────────────────────


def test_flask_route_get() -> None:
    source = """\
from flask import Flask
app = Flask(__name__)

@app.route("/items", methods=["GET"])
def list_items():
    pass
"""
    extractor = PythonHttpExtractor()
    result = extractor.extract("test.py", _parse(source), _symbols([("list_items", "app.list_items", 5, 6)]))
    assert len(result.endpoint_defs) == 1
    ep = result.endpoint_defs[0]
    assert ep.route == "/items"
    assert ep.http_method == "GET"
    assert ep.handler_full_name == "app.list_items"


def test_flask_route_multiple_methods() -> None:
    source = """\
@app.route("/items", methods=["GET", "POST"])
def items():
    pass
"""
    extractor = PythonHttpExtractor()
    result = extractor.extract("test.py", _parse(source), _symbols([("items", "app.items", 2, 3)]))
    assert len(result.endpoint_defs) == 2
    pairs = {(ep.route, ep.http_method) for ep in result.endpoint_defs}
    assert ("/items", "GET") in pairs
    assert ("/items", "POST") in pairs


def test_flask_route_param_normalized() -> None:
    source = """\
@app.route("/items/<int:item_id>")
def get_item(item_id):
    pass
"""
    extractor = PythonHttpExtractor()
    result = extractor.extract("test.py", _parse(source), _symbols([("get_item", "app.get_item", 2, 3)]))
    assert len(result.endpoint_defs) >= 1
    assert result.endpoint_defs[0].route == "/items/{item_id}"


def test_flask_route_no_methods_defaults_to_get() -> None:
    """Flask @app.route without methods= defaults to GET."""
    source = """\
@app.route("/items")
def list_items():
    pass
"""
    extractor = PythonHttpExtractor()
    result = extractor.extract("test.py", _parse(source), _symbols([("list_items", "app.list_items", 2, 3)]))
    assert len(result.endpoint_defs) == 1
    assert result.endpoint_defs[0].http_method == "GET"


def test_flask_shorthand_get() -> None:
    """Flask 2.0+ @app.get() shorthand."""
    source = """\
@app.get("/items")
def list_items():
    pass
"""
    extractor = PythonHttpExtractor()
    result = extractor.extract("test.py", _parse(source), _symbols([("list_items", "app.list_items", 2, 3)]))
    assert len(result.endpoint_defs) == 1
    assert result.endpoint_defs[0].http_method == "GET"
    assert result.endpoint_defs[0].route == "/items"


def test_flask_blueprint_route() -> None:
    source = """\
@bp.route("/items/<string:name>")
def get_item(name):
    pass
"""
    extractor = PythonHttpExtractor()
    result = extractor.extract("test.py", _parse(source), _symbols([("get_item", "app.get_item", 2, 3)]))
    assert len(result.endpoint_defs) >= 1
    assert result.endpoint_defs[0].route == "/items/{name}"


# ──────────────────────────────────────────────
# Django REST endpoint extraction
# ──────────────────────────────────────────────


def test_django_modelviewset_conventional_routes() -> None:
    source = """\
from rest_framework.viewsets import ModelViewSet

class UserViewSet(ModelViewSet):
    def list(self, request):
        pass
    def create(self, request):
        pass
    def retrieve(self, request, pk=None):
        pass
"""
    extractor = PythonHttpExtractor()
    syms = _symbols([
        ("UserViewSet", "views.UserViewSet", 3, 9),
        ("list", "views.UserViewSet.list", 4, 5),
        ("create", "views.UserViewSet.create", 6, 7),
        ("retrieve", "views.UserViewSet.retrieve", 8, 9),
    ])
    result = extractor.extract("test.py", _parse(source), syms)
    routes = {(ep.route, ep.http_method) for ep in result.endpoint_defs}
    assert ("/user", "GET") in routes
    assert ("/user", "POST") in routes
    assert ("/user/{id}", "GET") in routes


def test_django_apiview_get_method() -> None:
    source = """\
from rest_framework.views import APIView

class UserView(APIView):
    def get(self, request):
        pass
"""
    extractor = PythonHttpExtractor()
    syms = _symbols([
        ("UserView", "views.UserView", 3, 5),
        ("get", "views.UserView.get", 4, 5),
    ])
    result = extractor.extract("test.py", _parse(source), syms)
    routes = {(ep.route, ep.http_method) for ep in result.endpoint_defs}
    assert ("/user", "GET") in routes


def test_django_api_view_decorator() -> None:
    source = """\
from rest_framework.decorators import api_view

@api_view(["GET"])
def list_users(request):
    pass
"""
    extractor = PythonHttpExtractor()
    result = extractor.extract("test.py", _parse(source), _symbols([("list_users", "views.list_users", 4, 5)]))
    assert len(result.endpoint_defs) == 1
    assert result.endpoint_defs[0].http_method == "GET"


# ──────────────────────────────────────────────
# requests client call extraction
# ──────────────────────────────────────────────


def test_requests_get() -> None:
    source = """\
import requests

def fetch_users():
    return requests.get("/api/users")
"""
    extractor = PythonHttpExtractor()
    result = extractor.extract("test.py", _parse(source), _symbols([("fetch_users", "mod.fetch_users", 3, 4)]))
    assert len(result.client_calls) == 1
    call = result.client_calls[0]
    assert call.route == "/api/users"
    assert call.http_method == "GET"
    assert call.caller_full_name == "mod.fetch_users"


def test_requests_post() -> None:
    source = """\
import requests

def create_user(data):
    return requests.post("/api/users", json=data)
"""
    extractor = PythonHttpExtractor()
    result = extractor.extract("test.py", _parse(source), _symbols([("create_user", "mod.create_user", 3, 4)]))
    assert len(result.client_calls) == 1
    assert result.client_calls[0].http_method == "POST"


def test_requests_fstring_url() -> None:
    source = """\
import requests

def fetch_user(user_id):
    return requests.get(f"/api/users/{user_id}")
"""
    extractor = PythonHttpExtractor()
    result = extractor.extract("test.py", _parse(source), _symbols([("fetch_user", "mod.fetch_user", 3, 4)]))
    assert len(result.client_calls) == 1
    assert result.client_calls[0].route == "/api/users/{user_id}"


def test_requests_all_verbs() -> None:
    source = """\
import requests

def sync():
    requests.get("/api/x")
    requests.post("/api/x")
    requests.put("/api/x")
    requests.delete("/api/x")
    requests.patch("/api/x")
"""
    extractor = PythonHttpExtractor()
    result = extractor.extract("test.py", _parse(source), _symbols([("sync", "mod.sync", 3, 9)]))
    methods = {c.http_method for c in result.client_calls}
    assert methods == {"GET", "POST", "PUT", "DELETE", "PATCH"}


def test_requests_outside_function_skipped() -> None:
    source = """\
import requests
requests.get("/api/users")
"""
    extractor = PythonHttpExtractor()
    result = extractor.extract("test.py", _parse(source), [])
    assert len(result.client_calls) == 0


def test_requests_url_without_slash_skipped() -> None:
    source = """\
import requests

def fetch():
    return requests.get("some-key")
"""
    extractor = PythonHttpExtractor()
    result = extractor.extract("test.py", _parse(source), _symbols([("fetch", "mod.fetch", 3, 4)]))
    assert len(result.client_calls) == 0


def test_requests_constant_url_resolution() -> None:
    source = """\
import requests

USERS_URL = "/api/users"

def fetch():
    return requests.get(USERS_URL)
"""
    extractor = PythonHttpExtractor()
    result = extractor.extract("test.py", _parse(source), _symbols([("fetch", "mod.fetch", 6, 7)]))
    assert len(result.client_calls) == 1
    assert result.client_calls[0].route == "/api/users"


# ──────────────────────────────────────────────
# Edge cases
# ──────────────────────────────────────────────


def test_non_http_decorator_skipped() -> None:
    source = """\
@login_required
def protected_view():
    pass
"""
    extractor = PythonHttpExtractor()
    result = extractor.extract("test.py", _parse(source), _symbols([("protected_view", "mod.protected_view", 2, 3)]))
    assert len(result.endpoint_defs) == 0


def test_empty_source() -> None:
    extractor = PythonHttpExtractor()
    result = extractor.extract("test.py", _parse(""), [])
    assert result.endpoint_defs == []
    assert result.client_calls == []


def test_both_server_and_client_in_same_file() -> None:
    source = """\
import requests
from fastapi import FastAPI
app = FastAPI()

@app.get("/items")
async def list_items():
    pass

def fetch_external():
    return requests.get("/external/items")
"""
    extractor = PythonHttpExtractor()
    syms = _symbols([
        ("list_items", "api.list_items", 6, 7),
        ("fetch_external", "api.fetch_external", 9, 10),
    ])
    result = extractor.extract("test.py", _parse(source), syms)
    assert len(result.endpoint_defs) == 1
    assert len(result.client_calls) == 1


# ---------------------------------------------------------------------------
# _find_enclosing_symbol narrowest-range tests -- PROD-04 regression
# ---------------------------------------------------------------------------

from synapse.indexer.python.python_http_extractor import _find_enclosing_symbol


def test_find_enclosing_symbol_nested_class_narrowest_range() -> None:
    """PROD-04: when two sibling inner classes overlap at a call site, the narrower one wins.

    Sibling scenario: Inner1 (5-15, span=10) starts before Inner2 (8-20, span=12).
    Both contain line 12. Narrowest-range must return Inner1, not Inner2.
    Last-match (current bug) returns Inner2 because it starts later in sorted order.
    """
    symbols = [
        (1, 100, "OuterClass.outerMethod"),
        (5, 15, "OuterClass.Inner1.inner1Method"),
        (8, 20, "OuterClass.Inner2.inner2Method"),
    ]
    assert _find_enclosing_symbol(12, symbols) == "OuterClass.Inner1.inner1Method"


def test_find_enclosing_symbol_outer_only_when_not_in_inner() -> None:
    symbols = [
        (1, 50, "OuterClass.outerMethod"),
        (10, 20, "OuterClass.InnerClass.innerMethod"),
    ]
    assert _find_enclosing_symbol(5, symbols) == "OuterClass.outerMethod"


def test_find_enclosing_symbol_single_symbol() -> None:
    symbols = [(1, 50, "OuterClass.outerMethod")]
    assert _find_enclosing_symbol(15, symbols) == "OuterClass.outerMethod"
