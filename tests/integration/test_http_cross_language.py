"""Cross-language HTTP endpoint matching tests.

Verifies that SERVES edges from one language's extractor match HTTP_CALLS edges
from another language's extractor via the route matcher.

This is a component-level test that exercises tree-sitter parsers and the
matcher directly — no Memgraph or external services required.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

import tree_sitter_python
import tree_sitter_typescript
from tree_sitter import Language, Parser

from synapps.indexer.http.matcher import match_endpoints
from synapps.indexer.python.python_http_extractor import PythonHttpExtractor
from synapps.indexer.typescript.typescript_http_extractor import TypeScriptHttpExtractor
from synapps.lsp.interface import IndexSymbol, SymbolKind

_py_lang = Language(tree_sitter_python.language())
_py_parser = Parser(_py_lang)

_ts_lang = Language(tree_sitter_typescript.language_typescript())
_ts_parser = Parser(_ts_lang)


def _py_parse(source: str):
    return _py_parser.parse(bytes(source, "utf-8"))


def _ts_parse(source: str):
    return _ts_parser.parse(bytes(source, "utf-8"))


def _py_symbols(pairs: list[tuple[str, str, int, int]]) -> list[IndexSymbol]:
    return [
        IndexSymbol(name=n, full_name=fn, kind=SymbolKind.METHOD, file_path="server.py", line=ln, end_line=el)
        for n, fn, ln, el in pairs
    ]


def _ts_symbols(pairs: list[tuple[str, str, int, int]]) -> list[IndexSymbol]:
    return [
        IndexSymbol(name=n, full_name=fn, kind=SymbolKind.METHOD, file_path="client.ts", line=ln, end_line=el)
        for n, fn, ln, el in pairs
    ]


def test_ts_client_calls_match_python_server_endpoints() -> None:
    """TypeScript client calls for /api/users match Python FastAPI server endpoints."""
    py_source = """\
from fastapi import FastAPI
app = FastAPI()

@app.get("/api/users")
async def list_users():
    pass

@app.post("/api/users")
async def create_user():
    pass
"""
    ts_source = """\
function fetchUsers() {
    return api.get('/api/users');
}

function createUser(data) {
    return api.post('/api/users', data);
}
"""
    py_tree = _py_parse(py_source)
    py_symbols = _py_symbols([
        ("list_users", "server.list_users", 5, 6),
        ("create_user", "server.create_user", 9, 10),
    ])
    py_result = PythonHttpExtractor().extract("server.py", py_tree, py_symbols)

    ts_tree = _ts_parse(ts_source)
    ts_symbols = _ts_symbols([
        ("fetchUsers", "client.fetchUsers", 1, 3),
        ("createUser", "client.createUser", 5, 7),
    ])
    ts_result = TypeScriptHttpExtractor().extract("client.ts", ts_tree, ts_symbols)

    assert len(py_result.endpoint_defs) == 2
    assert len(ts_result.client_calls) == 2

    matched = match_endpoints(py_result.endpoint_defs, ts_result.client_calls)

    # Both routes should be matched with both endpoint_def and client_calls populated
    matched_with_both = [m for m in matched if m.endpoint_def is not None and m.client_calls]
    assert len(matched_with_both) >= 2, f"Expected 2+ matched endpoints, got: {matched}"

    methods = {m.http_method for m in matched_with_both}
    assert "GET" in methods, f"GET /api/users not matched: {matched}"
    assert "POST" in methods, f"POST /api/users not matched: {matched}"


def test_ts_client_calls_match_python_parameterized_endpoint() -> None:
    """TypeScript template literal with ${userId} matches Python {user_id} parameter."""
    py_source = """\
from fastapi import FastAPI
app = FastAPI()

@app.get("/api/users/{user_id}")
async def get_user(user_id: int):
    pass
"""
    ts_source = """\
function getUser(userId) {
    return api.get(`/api/users/${userId}`);
}
"""
    py_tree = _py_parse(py_source)
    py_symbols = _py_symbols([("get_user", "server.get_user", 5, 6)])
    py_result = PythonHttpExtractor().extract("server.py", py_tree, py_symbols)

    ts_tree = _ts_parse(ts_source)
    ts_symbols = _ts_symbols([("getUser", "client.getUser", 1, 3)])
    ts_result = TypeScriptHttpExtractor().extract("client.ts", ts_tree, ts_symbols)

    assert len(py_result.endpoint_defs) == 1
    assert len(ts_result.client_calls) == 1

    # Both normalise path params: Python keeps {user_id}, TS produces {userId}
    # The matcher treats any {param} segment as wildcards that match each other
    matched = match_endpoints(py_result.endpoint_defs, ts_result.client_calls)
    matched_with_both = [m for m in matched if m.endpoint_def is not None and m.client_calls]
    assert len(matched_with_both) == 1, f"Expected parameterized route to match: {matched}"
    assert matched_with_both[0].http_method == "GET"


def test_cross_language_no_match_different_routes() -> None:
    """No match when server serves /api/users but client calls /api/items."""
    py_source = """\
from fastapi import FastAPI
app = FastAPI()

@app.get("/api/users")
async def list_users():
    pass
"""
    ts_source = """\
function fetchItems() {
    return api.get('/api/items');
}
"""
    py_tree = _py_parse(py_source)
    py_symbols = _py_symbols([("list_users", "server.list_users", 5, 6)])
    py_result = PythonHttpExtractor().extract("server.py", py_tree, py_symbols)

    ts_tree = _ts_parse(ts_source)
    ts_symbols = _ts_symbols([("fetchItems", "client.fetchItems", 1, 3)])
    ts_result = TypeScriptHttpExtractor().extract("client.ts", ts_tree, ts_symbols)

    matched = match_endpoints(py_result.endpoint_defs, ts_result.client_calls)

    # No MatchedEndpoint should have both endpoint_def and client_calls
    matched_with_both = [m for m in matched if m.endpoint_def is not None and m.client_calls]
    assert len(matched_with_both) == 0, f"Expected no cross-route match, got: {matched_with_both}"
