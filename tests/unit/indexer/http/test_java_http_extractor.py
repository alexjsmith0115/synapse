from __future__ import annotations

import tree_sitter_java
from tree_sitter import Language, Parser

from synapse.lsp.interface import IndexSymbol, SymbolKind

_lang = Language(tree_sitter_java.language())
_parser = Parser(_lang)


def _parse(source: str):
    return _parser.parse(bytes(source, "utf-8"))


def _symbols(pairs: list[tuple[str, str, int, int]]) -> list[IndexSymbol]:
    """Build IndexSymbol list from (name, full_name, line, end_line) tuples."""
    return [
        IndexSymbol(name=n, full_name=fn, kind=SymbolKind.METHOD, file_path="test.java", line=ln, end_line=el)
        for n, fn, ln, el in pairs
    ]


# ---------------------------------------------------------------------------
# Spring server-side endpoint tests
# ---------------------------------------------------------------------------

def test_get_mapping_basic() -> None:
    source = """
@RestController
public class ItemController {
    @GetMapping("/items")
    public List<Item> getAll() { return null; }
}
"""
    from synapse.indexer.java.java_http_extractor import JavaHttpExtractor
    extractor = JavaHttpExtractor()
    result = extractor.extract("test.java", _parse(source), _symbols([("getAll", "ItemController.getAll", 4, 5)]))
    assert len(result.endpoint_defs) == 1
    ep = result.endpoint_defs[0]
    assert ep.route == "/items"
    assert ep.http_method == "GET"
    assert ep.handler_full_name == "ItemController.getAll"


def test_post_mapping() -> None:
    source = """
@RestController
public class ItemController {
    @PostMapping("/items")
    public Item create(Item item) { return null; }
}
"""
    from synapse.indexer.java.java_http_extractor import JavaHttpExtractor
    extractor = JavaHttpExtractor()
    result = extractor.extract("test.java", _parse(source), _symbols([("create", "ItemController.create", 4, 5)]))
    assert len(result.endpoint_defs) == 1
    assert result.endpoint_defs[0].http_method == "POST"
    assert result.endpoint_defs[0].route == "/items"


def test_put_mapping() -> None:
    source = """
@RestController
public class ItemController {
    @PutMapping("/items/{id}")
    public Item update(Long id, Item item) { return null; }
}
"""
    from synapse.indexer.java.java_http_extractor import JavaHttpExtractor
    extractor = JavaHttpExtractor()
    result = extractor.extract("test.java", _parse(source), _symbols([("update", "ItemController.update", 4, 5)]))
    assert len(result.endpoint_defs) == 1
    assert result.endpoint_defs[0].http_method == "PUT"
    assert result.endpoint_defs[0].route == "/items/{id}"


def test_delete_mapping() -> None:
    source = """
@RestController
public class ItemController {
    @DeleteMapping("/items/{id}")
    public void delete(Long id) {}
}
"""
    from synapse.indexer.java.java_http_extractor import JavaHttpExtractor
    extractor = JavaHttpExtractor()
    result = extractor.extract("test.java", _parse(source), _symbols([("delete", "ItemController.delete", 4, 5)]))
    assert len(result.endpoint_defs) == 1
    assert result.endpoint_defs[0].http_method == "DELETE"
    assert result.endpoint_defs[0].route == "/items/{id}"


def test_patch_mapping() -> None:
    source = """
@RestController
public class ItemController {
    @PatchMapping("/items/{id}")
    public Item patch(Long id, Item item) { return null; }
}
"""
    from synapse.indexer.java.java_http_extractor import JavaHttpExtractor
    extractor = JavaHttpExtractor()
    result = extractor.extract("test.java", _parse(source), _symbols([("patch", "ItemController.patch", 4, 5)]))
    assert len(result.endpoint_defs) == 1
    assert result.endpoint_defs[0].http_method == "PATCH"
    assert result.endpoint_defs[0].route == "/items/{id}"


def test_class_level_request_mapping_prefix_combined() -> None:
    """Class-level @RequestMapping prefix combined with method-level @GetMapping."""
    source = """
@RestController
@RequestMapping("/api")
public class ItemController {
    @GetMapping("/{id}")
    public Item getById(Long id) { return null; }
}
"""
    from synapse.indexer.java.java_http_extractor import JavaHttpExtractor
    extractor = JavaHttpExtractor()
    result = extractor.extract("test.java", _parse(source), _symbols([("getById", "ItemController.getById", 5, 6)]))
    assert len(result.endpoint_defs) == 1
    assert result.endpoint_defs[0].route == "/api/{id}"
    assert result.endpoint_defs[0].http_method == "GET"


