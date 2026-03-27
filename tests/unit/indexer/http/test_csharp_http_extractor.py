from __future__ import annotations

import tree_sitter_c_sharp
from tree_sitter import Language, Parser

from synapse.indexer.csharp.csharp_http_extractor import CSharpHttpExtractor
from synapse.lsp.interface import IndexSymbol, SymbolKind

_lang = Language(tree_sitter_c_sharp.language())
_parser = Parser(_lang)


def _parse(source: str):
    return _parser.parse(bytes(source, "utf-8"))


def _symbols(pairs: list[tuple[str, str, int]]) -> list[IndexSymbol]:
    """Build IndexSymbol list from (name, full_name, line) triples."""
    return [
        IndexSymbol(name=n, full_name=fn, kind=SymbolKind.METHOD, file_path="test.cs", line=ln)
        for n, fn, ln in pairs
    ]


def _symbols_with_end(pairs: list[tuple[str, str, int, int]]) -> list[IndexSymbol]:
    """Build IndexSymbol list from (name, full_name, start_line, end_line) tuples."""
    return [
        IndexSymbol(name=n, full_name=fn, kind=SymbolKind.METHOD, file_path="test.cs", line=ln, end_line=end)
        for n, fn, ln, end in pairs
    ]


def test_basic_controller_endpoint() -> None:
    source = '''
[ApiController]
[Route("api/items")]
public class ItemsController : ControllerBase {
    [HttpGet]
    public IActionResult GetAll() { }
}
'''
    extractor = CSharpHttpExtractor()
    result = extractor.extract("test.cs", _parse(source), _symbols([("GetAll", "ItemsController.GetAll", 5)]))
    assert len(result.endpoint_defs) == 1
    ep = result.endpoint_defs[0]
    assert ep.route == "/api/items"
    assert ep.http_method == "GET"
    assert ep.handler_full_name == "ItemsController.GetAll"


def test_method_route_suffix() -> None:
    source = '''
[ApiController]
[Route("api/items")]
public class ItemsController : ControllerBase {
    [HttpGet("{id:guid}")]
    public IActionResult GetById(Guid id) { }
}
'''
    extractor = CSharpHttpExtractor()
    result = extractor.extract("test.cs", _parse(source), _symbols([("GetById", "ItemsController.GetById", 5)]))
    assert len(result.endpoint_defs) == 1
    assert result.endpoint_defs[0].route == "/api/items/{id}"
    assert result.endpoint_defs[0].http_method == "GET"


def test_post_with_sub_route() -> None:
    source = '''
[ApiController]
[Route("api/meetings")]
public class MeetingsController : ControllerBase {
    [HttpPost("{id:guid}/complete")]
    public IActionResult Complete(Guid id) { }
}
'''
    extractor = CSharpHttpExtractor()
    result = extractor.extract("test.cs", _parse(source), _symbols([("Complete", "MeetingsController.Complete", 5)]))
    assert result.endpoint_defs[0].route == "/api/meetings/{id}/complete"
    assert result.endpoint_defs[0].http_method == "POST"


def test_tilde_overrides_class_route() -> None:
    source = '''
[ApiController]
[Route("api/users")]
public class UsersController : ControllerBase {
    [HttpGet("~/api/auth/me")]
    public IActionResult GetAuthMe() { }
}
'''
    extractor = CSharpHttpExtractor()
    result = extractor.extract("test.cs", _parse(source), _symbols([("GetAuthMe", "UsersController.GetAuthMe", 5)]))
    assert result.endpoint_defs[0].route == "/api/auth/me"


def test_multiple_verbs_on_class() -> None:
    source = '''
[ApiController]
[Route("api/items")]
public class ItemsController : ControllerBase {
    [HttpGet]
    public IActionResult GetAll() { }

    [HttpPost]
    public IActionResult Create() { }

    [HttpDelete("{id:guid}")]
    public IActionResult Delete(Guid id) { }
}
'''
    extractor = CSharpHttpExtractor()
    result = extractor.extract(
        "test.cs",
        _parse(source),
        _symbols([
            ("GetAll", "ItemsController.GetAll", 5),
            ("Create", "ItemsController.Create", 8),
            ("Delete", "ItemsController.Delete", 11),
        ]),
    )
    assert len(result.endpoint_defs) == 3
    routes = {(ep.route, ep.http_method) for ep in result.endpoint_defs}
    assert ("/api/items", "GET") in routes
    assert ("/api/items", "POST") in routes
    assert ("/api/items/{id}", "DELETE") in routes


def test_non_controller_class_skipped() -> None:
    source = '''
public class MyService {
    [HttpGet]
    public void DoSomething() { }
}
'''
    extractor = CSharpHttpExtractor()
    result = extractor.extract("test.cs", _parse(source), _symbols([("DoSomething", "MyService.DoSomething", 3)]))
    assert len(result.endpoint_defs) == 0


