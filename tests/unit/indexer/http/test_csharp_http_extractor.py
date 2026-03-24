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
