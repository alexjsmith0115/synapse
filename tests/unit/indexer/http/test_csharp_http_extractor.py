from __future__ import annotations

import tree_sitter_c_sharp
from tree_sitter import Language, Parser

from synapps.indexer.csharp.csharp_http_extractor import CSharpHttpExtractor
from synapps.lsp.interface import IndexSymbol, SymbolKind

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

from synapps.indexer.csharp.csharp_http_extractor import _find_enclosing_symbol


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


# ---------------------------------------------------------------------------
# Generic method extraction tests -- HTTP_CALLS regression
# ---------------------------------------------------------------------------


def test_httpclient_get_from_json_async() -> None:
    """GetFromJsonAsync<T> is a generic method; extractor must handle generic_name AST nodes."""
    source = '''\
public class UserService {
    private HttpClient _httpClient;
    public async Task<List<User>> GetUsers() {
        return await _httpClient.GetFromJsonAsync<List<User>>("/api/users");
    }
}
'''
    extractor = CSharpHttpExtractor()
    syms = _symbols_with_end([("GetUsers", "UserService.GetUsers", 3, 5)])
    result = extractor.extract("test.cs", _parse(source), syms)
    assert len(result.client_calls) == 1
    call = result.client_calls[0]
    assert call.http_method == "GET"
    assert call.route == "/api/users"
    assert call.caller_full_name == "UserService.GetUsers"


def test_httpclient_post_as_json_async() -> None:
    """PostAsJsonAsync<T> is a generic method."""
    source = '''\
public class UserService {
    private HttpClient _httpClient;
    public async Task CreateUser(User user) {
        await _httpClient.PostAsJsonAsync<User>("/api/users", user);
    }
}
'''
    extractor = CSharpHttpExtractor()
    syms = _symbols_with_end([("CreateUser", "UserService.CreateUser", 3, 5)])
    result = extractor.extract("test.cs", _parse(source), syms)
    assert len(result.client_calls) == 1
    assert result.client_calls[0].http_method == "POST"
    assert result.client_calls[0].route == "/api/users"


def test_httpclient_put_as_json_async() -> None:
    """PutAsJsonAsync<T> is a generic method."""
    source = '''\
public class UserService {
    private HttpClient _httpClient;
    public async Task UpdateUser(int id, User user) {
        await _httpClient.PutAsJsonAsync<User>($"/api/users/{id}", user);
    }
}
'''
    extractor = CSharpHttpExtractor()
    syms = _symbols_with_end([("UpdateUser", "UserService.UpdateUser", 3, 5)])
    result = extractor.extract("test.cs", _parse(source), syms)
    assert len(result.client_calls) == 1
    assert result.client_calls[0].http_method == "PUT"
    assert result.client_calls[0].route == "/api/users/{param}"


def test_httpclient_get_stream_async() -> None:
    """GetStreamAsync is non-generic but missing from verb map."""
    source = '''\
public class DataService {
    private HttpClient _httpClient;
    public async Task<Stream> DownloadData() {
        return await _httpClient.GetStreamAsync("/api/data/export");
    }
}
'''
    extractor = CSharpHttpExtractor()
    syms = _symbols_with_end([("DownloadData", "DataService.DownloadData", 3, 5)])
    result = extractor.extract("test.cs", _parse(source), syms)
    assert len(result.client_calls) == 1
    assert result.client_calls[0].http_method == "GET"
    assert result.client_calls[0].route == "/api/data/export"


# ---------------------------------------------------------------------------
# FastEndpoints detection tests
# ---------------------------------------------------------------------------


def test_fastendpoints_generic_base() -> None:
    """class Foo : Endpoint<Req, Res> with Configure() Post produces one endpoint."""
    source = '''\
public class TodoEndpoint : Endpoint<TodoRequest, TodoResponse> {
    public override void Configure() {
        Post("/api/todos");
        AllowAnonymous();
    }
    public override async Task HandleAsync(TodoRequest req, CancellationToken ct) { }
}
'''
    extractor = CSharpHttpExtractor()
    syms = _symbols([("HandleAsync", "TodoEndpoint.HandleAsync", 6)])
    result = extractor.extract("test.cs", _parse(source), syms)
    assert len(result.endpoint_defs) == 1
    ep = result.endpoint_defs[0]
    assert ep.route == "/api/todos"
    assert ep.http_method == "POST"
    assert ep.handler_full_name == "TodoEndpoint.HandleAsync"


