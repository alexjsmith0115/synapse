from __future__ import annotations

import tree_sitter_java
from tree_sitter import Language, Parser

from synapps.lsp.interface import IndexSymbol, SymbolKind

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
    from synapps.indexer.java.java_http_extractor import JavaHttpExtractor
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
    from synapps.indexer.java.java_http_extractor import JavaHttpExtractor
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
    from synapps.indexer.java.java_http_extractor import JavaHttpExtractor
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
    from synapps.indexer.java.java_http_extractor import JavaHttpExtractor
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
    from synapps.indexer.java.java_http_extractor import JavaHttpExtractor
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
    from synapps.indexer.java.java_http_extractor import JavaHttpExtractor
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
    from synapps.indexer.java.java_http_extractor import JavaHttpExtractor
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
    from synapps.indexer.java.java_http_extractor import JavaHttpExtractor
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
    from synapps.indexer.java.java_http_extractor import JavaHttpExtractor
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
    from synapps.indexer.java.java_http_extractor import JavaHttpExtractor
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
    from synapps.indexer.java.java_http_extractor import JavaHttpExtractor
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
    from synapps.indexer.java.java_http_extractor import JavaHttpExtractor
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
    from synapps.indexer.java.java_http_extractor import JavaHttpExtractor
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
    from synapps.indexer.java.java_http_extractor import JavaHttpExtractor
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
    from synapps.indexer.java.java_http_extractor import JavaHttpExtractor
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
    from synapps.indexer.java.java_http_extractor import JavaHttpExtractor
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
    from synapps.indexer.java.java_http_extractor import JavaHttpExtractor
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
    from synapps.indexer.java.java_http_extractor import JavaHttpExtractor
    extractor = JavaHttpExtractor()
    result = extractor.extract("test.java", _parse(source), _symbols([("getUser", "UserClient.getUser", 3, 5)]))
    assert len(result.client_calls) == 0


def test_empty_source() -> None:
    from synapps.indexer.java.java_http_extractor import JavaHttpExtractor
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
    from synapps.indexer.java.java_http_extractor import JavaHttpExtractor
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
    from synapps.indexer.java.java_http_extractor import JavaHttpExtractor
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
    from synapps.indexer.java.java_http_extractor import JavaHttpExtractor
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
    from synapps.indexer.java.java_http_extractor import JavaHttpExtractor
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
    from synapps.indexer.java.java_http_extractor import JavaHttpExtractor
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
    from synapps.indexer.java.java_http_extractor import JavaHttpExtractor
    extractor = JavaHttpExtractor()
    result = extractor.extract("test.java", _parse(source), _symbols([("getAll", "ItemService.getAll", 3, 4)]))
    assert len(result.endpoint_defs) == 0


def test_jaxrs_symbol_with_parens_in_name() -> None:
    """JDT LS provides names like 'getInfo()' — extractor should still match."""
    source = """
@Path("/info")
public class InfoResource {
    @GET
    public Response getInfo() { return null; }
}
"""
    from synapps.indexer.java.java_http_extractor import JavaHttpExtractor
    extractor = JavaHttpExtractor()
    # Simulate JDT LS naming: "getInfo()" instead of "getInfo"
    result = extractor.extract("test.java", _parse(source), _symbols([("getInfo()", "InfoResource.getInfo()", 4, 5)]))
    assert len(result.endpoint_defs) == 1
    assert result.endpoint_defs[0].route == "/info"
    assert result.endpoint_defs[0].handler_full_name == "InfoResource.getInfo()"