def test_request_mapping_with_method_post() -> None:
    """@RequestMapping(method = RequestMethod.POST, path = '/items') -> POST."""
    source = """
@RestController
public class ItemController {
    @RequestMapping(method = RequestMethod.POST, path = "/items")
    public Item create(Item item) { return null; }
}
"""
    from synapse.indexer.java.java_http_extractor import JavaHttpExtractor
    extractor = JavaHttpExtractor()
    result = extractor.extract("test.java", _parse(source), _symbols([("create", "ItemController.create", 4, 5)]))
    assert len(result.endpoint_defs) == 1
    assert result.endpoint_defs[0].http_method == "POST"
    assert result.endpoint_defs[0].route == "/items"


def test_request_mapping_with_value_arg() -> None:
    """@RequestMapping(value = '/items') -> defaults to GET."""
    source = """
@RestController
public class ItemController {
    @RequestMapping(value = "/items")
    public List<Item> getAll() { return null; }
}
"""
    from synapse.indexer.java.java_http_extractor import JavaHttpExtractor
    extractor = JavaHttpExtractor()
    result = extractor.extract("test.java", _parse(source), _symbols([("getAll", "ItemController.getAll", 4, 5)]))
    assert len(result.endpoint_defs) == 1
    assert result.endpoint_defs[0].route == "/items"
    assert result.endpoint_defs[0].http_method == "GET"


def test_controller_annotation_also_detected() -> None:
    """@Controller (not @RestController) with @RequestMapping is also detected."""
    source = """
@Controller
@RequestMapping("/views")
public class ViewController {
    @GetMapping("/home")
    public String home() { return "home"; }
}
"""
    from synapse.indexer.java.java_http_extractor import JavaHttpExtractor
    extractor = JavaHttpExtractor()
    result = extractor.extract("test.java", _parse(source), _symbols([("home", "ViewController.home", 5, 6)]))
    assert len(result.endpoint_defs) == 1
    assert result.endpoint_defs[0].route == "/views/home"


def test_non_controller_class_skipped() -> None:
    """A class without @RestController or @Controller annotation is skipped."""
    source = """
public class ItemService {
    @GetMapping("/items")
    public List<Item> getAll() { return null; }
}
"""
    from synapse.indexer.java.java_http_extractor import JavaHttpExtractor
    extractor = JavaHttpExtractor()
    result = extractor.extract("test.java", _parse(source), _symbols([("getAll", "ItemService.getAll", 3, 4)]))
    assert len(result.endpoint_defs) == 0


# ---------------------------------------------------------------------------
# RestTemplate client-side tests
# ---------------------------------------------------------------------------

def test_rest_template_get_for_object() -> None:
    source = """
public class UserClient {
    public User getUser() {
        return restTemplate.getForObject("/api/users", User.class);
    }
}
"""
    from synapse.indexer.java.java_http_extractor import JavaHttpExtractor
    extractor = JavaHttpExtractor()
    result = extractor.extract("test.java", _parse(source), _symbols([("getUser", "UserClient.getUser", 3, 5)]))
    assert len(result.client_calls) == 1
    call = result.client_calls[0]
    assert call.route == "/api/users"
    assert call.http_method == "GET"
    assert call.caller_full_name == "UserClient.getUser"


def test_rest_template_post_for_object() -> None:
    source = """
public class UserClient {
    public User createUser(User user) {
        return restTemplate.postForObject("/api/users", user, User.class);
    }
}
"""
    from synapse.indexer.java.java_http_extractor import JavaHttpExtractor
    extractor = JavaHttpExtractor()
    result = extractor.extract("test.java", _parse(source), _symbols([("createUser", "UserClient.createUser", 3, 5)]))
    assert len(result.client_calls) == 1
    assert result.client_calls[0].http_method == "POST"
    assert result.client_calls[0].route == "/api/users"


def test_rest_template_put() -> None:
    source = """
public class UserClient {
    public void updateUser(Long id, User user) {
        restTemplate.put("/api/users/{id}", user);
    }
}
"""
    from synapse.indexer.java.java_http_extractor import JavaHttpExtractor
    extractor = JavaHttpExtractor()
    result = extractor.extract("test.java", _parse(source), _symbols([("updateUser", "UserClient.updateUser", 3, 5)]))
    assert len(result.client_calls) == 1
    assert result.client_calls[0].http_method == "PUT"
    assert result.client_calls[0].route == "/api/users/{id}"