def test_fastendpoints_plain_base() -> None:
    """class Foo : EndpointWithoutRequest with Configure() Get produces one endpoint."""
    source = '''\
public class HealthEndpoint : EndpointWithoutRequest {
    public override void Configure() {
        Get("/api/health");
    }
    public override async Task HandleAsync(CancellationToken ct) { }
}
'''
    extractor = CSharpHttpExtractor()
    syms = _symbols([("HandleAsync", "HealthEndpoint.HandleAsync", 5)])
    result = extractor.extract("test.cs", _parse(source), syms)
    assert len(result.endpoint_defs) == 1
    ep = result.endpoint_defs[0]
    assert ep.route == "/api/health"
    assert ep.http_method == "GET"


def test_fastendpoints_mapper_base() -> None:
    """class Foo : EndpointWithMapper<Req, Mapper> with Configure() Put produces one endpoint."""
    source = '''\
public class ItemEndpoint : EndpointWithMapper<ItemRequest, ItemMapper> {
    public override void Configure() {
        Put("/api/items");
    }
    public override async Task HandleAsync(ItemRequest req, CancellationToken ct) { }
}
'''
    extractor = CSharpHttpExtractor()
    syms = _symbols([("HandleAsync", "ItemEndpoint.HandleAsync", 5)])
    result = extractor.extract("test.cs", _parse(source), syms)
    assert len(result.endpoint_defs) == 1
    ep = result.endpoint_defs[0]
    assert ep.route == "/api/items"
    assert ep.http_method == "PUT"


def test_fastendpoints_handler_is_handle_async() -> None:
    """handler_full_name must be the HandleAsync full_name (with namespace), not the class."""
    source = '''\
namespace MyNs {
    public class TodoEndpoint : Endpoint<TodoRequest, TodoResponse> {
        public override void Configure() {
            Post("/api/todos");
        }
        public override async Task HandleAsync(TodoRequest req, CancellationToken ct) { }
    }
}
'''
    extractor = CSharpHttpExtractor()
    syms = _symbols([("HandleAsync", "MyNs.TodoEndpoint.HandleAsync", 6)])
    result = extractor.extract("test.cs", _parse(source), syms)
    assert len(result.endpoint_defs) == 1
    assert result.endpoint_defs[0].handler_full_name == "MyNs.TodoEndpoint.HandleAsync"


def test_fastendpoints_mutual_exclusion_route_attr() -> None:
    """Class with [Route] attribute AND Endpoint<T> base must produce exactly 1 endpoint (FastEndpoints wins)."""
    source = '''\
[Route("/api/swagger")]
public class TodoEndpoint : Endpoint<TodoRequest, TodoResponse> {
    public override void Configure() {
        Post("/api/todos");
    }
    public override async Task HandleAsync(TodoRequest req, CancellationToken ct) { }
}
'''
    extractor = CSharpHttpExtractor()
    syms = _symbols([("HandleAsync", "TodoEndpoint.HandleAsync", 6)])
    result = extractor.extract("test.cs", _parse(source), syms)
    # Exactly 1 endpoint — FastEndpoints path wins, no duplicate from controller path
    assert len(result.endpoint_defs) == 1
    # Route comes from Configure(), not from [Route]
    assert result.endpoint_defs[0].route == "/api/todos"


def test_non_fastendpoints_post_not_detected() -> None:
    """A plain class with a Post() method but no FastEndpoints base produces zero endpoints."""
    source = '''\
public class NotAnEndpoint {
    public void Post() { }
}
'''
    extractor = CSharpHttpExtractor()
    result = extractor.extract("test.cs", _parse(source), [])
    assert len(result.endpoint_defs) == 0