def test_jaxrs_symbol_line_off_by_one() -> None:
    """JDT LS may report 0-based line numbers — extractor should still match."""
    source = """
@Path("/route")
public class RouteResource {
    @GET
    public Response getRoute() { return null; }
}
"""
    from synapps.indexer.java.java_http_extractor import JavaHttpExtractor
    extractor = JavaHttpExtractor()
    # Line 3 (0-based) instead of 4 (1-based) for the method at tree-sitter line 4
    result = extractor.extract("test.java", _parse(source), _symbols([("getRoute", "RouteResource.getRoute", 3, 5)]))
    assert len(result.endpoint_defs) == 1
    assert result.endpoint_defs[0].handler_full_name == "RouteResource.getRoute"


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
    from synapps.indexer.java.java_http_extractor import JavaHttpExtractor
    extractor = JavaHttpExtractor()
    result = extractor.extract("test.java", _parse(source), _symbols([
        ("hello", "SpringController.hello", 5, 6),
        ("getAll", "JaxrsResource.getAll", 11, 12),
    ]))
    assert len(result.endpoint_defs) == 2
    routes = {ep.route for ep in result.endpoint_defs}
    assert "/spring/hello" in routes
    assert "/jaxrs" in routes


def test_jaxrs_constraint_route_normalized() -> None:
    """JAX-RS path with constraint like {id: [0-9]+} is normalized to {id} -- PROD-03 round-trip."""
    source = """
@Path("/items/{id: [0-9]+}")
public class ItemResource {
    @GET
    public Response getItem() { return null; }
}
"""
    from synapps.indexer.java.java_http_extractor import JavaHttpExtractor
    extractor = JavaHttpExtractor()
    result = extractor.extract("test.java", _parse(source), _symbols([("getItem", "ItemResource.getItem", 4, 5)]))
    assert len(result.endpoint_defs) == 1
    ep = result.endpoint_defs[0]
    assert ep.route == "/items/{id}"
    assert ep.http_method == "GET"


# ---------------------------------------------------------------------------
# _find_enclosing_symbol narrowest-range tests -- PROD-04 regression
# ---------------------------------------------------------------------------

from synapps.indexer.java.java_http_extractor import _find_enclosing_symbol


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
# RestTemplate exchange() tests
# ---------------------------------------------------------------------------

def test_rest_template_exchange_get() -> None:
    """exchange(url, HttpMethod.GET, ...) with string_literal URL produces GET client call."""
    source = """
public class OrderClient {
    public String getOrders() {
        return restTemplate.exchange("/api/orders", HttpMethod.GET, entity, String.class);
    }
}
"""
    from synapps.indexer.java.java_http_extractor import JavaHttpExtractor
    extractor = JavaHttpExtractor()
    result = extractor.extract("test.java", _parse(source), _symbols([("getOrders", "OrderClient.getOrders", 3, 5)]))
    assert len(result.client_calls) == 1
    call = result.client_calls[0]
    assert call.route == "/api/orders"
    assert call.http_method == "GET"
    assert call.caller_full_name == "OrderClient.getOrders"


def test_rest_template_exchange_post() -> None:
    """exchange(url, HttpMethod.POST, ...) produces POST client call."""
    source = """
public class OrderClient {
    public String createOrder(Object entity) {
        return restTemplate.exchange("/api/orders", HttpMethod.POST, entity, String.class);
    }
}
"""
    from synapps.indexer.java.java_http_extractor import JavaHttpExtractor
    extractor = JavaHttpExtractor()
    result = extractor.extract("test.java", _parse(source), _symbols([("createOrder", "OrderClient.createOrder", 3, 5)]))
    assert len(result.client_calls) == 1
    call = result.client_calls[0]
    assert call.route == "/api/orders"
    assert call.http_method == "POST"


def test_rest_template_exchange_put() -> None:
    """exchange(url, HttpMethod.PUT, ...) produces PUT client call."""
    source = """
public class OrderClient {
    public void updateOrder(Object entity) {
        restTemplate.exchange("/api/orders/1", HttpMethod.PUT, entity, String.class);
    }
}
"""
    from synapps.indexer.java.java_http_extractor import JavaHttpExtractor
    extractor = JavaHttpExtractor()
    result = extractor.extract("test.java", _parse(source), _symbols([("updateOrder", "OrderClient.updateOrder", 3, 5)]))
    assert len(result.client_calls) == 1
    assert result.client_calls[0].http_method == "PUT"
    assert result.client_calls[0].route == "/api/orders/1"