def test_rest_template_delete() -> None:
    source = """
public class UserClient {
    public void deleteUser(Long id) {
        restTemplate.delete("/api/users/{id}");
    }
}
"""
    from synapse.indexer.java.java_http_extractor import JavaHttpExtractor
    extractor = JavaHttpExtractor()
    result = extractor.extract("test.java", _parse(source), _symbols([("deleteUser", "UserClient.deleteUser", 3, 5)]))
    assert len(result.client_calls) == 1
    assert result.client_calls[0].http_method == "DELETE"
    assert result.client_calls[0].route == "/api/users/{id}"


# ---------------------------------------------------------------------------
# WebClient client-side tests
# ---------------------------------------------------------------------------

def test_webclient_get() -> None:
    source = """
public class UserClient {
    public Mono<User> getUser() {
        return webClient.get().uri("/api/users").retrieve().bodyToMono(User.class);
    }
}
"""
    from synapse.indexer.java.java_http_extractor import JavaHttpExtractor
    extractor = JavaHttpExtractor()
    result = extractor.extract("test.java", _parse(source), _symbols([("getUser", "UserClient.getUser", 3, 5)]))
    assert len(result.client_calls) == 1
    call = result.client_calls[0]
    assert call.route == "/api/users"
    assert call.http_method == "GET"


def test_webclient_post() -> None:
    source = """
public class UserClient {
    public Mono<User> createUser(User user) {
        return webClient.post().uri("/api/users").bodyValue(user).retrieve().bodyToMono(User.class);
    }
}
"""
    from synapse.indexer.java.java_http_extractor import JavaHttpExtractor
    extractor = JavaHttpExtractor()
    result = extractor.extract("test.java", _parse(source), _symbols([("createUser", "UserClient.createUser", 3, 5)]))
    assert len(result.client_calls) == 1
    assert result.client_calls[0].http_method == "POST"
    assert result.client_calls[0].route == "/api/users"


# ---------------------------------------------------------------------------
# java.net.http client-side tests
# ---------------------------------------------------------------------------

def test_java_net_http_get() -> None:
    source = """
public class UserClient {
    public HttpResponse<String> getUser() throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("/api/users"))
            .GET()
            .build();
        return client.send(request, HttpResponse.BodyHandlers.ofString());
    }
}
"""
    from synapse.indexer.java.java_http_extractor import JavaHttpExtractor
    extractor = JavaHttpExtractor()
    result = extractor.extract("test.java", _parse(source), _symbols([("getUser", "UserClient.getUser", 3, 9)]))
    assert len(result.client_calls) == 1
    call = result.client_calls[0]
    assert call.route == "/api/users"
    assert call.http_method == "GET"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_url_without_slash_skipped() -> None:
    """A 'URL' argument without '/' is filtered out to avoid false positives."""
    source = """
public class UserClient {
    public User getUser() {
        return restTemplate.getForObject("somekey", User.class);
    }
}
"""
    from synapse.indexer.java.java_http_extractor import JavaHttpExtractor
    extractor = JavaHttpExtractor()
    result = extractor.extract("test.java", _parse(source), _symbols([("getUser", "UserClient.getUser", 3, 5)]))
    assert len(result.client_calls) == 0


def test_empty_source() -> None:
    from synapse.indexer.java.java_http_extractor import JavaHttpExtractor
    extractor = JavaHttpExtractor()
    result = extractor.extract("test.java", _parse(""), [])
    assert result.endpoint_defs == []
    assert result.client_calls == []


# ---------------------------------------------------------------------------
# JAX-RS server-side endpoint tests
# ---------------------------------------------------------------------------

def test_jaxrs_path_with_get() -> None:
    """JAX-RS: @Path on class + @GET on method → SERVES edge."""
    source = """
@Path("/route")
public class RouteResource {
    @GET
    public Response getRoute() { return null; }
}
"""
    from synapse.indexer.java.java_http_extractor import JavaHttpExtractor
    extractor = JavaHttpExtractor()
    result = extractor.extract("test.java", _parse(source), _symbols([("getRoute", "RouteResource.getRoute", 4, 5)]))
    assert len(result.endpoint_defs) == 1
    ep = result.endpoint_defs[0]
    assert ep.route == "/route"
    assert ep.http_method == "GET"
    assert ep.handler_full_name == "RouteResource.getRoute"