def test_fastendpoints_configure_delete() -> None:
    """Configure() with Delete produces verb=DELETE."""
    source = '''\
public class ItemDeleteEndpoint : Endpoint<DeleteRequest, DeleteResponse> {
    public override void Configure() {
        Delete("/api/items/{id}");
    }
    public override async Task HandleAsync(DeleteRequest req, CancellationToken ct) { }
}
'''
    extractor = CSharpHttpExtractor()
    syms = _symbols([("HandleAsync", "ItemDeleteEndpoint.HandleAsync", 5)])
    result = extractor.extract("test.cs", _parse(source), syms)
    assert len(result.endpoint_defs) == 1
    assert result.endpoint_defs[0].route == "/api/items/{id}"
    assert result.endpoint_defs[0].http_method == "DELETE"


def test_fastendpoints_configure_patch() -> None:
    """Configure() with Patch produces verb=PATCH."""
    source = '''\
public class ItemPatchEndpoint : Endpoint<PatchRequest, PatchResponse> {
    public override void Configure() {
        Patch("/api/items/{id}");
    }
    public override async Task HandleAsync(PatchRequest req, CancellationToken ct) { }
}
'''
    extractor = CSharpHttpExtractor()
    syms = _symbols([("HandleAsync", "ItemPatchEndpoint.HandleAsync", 5)])
    result = extractor.extract("test.cs", _parse(source), syms)
    assert len(result.endpoint_defs) == 1
    assert result.endpoint_defs[0].route == "/api/items/{id}"
    assert result.endpoint_defs[0].http_method == "PATCH"


def test_fastendpoints_handle_async_missing() -> None:
    """FastEndpoints class with no HandleAsync in symbol_map produces 0 endpoints (graceful skip)."""
    source = '''\
public class TodoEndpoint : Endpoint<TodoRequest, TodoResponse> {
    public override void Configure() {
        Post("/api/todos");
    }
    public override async Task HandleAsync(TodoRequest req, CancellationToken ct) { }
}
'''
    extractor = CSharpHttpExtractor()
    # No symbols provided — HandleAsync cannot be resolved
    result = extractor.extract("test.cs", _parse(source), [])
    assert len(result.endpoint_defs) == 0


# ---------------------------------------------------------------------------
# FastEndpoints Verbs() + Routes() multi-declaration tests (Plan 02 / FE-05)
# ---------------------------------------------------------------------------


def test_fastendpoints_verbs_routes_cross_product() -> None:
    """Verbs(Http.POST, Http.PUT) + Routes('/a', '/b') produces 4 endpoints (cross-product per D-04)."""
    source = '''\
public class MultiEndpoint : Endpoint<Req, Res> {
    public override void Configure() {
        Verbs(Http.POST, Http.PUT);
        Routes("/a", "/b");
    }
    public override async Task HandleAsync(Req req, CancellationToken ct) { }
}
'''
    extractor = CSharpHttpExtractor()
    syms = _symbols([("HandleAsync", "MultiEndpoint.HandleAsync", 7)])
    result = extractor.extract("test.cs", _parse(source), syms)
    assert len(result.endpoint_defs) == 4
    pairs = {(ep.http_method, ep.route) for ep in result.endpoint_defs}
    assert pairs == {("POST", "/a"), ("POST", "/b"), ("PUT", "/a"), ("PUT", "/b")}
    assert all(ep.handler_full_name == "MultiEndpoint.HandleAsync" for ep in result.endpoint_defs)


def test_fastendpoints_verbs_string_style() -> None:
    """Verbs('GET', 'POST') string-style arguments produce correct verbs."""
    source = '''\
public class StringVerbEndpoint : Endpoint<Req, Res> {
    public override void Configure() {
        Verbs("GET", "POST");
        Routes("/api/multi");
    }
    public override async Task HandleAsync(Req req, CancellationToken ct) { }
}
'''
    extractor = CSharpHttpExtractor()
    syms = _symbols([("HandleAsync", "StringVerbEndpoint.HandleAsync", 7)])
    result = extractor.extract("test.cs", _parse(source), syms)
    assert len(result.endpoint_defs) == 2
    pairs = {(ep.http_method, ep.route) for ep in result.endpoint_defs}
    assert pairs == {("GET", "/api/multi"), ("POST", "/api/multi")}