def test_rest_template_exchange_delete() -> None:
    """exchange(url, HttpMethod.DELETE, ...) produces DELETE client call."""
    source = """
public class OrderClient {
    public void deleteOrder() {
        restTemplate.exchange("/api/orders/1", HttpMethod.DELETE, null, String.class);
    }
}
"""
    from synapps.indexer.java.java_http_extractor import JavaHttpExtractor
    extractor = JavaHttpExtractor()
    result = extractor.extract("test.java", _parse(source), _symbols([("deleteOrder", "OrderClient.deleteOrder", 3, 5)]))
    assert len(result.client_calls) == 1
    assert result.client_calls[0].http_method == "DELETE"
    assert result.client_calls[0].route == "/api/orders/1"


def test_rest_template_exchange_binary_expression_url() -> None:
    """exchange(baseUrl + "/orders/" + orderId, ...) produces {param}/orders/{param} route."""
    source = """
public class OrderClient {
    public String getOrders() {
        return restTemplate.exchange(baseUrl + "/orders/" + orderId, HttpMethod.GET, entity, String.class);
    }
}
"""
    from synapps.indexer.java.java_http_extractor import JavaHttpExtractor
    extractor = JavaHttpExtractor()
    result = extractor.extract("test.java", _parse(source), _symbols([("getOrders", "OrderClient.getOrders", 3, 5)]))
    assert len(result.client_calls) == 1
    call = result.client_calls[0]
    assert call.http_method == "GET"
    # String literal parts preserved, identifier parts become {param}
    assert "{param}" in call.route
    assert "/orders/" in call.route


def test_rest_template_exchange_identifier_url() -> None:
    """exchange(url, HttpMethod.GET, ...) where url is bare identifier -> route='{dynamic}'."""
    source = """
public class OrderClient {
    public String getOrders(String url) {
        return restTemplate.exchange(url, HttpMethod.GET, entity, String.class);
    }
}
"""
    from synapps.indexer.java.java_http_extractor import JavaHttpExtractor
    extractor = JavaHttpExtractor()
    result = extractor.extract("test.java", _parse(source), _symbols([("getOrders", "OrderClient.getOrders", 3, 5)]))
    assert len(result.client_calls) == 1
    assert result.client_calls[0].route == "{dynamic}"


def test_rest_template_exchange_no_slash_in_resolved_url_skipped() -> None:
    """binary_expression URL that resolves to no '/' produces no client call."""
    source = """
public class OrderClient {
    public String getData() {
        return restTemplate.exchange(prefix + suffix, HttpMethod.GET, entity, String.class);
    }
}
"""
    from synapps.indexer.java.java_http_extractor import JavaHttpExtractor
    extractor = JavaHttpExtractor()
    result = extractor.extract("test.java", _parse(source), _symbols([("getData", "OrderClient.getData", 3, 5)]))
    # No slash in resolved URL -> skipped
    assert len(result.client_calls) == 0


def test_rest_template_exchange_caller_attribution() -> None:
    """exchange() inside a named method -> caller_full_name matches enclosing method."""
    source = """
public class TrainClient {
    public String queryTrains() {
        return restTemplate.exchange("/api/trains", HttpMethod.GET, entity, String.class);
    }
}
"""
    from synapps.indexer.java.java_http_extractor import JavaHttpExtractor
    extractor = JavaHttpExtractor()
    result = extractor.extract("test.java", _parse(source), _symbols([("queryTrains", "TrainClient.queryTrains", 3, 5)]))
    assert len(result.client_calls) == 1
    assert result.client_calls[0].caller_full_name == "TrainClient.queryTrains"