def test_no_client_calls_returned() -> None:
    source = '''
[ApiController]
[Route("api/items")]
public class ItemsController : ControllerBase {
    [HttpGet]
    public IActionResult GetAll() { }
}
'''
    extractor = CSharpHttpExtractor()
    result = extractor.extract("test.cs", _parse(source), _symbols([("GetAll", "ItemsController.GetAll", 5)]))
    assert result.client_calls == []


def test_empty_source() -> None:
    extractor = CSharpHttpExtractor()
    result = extractor.extract("test.cs", _parse(""), [])
    assert result.endpoint_defs == []
    assert result.client_calls == []


def test_apicontroller_on_base_class() -> None:
    """Controllers inheriting from a base with [ApiController] should still be detected."""
    source = '''
[Route("api/meetings")]
public class MeetingsController : BaseApiController {
    [HttpPost]
    public IActionResult Create() { }

    [HttpGet("{id:guid}")]
    public IActionResult GetById(Guid id) { }
}
'''
    extractor = CSharpHttpExtractor()
    result = extractor.extract(
        "test.cs",
        _parse(source),
        _symbols([
            ("Create", "MeetingsController.Create", 4),
            ("GetById", "MeetingsController.GetById", 7),
        ]),
    )
    assert len(result.endpoint_defs) == 2
    routes = {(ep.route, ep.http_method) for ep in result.endpoint_defs}
    assert ("/api/meetings", "POST") in routes
    assert ("/api/meetings/{id}", "GET") in routes


def test_controller_placeholder_in_route() -> None:
    source = '''
[ApiController]
[Route("api/[controller]")]
public class TasksController : ControllerBase {
    [HttpGet]
    public IActionResult GetAll() { }
}
'''
    extractor = CSharpHttpExtractor()
    result = extractor.extract("test.cs", _parse(source), _symbols([("GetAll", "TasksController.GetAll", 5)]))
    assert result.endpoint_defs[0].route == "/api/tasks"


# ---------------------------------------------------------------------------
# Client-side extraction tests (HTTP_CALLS)
# ---------------------------------------------------------------------------

def test_httpclient_get_async() -> None:
    source = '''\
public class UserService {
    private HttpClient _httpClient;
    public async Task<string> FetchUsers() {
        var response = await _httpClient.GetAsync("/api/users");
        return response;
    }
}
'''
    extractor = CSharpHttpExtractor()
    syms = _symbols_with_end([("FetchUsers", "UserService.FetchUsers", 3, 6)])
    result = extractor.extract("test.cs", _parse(source), syms)
    assert len(result.client_calls) == 1
    call = result.client_calls[0]
    assert call.http_method == "GET"
    assert call.route == "/api/users"
    assert call.caller_full_name == "UserService.FetchUsers"


def test_httpclient_post_async() -> None:
    source = '''\
public class UserService {
    private HttpClient _httpClient;
    public async Task Create() {
        var response = await _httpClient.PostAsync("/api/users", content);
    }
}
'''
    extractor = CSharpHttpExtractor()
    syms = _symbols_with_end([("Create", "UserService.Create", 3, 5)])
    result = extractor.extract("test.cs", _parse(source), syms)
    assert len(result.client_calls) == 1
    assert result.client_calls[0].http_method == "POST"
    assert result.client_calls[0].route == "/api/users"


def test_httpclient_put_async() -> None:
    source = '''\
public class UserService {
    private HttpClient _httpClient;
    public async Task Update(int id) {
        await _httpClient.PutAsync("/api/users/1", content);
    }
}
'''
    extractor = CSharpHttpExtractor()
    syms = _symbols_with_end([("Update", "UserService.Update", 3, 5)])
    result = extractor.extract("test.cs", _parse(source), syms)
    assert len(result.client_calls) == 1
    assert result.client_calls[0].http_method == "PUT"
    assert result.client_calls[0].route == "/api/users/1"


def test_httpclient_delete_async() -> None:
    source = '''\
public class UserService {
    private HttpClient _httpClient;
    public async Task Delete(int id) {
        await _httpClient.DeleteAsync("/api/users/1");
    }
}
'''
    extractor = CSharpHttpExtractor()
    syms = _symbols_with_end([("Delete", "UserService.Delete", 3, 5)])
    result = extractor.extract("test.cs", _parse(source), syms)
    assert len(result.client_calls) == 1
    assert result.client_calls[0].http_method == "DELETE"
    assert result.client_calls[0].route == "/api/users/1"


def test_httpclient_patch_async() -> None:
    source = '''\
public class UserService {
    private HttpClient _httpClient;
    public async Task Patch() {
        await _httpClient.PatchAsync("/api/users/1", content);
    }
}
'''
    extractor = CSharpHttpExtractor()
    syms = _symbols_with_end([("Patch", "UserService.Patch", 3, 5)])
    result = extractor.extract("test.cs", _parse(source), syms)
    assert len(result.client_calls) == 1
    assert result.client_calls[0].http_method == "PATCH"