def test_fastendpoints_verbs_enum_single() -> None:
    """Verbs(Http.DELETE) + Routes('/api/items') produces exactly 1 endpoint."""
    source = '''\
public class SingleVerbEndpoint : EndpointWithoutRequest {
    public override void Configure() {
        Verbs(Http.DELETE);
        Routes("/api/items");
    }
    public override async Task HandleAsync(CancellationToken ct) { }
}
'''
    extractor = CSharpHttpExtractor()
    syms = _symbols([("HandleAsync", "SingleVerbEndpoint.HandleAsync", 7)])
    result = extractor.extract("test.cs", _parse(source), syms)
    assert len(result.endpoint_defs) == 1
    assert result.endpoint_defs[0].http_method == "DELETE"
    assert result.endpoint_defs[0].route == "/api/items"


# ---------------------------------------------------------------------------
# IEndpointGroup detection tests (Phase 24 / EG-01..EG-04)
# ---------------------------------------------------------------------------


def test_iendpointgroup_basic_mapget() -> None:
    """Class implementing IEndpointGroup with MapGet produces 1 endpoint."""
    source = '''
public class TodoItems : IEndpointGroup {
    public void Map(IEndpointRouteBuilder app) {
        app.MapGet("/todos", GetAllTodos);
    }
    public static IResult GetAllTodos() { return Results.Ok(); }
}
'''
    extractor = CSharpHttpExtractor()
    syms = _symbols([
        ("Map", "TodoItems.Map", 3),
        ("GetAllTodos", "TodoItems.GetAllTodos", 6),
    ])
    result = extractor.extract("test.cs", _parse(source), syms)
    assert len(result.endpoint_defs) == 1
    ep = result.endpoint_defs[0]
    assert ep.route == "/todos"
    assert ep.http_method == "GET"
    assert ep.handler_full_name == "TodoItems.GetAllTodos"


def test_iendpointgroup_multiple_verbs() -> None:
    """IEndpointGroup Map() with MapGet + MapPost + MapDelete produces 3 endpoints."""
    source = '''
public class TodoItems : IEndpointGroup {
    public void Map(IEndpointRouteBuilder app) {
        app.MapGet("/todos", GetAll);
        app.MapPost("/todos", Create);
        app.MapDelete("/todos/{id}", Delete);
    }
    public static IResult GetAll() { return Results.Ok(); }
    public static IResult Create() { return Results.Ok(); }
    public static IResult Delete() { return Results.Ok(); }
}
'''
    extractor = CSharpHttpExtractor()
    syms = _symbols([
        ("Map", "TodoItems.Map", 3),
        ("GetAll", "TodoItems.GetAll", 8),
        ("Create", "TodoItems.Create", 9),
        ("Delete", "TodoItems.Delete", 10),
    ])
    result = extractor.extract("test.cs", _parse(source), syms)
    assert len(result.endpoint_defs) == 3
    pairs = {(ep.http_method, ep.route) for ep in result.endpoint_defs}
    assert ("GET", "/todos") in pairs
    assert ("POST", "/todos") in pairs
    assert ("DELETE", "/todos/{id}") in pairs


def test_iendpointgroup_endpointgroupbase() -> None:
    """Class inheriting EndpointGroupBase (not interface) is also detected."""
    source = '''
public class HealthGroup : EndpointGroupBase {
    public override void Map(IEndpointRouteBuilder app) {
        app.MapGet("/health", GetHealth);
    }
    public static IResult GetHealth() { return Results.Ok(); }
}
'''
    extractor = CSharpHttpExtractor()
    syms = _symbols([
        ("Map", "HealthGroup.Map", 3),
        ("GetHealth", "HealthGroup.GetHealth", 6),
    ])
    result = extractor.extract("test.cs", _parse(source), syms)
    assert len(result.endpoint_defs) == 1
    ep = result.endpoint_defs[0]
    assert ep.route == "/health"
    assert ep.http_method == "GET"
    assert ep.handler_full_name == "HealthGroup.GetHealth"