def test_jaxrs_path_with_post() -> None:
    """JAX-RS: @Path on class + @POST on method → POST endpoint."""
    source = """
@Path("/route")
public class RouteResource {
    @POST
    public Response createRoute() { return null; }
}
"""
    from synapse.indexer.java.java_http_extractor import JavaHttpExtractor
    extractor = JavaHttpExtractor()
    result = extractor.extract("test.java", _parse(source), _symbols([("createRoute", "RouteResource.createRoute", 4, 5)]))
    assert len(result.endpoint_defs) == 1
    assert result.endpoint_defs[0].http_method == "POST"
    assert result.endpoint_defs[0].route == "/route"


def test_jaxrs_class_and_method_path_combined() -> None:
    """JAX-RS: class @Path + method @Path combined."""
    source = """
@Path("/api")
public class InfoResource {
    @GET
    @Path("/info")
    public Response getInfo() { return null; }
}
"""
    from synapse.indexer.java.java_http_extractor import JavaHttpExtractor
    extractor = JavaHttpExtractor()
    result = extractor.extract("test.java", _parse(source), _symbols([("getInfo", "InfoResource.getInfo", 4, 6)]))
    assert len(result.endpoint_defs) == 1
    assert result.endpoint_defs[0].route == "/api/info"
    assert result.endpoint_defs[0].http_method == "GET"


def test_jaxrs_put_delete_patch() -> None:
    """JAX-RS: @PUT, @DELETE, @PATCH marker annotations."""
    source = """
@Path("/items")
public class ItemResource {
    @PUT
    @Path("/{id}")
    public Response updateItem() { return null; }

    @DELETE
    @Path("/{id}")
    public Response deleteItem() { return null; }

    @PATCH
    @Path("/{id}")
    public Response patchItem() { return null; }
}
"""
    from synapse.indexer.java.java_http_extractor import JavaHttpExtractor
    extractor = JavaHttpExtractor()
    result = extractor.extract("test.java", _parse(source), _symbols([
        ("updateItem", "ItemResource.updateItem", 4, 6),
        ("deleteItem", "ItemResource.deleteItem", 8, 10),
        ("patchItem", "ItemResource.patchItem", 12, 14),
    ]))
    assert len(result.endpoint_defs) == 3
    methods = {ep.http_method for ep in result.endpoint_defs}
    assert methods == {"PUT", "DELETE", "PATCH"}
    for ep in result.endpoint_defs:
        assert ep.route == "/items/{id}"


def test_jaxrs_no_verb_annotation_skipped() -> None:
    """JAX-RS: method with @Path but no HTTP verb annotation is skipped."""
    source = """
@Path("/items")
public class ItemResource {
    @Path("/sub")
    public SubResource getSubResource() { return null; }
}
"""
    from synapse.indexer.java.java_http_extractor import JavaHttpExtractor
    extractor = JavaHttpExtractor()
    result = extractor.extract("test.java", _parse(source), _symbols([("getSubResource", "ItemResource.getSubResource", 4, 5)]))
    assert len(result.endpoint_defs) == 0


def test_jaxrs_class_without_path_skipped() -> None:
    """A class without @Path or Spring controller annotation is still skipped."""
    source = """
public class ItemService {
    @GET
    public Response getAll() { return null; }
}
"""
    from synapse.indexer.java.java_http_extractor import JavaHttpExtractor
    extractor = JavaHttpExtractor()
    result = extractor.extract("test.java", _parse(source), _symbols([("getAll", "ItemService.getAll", 3, 4)]))
    assert len(result.endpoint_defs) == 0


def test_jaxrs_mixed_with_spring_in_same_file() -> None:
    """Both Spring and JAX-RS classes in the same file are detected independently."""
    source = """
@RestController
@RequestMapping("/spring")
public class SpringController {
    @GetMapping("/hello")
    public String hello() { return "hello"; }
}

@Path("/jaxrs")
public class JaxrsResource {
    @GET
    public Response getAll() { return null; }
}
"""
    from synapse.indexer.java.java_http_extractor import JavaHttpExtractor
    extractor = JavaHttpExtractor()
    result = extractor.extract("test.java", _parse(source), _symbols([
        ("hello", "SpringController.hello", 5, 6),
        ("getAll", "JaxrsResource.getAll", 11, 12),
    ]))
    assert len(result.endpoint_defs) == 2
    routes = {ep.route for ep in result.endpoint_defs}
    assert "/spring/hello" in routes
    assert "/jaxrs" in routes