def test_httpclient_get_string_async() -> None:
    source = '''\
public class DataService {
    private HttpClient _httpClient;
    public async Task<string> GetData() {
        return await _httpClient.GetStringAsync("/api/data");
    }
}
'''
    extractor = CSharpHttpExtractor()
    syms = _symbols_with_end([("GetData", "DataService.GetData", 3, 5)])
    result = extractor.extract("test.cs", _parse(source), syms)
    assert len(result.client_calls) == 1
    assert result.client_calls[0].http_method == "GET"
    assert result.client_calls[0].route == "/api/data"


def test_restsharp_request_get() -> None:
    source = '''\
public class ApiClient {
    public void FetchUsers() {
        var request = new RestRequest("/api/users", Method.Get);
    }
}
'''
    extractor = CSharpHttpExtractor()
    syms = _symbols_with_end([("FetchUsers", "ApiClient.FetchUsers", 2, 4)])
    result = extractor.extract("test.cs", _parse(source), syms)
    assert len(result.client_calls) == 1
    call = result.client_calls[0]
    assert call.http_method == "GET"
    assert call.route == "/api/users"
    assert call.caller_full_name == "ApiClient.FetchUsers"


def test_restsharp_request_post() -> None:
    source = '''\
public class ApiClient {
    public void CreateUser() {
        var request = new RestRequest("/api/users", Method.Post);
    }
}
'''
    extractor = CSharpHttpExtractor()
    syms = _symbols_with_end([("CreateUser", "ApiClient.CreateUser", 2, 4)])
    result = extractor.extract("test.cs", _parse(source), syms)
    assert len(result.client_calls) == 1
    assert result.client_calls[0].http_method == "POST"
    assert result.client_calls[0].route == "/api/users"


def test_interpolated_string_url() -> None:
    source = '''\
public class ItemService {
    private HttpClient _httpClient;
    public async Task FetchItem(int id) {
        await _httpClient.GetAsync($"/api/items/{id}");
    }
}
'''
    extractor = CSharpHttpExtractor()
    syms = _symbols_with_end([("FetchItem", "ItemService.FetchItem", 3, 5)])
    result = extractor.extract("test.cs", _parse(source), syms)
    assert len(result.client_calls) == 1
    call = result.client_calls[0]
    assert call.http_method == "GET"
    assert call.route == "/api/items/{param}"


def test_client_and_server_in_same_file() -> None:
    """File with both ASP.NET controller and HttpClient calls produces both endpoint_defs and client_calls."""
    source = '''\
[ApiController]
[Route("api/proxy")]
public class ProxyController : ControllerBase {
    private HttpClient _httpClient;

    [HttpGet]
    public async Task<IActionResult> ForwardGet() {
        var response = await _httpClient.GetAsync("/api/upstream");
        return Ok(response);
    }
}
'''
    extractor = CSharpHttpExtractor()
    syms = _symbols_with_end([("ForwardGet", "ProxyController.ForwardGet", 7, 10)])
    result = extractor.extract("test.cs", _parse(source), syms)
    # Server-side endpoint
    assert len(result.endpoint_defs) == 1
    assert result.endpoint_defs[0].route == "/api/proxy"
    assert result.endpoint_defs[0].http_method == "GET"
    # Client-side call
    assert len(result.client_calls) == 1
    assert result.client_calls[0].route == "/api/upstream"
    assert result.client_calls[0].http_method == "GET"


def test_existing_server_extraction_unchanged() -> None:
    """Regression guard: existing [HttpGet] extraction still works after client-side changes."""
    source = '''
[ApiController]
[Route("api/items")]
public class ItemsController : ControllerBase {
    [HttpGet]
    public IActionResult GetAll() { }
}
'''
    extractor = CSharpHttpExtractor()
    result = extractor.extract("test.cs", _parse(source), _symbols([("GetAll", "ItemsController.GetAll", 5)]))
    assert len(result.endpoint_defs) == 1
    ep = result.endpoint_defs[0]
    assert ep.route == "/api/items"
    assert ep.http_method == "GET"
    assert ep.handler_full_name == "ItemsController.GetAll"
    # No spurious client calls from server-side extraction
    assert result.client_calls == []


def test_url_without_slash_skipped() -> None:
    """HttpClient calls with URLs lacking '/' are ignored (false positive filter)."""
    source = '''\
public class SomeService {
    private HttpClient _httpClient;
    public async Task DoThing() {
        await _httpClient.GetAsync("no-slash-here");
    }
}
'''
    extractor = CSharpHttpExtractor()
    syms = _symbols_with_end([("DoThing", "SomeService.DoThing", 3, 5)])
    result = extractor.extract("test.cs", _parse(source), syms)
    assert result.client_calls == []


# ---------------------------------------------------------------------------
# _find_enclosing_symbol narrowest-range tests -- PROD-04 regression
# ---------------------------------------------------------------------------

from synapse.indexer.csharp.csharp_http_extractor import _find_enclosing_symbol


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