def test_iendpointgroup_handler_first_ordering() -> None:
    """app.MapPost(CreateItem, '{id}') — handler-first — produces correct route and verb (EG-04)."""
    source = '''
public class Items : IEndpointGroup {
    public void Map(IEndpointRouteBuilder app) {
        app.MapPost(CreateItem, "{id}");
    }
    public static IResult CreateItem() { return Results.Ok(); }
}
'''
    extractor = CSharpHttpExtractor()
    syms = _symbols([
        ("Map", "Items.Map", 3),
        ("CreateItem", "Items.CreateItem", 6),
    ])
    result = extractor.extract("test.cs", _parse(source), syms)
    assert len(result.endpoint_defs) == 1
    ep = result.endpoint_defs[0]
    assert ep.route == "/{id}"
    assert ep.http_method == "POST"
    assert ep.handler_full_name == "Items.CreateItem"


def test_iendpointgroup_route_first_ordering() -> None:
    """app.MapGet('/items', GetItems) — route-first — produces correct route and verb (EG-04)."""
    source = '''
public class Items : IEndpointGroup {
    public void Map(IEndpointRouteBuilder app) {
        app.MapGet("/items", GetItems);
    }
    public static IResult GetItems() { return Results.Ok(); }
}
'''
    extractor = CSharpHttpExtractor()
    syms = _symbols([
        ("Map", "Items.Map", 3),
        ("GetItems", "Items.GetItems", 6),
    ])
    result = extractor.extract("test.cs", _parse(source), syms)
    assert len(result.endpoint_defs) == 1
    ep = result.endpoint_defs[0]
    assert ep.route == "/items"
    assert ep.http_method == "GET"
    assert ep.handler_full_name == "Items.GetItems"


def test_iendpointgroup_lambda_handler() -> None:
    """Lambda handler app.MapGet('/health', () => ...) resolves to Map method's full_name."""
    source = '''
public class HealthGroup : IEndpointGroup {
    public void Map(IEndpointRouteBuilder app) {
        app.MapGet("/health", () => Results.Ok());
    }
}
'''
    extractor = CSharpHttpExtractor()
    syms = _symbols([("Map", "HealthGroup.Map", 3)])
    result = extractor.extract("test.cs", _parse(source), syms)
    assert len(result.endpoint_defs) == 1
    ep = result.endpoint_defs[0]
    assert ep.route == "/health"
    assert ep.http_method == "GET"
    assert ep.handler_full_name == "HealthGroup.Map"


def test_iendpointgroup_mutual_exclusion() -> None:
    """IEndpointGroup class with [Route] attribute does NOT produce controller-style endpoints."""
    source = '''
[Route("/api/todos")]
public class TodoItems : IEndpointGroup {
    public void Map(IEndpointRouteBuilder app) {
        app.MapGet("/todos", GetAll);
    }
    public static IResult GetAll() { return Results.Ok(); }
}
'''
    extractor = CSharpHttpExtractor()
    syms = _symbols([
        ("Map", "TodoItems.Map", 4),
        ("GetAll", "TodoItems.GetAll", 7),
    ])
    result = extractor.extract("test.cs", _parse(source), syms)
    # Only IEndpointGroup endpoints — no controller-style duplicates
    assert len(result.endpoint_defs) == 1
    ep = result.endpoint_defs[0]
    assert ep.route == "/todos"
    assert ep.handler_full_name == "TodoItems.GetAll"


def test_iendpointgroup_negative_plain_class() -> None:
    """A plain class with a method named MapGet() is not an IEndpointGroup and produces zero endpoints."""
    source = '''
public class NotAnEndpointGroup {
    public void MapGet(string route, object handler) { }
}
'''
    extractor = CSharpHttpExtractor()
    result = extractor.extract("test.cs", _parse(source), [])
    assert len(result.endpoint_defs) == 0
