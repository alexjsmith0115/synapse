from __future__ import annotations

import logging

from tree_sitter import Tree

from synapse.indexer.http.interface import HttpClientCall, HttpEndpointDef, HttpExtractionResult
from synapse.indexer.http.route_utils import normalize_route
from synapse.indexer.tree_sitter_util import node_text
from synapse.lsp.interface import IndexSymbol

log = logging.getLogger(__name__)

_SPRING_VERB_MAP: dict[str, str] = {
    "GetMapping": "GET",
    "PostMapping": "POST",
    "PutMapping": "PUT",
    "DeleteMapping": "DELETE",
    "PatchMapping": "PATCH",
}

_SPRING_CONTROLLER_MARKERS = frozenset({"RestController", "Controller"})

_JAXRS_VERB_MAP: dict[str, str] = {
    "GET": "GET",
    "POST": "POST",
    "PUT": "PUT",
    "DELETE": "DELETE",
    "PATCH": "PATCH",
    "HEAD": "HEAD",
    "OPTIONS": "OPTIONS",
}

_REQUEST_METHOD_MAP: dict[str, str] = {
    "GET": "GET",
    "POST": "POST",
    "PUT": "PUT",
    "DELETE": "DELETE",
    "PATCH": "PATCH",
    "HEAD": "HEAD",
    "OPTIONS": "OPTIONS",
}

_RESTTEMPLATE_MAP: dict[str, str] = {
    "getForObject": "GET",
    "getForEntity": "GET",
    "postForObject": "POST",
    "postForEntity": "POST",
    "put": "PUT",
    "delete": "DELETE",
    "patchForObject": "PATCH",
}

_WEBCLIENT_VERB_METHODS = frozenset({"get", "post", "put", "delete", "patch"})

_JAVA_NET_HTTP_VERBS = frozenset({"GET", "POST", "PUT", "DELETE", "PATCH"})


class JavaHttpExtractor:
    """Extract HTTP endpoint definitions and client calls from Java source files.

    Server-side: Spring @XxxMapping annotations on @RestController/@Controller classes.
    Client-side: RestTemplate, WebClient, and java.net.http.HttpRequest builder chains.
    """

    def extract(
        self,
        file_path: str,
        tree: Tree,
        symbols: list[IndexSymbol],
    ) -> HttpExtractionResult:
        symbol_by_name_line: dict[tuple[str, int], IndexSymbol] = {}
        for sym in symbols:
            symbol_by_name_line[(sym.name, sym.line)] = sym

        # Sorted list for enclosing symbol lookup (0-indexed lines)
        sorted_symbols: list[tuple[int, int, str]] = sorted(
            [
                (s.line - 1, s.end_line - 1 if s.end_line else s.line - 1, s.full_name)
                for s in symbols
            ],
            key=lambda t: t[0],
        )

        endpoint_defs: list[HttpEndpointDef] = []
        client_calls: list[HttpClientCall] = []
        self._walk(tree.root_node, endpoint_defs, client_calls, symbol_by_name_line, sorted_symbols)
        return HttpExtractionResult(endpoint_defs=endpoint_defs, client_calls=client_calls)

    def _walk(self, node, endpoint_defs, client_calls, symbol_map, sorted_symbols) -> None:
        if node.type == "class_declaration":
            self._handle_class(node, endpoint_defs, symbol_map)
        if node.type == "method_invocation":
            self._handle_method_invocation(node, client_calls, sorted_symbols)
        for child in node.children:
            self._walk(child, endpoint_defs, client_calls, symbol_map, sorted_symbols)

    # ------------------------------------------------------------------
    # Spring server-side extraction
    # ------------------------------------------------------------------

    def _handle_class(self, node, endpoint_defs, symbol_map) -> None:
        modifiers_node = _find_child_by_type(node, "modifiers")
        if modifiers_node is None:
            return

        annotations = _collect_annotations(modifiers_node)
        ann_names = {name for name, _, _ in annotations}

        is_spring = bool(_SPRING_CONTROLLER_MARKERS & ann_names)
        is_jaxrs = "Path" in ann_names

        if not is_spring and not is_jaxrs:
            return

        class_route = ""
        for name, args, _arg_list_node in annotations:
            if name == "RequestMapping":
                class_route = _extract_route_from_annotation_args(args) or ""
                break
            if name == "Path":
                class_route = _extract_route_from_annotation_args(args) or ""
                break

        class_body = _find_child_by_type(node, "class_body")
        if class_body is None:
            return

        for child in class_body.children:
            if child.type == "method_declaration":
                if is_jaxrs:
                    self._handle_jaxrs_method(child, class_route, endpoint_defs, symbol_map)
                else:
                    self._handle_method(child, class_route, endpoint_defs, symbol_map)

    def _handle_method(self, node, class_route, endpoint_defs, symbol_map) -> None:
        modifiers_node = _find_child_by_type(node, "modifiers")
        if modifiers_node is None:
            return

        annotations = _collect_annotations(modifiers_node)
        method_name = _find_child_text_by_type(node, "identifier")
        if not method_name:
            return

        method_line = node.start_point[0] + 1
        sym = symbol_map.get((method_name, method_line))
        if sym is None:
            for (name, _line), s in symbol_map.items():
                if name == method_name:
                    sym = s
                    break
        if sym is None:
            return

        for ann_name, args, _arg_list_node in annotations:
            http_method = _SPRING_VERB_MAP.get(ann_name)
            if http_method is not None:
                method_route = _extract_route_from_annotation_args(args) or ""
                route = normalize_route(class_route, method_route)
                endpoint_defs.append(HttpEndpointDef(
                    route=route,
                    http_method=http_method,
                    handler_full_name=sym.full_name,
                    line=method_line,
                ))
            elif ann_name == "RequestMapping":
                method_route, http_method = _extract_route_and_method_from_request_mapping(args)
                route = normalize_route(class_route, method_route)
                endpoint_defs.append(HttpEndpointDef(
                    route=route,
                    http_method=http_method,
                    handler_full_name=sym.full_name,
                    line=method_line,
                ))

    # ------------------------------------------------------------------
    # JAX-RS server-side extraction
    # ------------------------------------------------------------------

    def _handle_jaxrs_method(self, node, class_route, endpoint_defs, symbol_map) -> None:
        modifiers_node = _find_child_by_type(node, "modifiers")
        if modifiers_node is None:
            return

        annotations = _collect_annotations(modifiers_node)
        method_name = _find_child_text_by_type(node, "identifier")
        if not method_name:
            return

        method_line = node.start_point[0] + 1
        sym = symbol_map.get((method_name, method_line))
        if sym is None:
            for (name, _line), s in symbol_map.items():
                if name == method_name:
                    sym = s
                    break
        if sym is None:
            return

        # Find HTTP verb and optional method-level @Path
        http_method: str | None = None
        method_route = ""
        for ann_name, args, _arg_list_node in annotations:
            if ann_name in _JAXRS_VERB_MAP:
                http_method = _JAXRS_VERB_MAP[ann_name]
            elif ann_name == "Path":
                method_route = _extract_route_from_annotation_args(args) or ""

        if http_method is None:
            return

        route = normalize_route(class_route, method_route)
        endpoint_defs.append(HttpEndpointDef(
            route=route,
            http_method=http_method,
            handler_full_name=sym.full_name,
            line=method_line,
        ))

    # ------------------------------------------------------------------
    # Client-side extraction
    # ------------------------------------------------------------------

    def _handle_method_invocation(self, node, client_calls, sorted_symbols) -> None:
        method_name = _method_invocation_name(node)
        if not method_name:
            return

        # RestTemplate pattern: restTemplate.getForObject("/url", ...)
        if method_name in _RESTTEMPLATE_MAP:
            http_method = _RESTTEMPLATE_MAP[method_name]
            url = _extract_first_string_arg(node)
            if url and "/" in url:
                line_0 = node.start_point[0]
                col_0 = node.start_point[1]
                caller = _find_enclosing_symbol(line_0, sorted_symbols)
                if caller is not None:
                    client_calls.append(HttpClientCall(
                        route=url,
                        http_method=http_method,
                        caller_full_name=caller,
                        line=line_0 + 1,
                        col=col_0,
                    ))

        # WebClient pattern: webClient.get().uri("/url")...
        # Detected at the .uri() call — walk up parent chain to find HTTP verb
        elif method_name == "uri":
            url = _extract_first_string_arg(node)
            if url and "/" in url:
                http_method = _find_webclient_verb(node)
                if http_method is not None:
                    line_0 = node.start_point[0]
                    col_0 = node.start_point[1]
                    caller = _find_enclosing_symbol(line_0, sorted_symbols)
                    if caller is not None:
                        client_calls.append(HttpClientCall(
                            route=url,
                            http_method=http_method,
                            caller_full_name=caller,
                            line=line_0 + 1,
                            col=col_0,
                        ))

        # java.net.http pattern: URI.create("/url") within builder chain with .GET()
        elif method_name == "create":
            if _is_uri_create_call(node):
                url = _extract_first_string_arg(node)
                if url and "/" in url:
                    http_method = _find_java_net_http_verb(node)
                    if http_method is not None:
                        line_0 = node.start_point[0]
                        col_0 = node.start_point[1]
                        caller = _find_enclosing_symbol(line_0, sorted_symbols)
                        if caller is not None:
                            client_calls.append(HttpClientCall(
                                route=url,
                                http_method=http_method,
                                caller_full_name=caller,
                                line=line_0 + 1,
                                col=col_0,
                            ))


# ---------------------------------------------------------------------------
# Annotation helpers
# ---------------------------------------------------------------------------

def _collect_annotations(modifiers_node) -> list[tuple[str, list, object]]:
    """Return [(ann_name, element_value_pairs, annotation_argument_list_node), ...] from modifiers."""
    result: list[tuple[str, list, object]] = []
    for child in modifiers_node.children:
        if child.type == "marker_annotation":
            name = _find_child_text_by_type(child, "identifier")
            if name:
                result.append((name, [], None))
        elif child.type == "annotation":
            name = _find_child_text_by_type(child, "identifier")
            if not name:
                continue
            arg_list = _find_child_by_type(child, "annotation_argument_list")
            args = _parse_annotation_args(arg_list) if arg_list else []
            result.append((name, args, arg_list))
    return result


def _parse_annotation_args(arg_list_node) -> list:
    """Parse annotation_argument_list into a list of (key, value) or (None, value) pairs."""
    items = []
    for child in arg_list_node.children:
        if child.type == "element_value_pair":
            key_node = child.children[0] if child.children else None
            key = node_text(key_node) if key_node and key_node.type == "identifier" else None
            # Value is the last non-punctuation child
            val = _find_element_value(child)
            items.append((key, val))
        elif child.type == "string_literal":
            items.append((None, child))
    return items


def _find_element_value(pair_node):
    """Return the value node from an element_value_pair (last non-= child)."""
    for child in reversed(pair_node.children):
        if child.type not in ("=", "identifier"):
            return child
    return None


def _extract_route_from_annotation_args(args: list) -> str | None:
    """Extract route string from parsed annotation args. Handles bare string, value=, path= forms."""
    for key, val_node in args:
        if key is None or key in ("value", "path"):
            if val_node is not None and val_node.type == "string_literal":
                return _extract_java_string(val_node)
    return None


def _extract_route_and_method_from_request_mapping(args: list) -> tuple[str, str]:
    """Extract route and HTTP method from @RequestMapping args. Defaults to GET."""
    route = ""
    http_method = "GET"
    for key, val_node in args:
        if val_node is None:
            continue
        if key is None or key in ("value", "path"):
            if val_node.type == "string_literal":
                route = _extract_java_string(val_node) or ""
        elif key == "method":
            # value is field_access like RequestMethod.POST -> last identifier
            verb = _extract_request_method_verb(val_node)
            if verb:
                http_method = verb
    return route, http_method


def _extract_request_method_verb(val_node) -> str | None:
    """Extract the HTTP verb from RequestMethod.XXX field access node."""
    if val_node.type == "field_access":
        # Last identifier child is the method name (GET, POST, ...)
        for child in reversed(val_node.children):
            if child.type == "identifier":
                verb = node_text(child).upper()
                return _REQUEST_METHOD_MAP.get(verb)
    return None


def _extract_java_string(string_literal_node) -> str | None:
    """Extract inner text from a Java string_literal node via string_fragment child."""
    for child in string_literal_node.children:
        if child.type == "string_fragment":
            return node_text(child)
    return ""


# ---------------------------------------------------------------------------
# Client call helpers
# ---------------------------------------------------------------------------

def _extract_first_string_arg(method_invocation_node) -> str | None:
    """Return the inner text of the first string_literal in the argument_list."""
    arg_list = _find_child_by_type(method_invocation_node, "argument_list")
    if arg_list is None:
        return None
    for child in arg_list.children:
        if child.type == "string_literal":
            return _extract_java_string(child)
    return None


def _find_webclient_verb(uri_invocation_node) -> str | None:
    """Walk up from a .uri() method_invocation to find the WebClient HTTP verb.

    The AST nests builder chains from innermost (earliest) to outermost:
    webClient.get().uri("/url").retrieve()
    is: method_invocation(object=method_invocation(webClient.get), ., uri, argument_list)

    The .uri() call's first child (object field) is the .get()/.post() invocation.
    """
    # The uri() call has an "object" field that is the .get() call
    receiver = uri_invocation_node.child_by_field_name("object")
    if receiver is None:
        # Fallback: first method_invocation child
        for child in uri_invocation_node.children:
            if child.type == "method_invocation":
                receiver = child
                break
    if receiver is not None and receiver.type == "method_invocation":
        verb_name = _method_invocation_name(receiver)
        if verb_name and verb_name in _WEBCLIENT_VERB_METHODS:
            return verb_name.upper()
    return None


def _is_uri_create_call(node) -> bool:
    """Return True if this method_invocation is URI.create(...)."""
    # The invocation object should be the identifier "URI"
    for child in node.children:
        if child.type == "identifier" and node_text(child) == "URI":
            return True
    return False


def _find_java_net_http_verb(uri_create_node) -> str | None:
    """Walk up from URI.create() to find the HTTP verb in the builder chain.

    Builder pattern: HttpRequest.newBuilder().uri(URI.create("/url")).GET().build()
    The uri() call wraps URI.create() in its argument_list.
    Walk up: uri_create_node -> argument_list -> uri() invocation -> .GET() invocation.
    """
    node = uri_create_node
    # Go up through argument_list to the enclosing .uri() invocation
    parent = node.parent
    if parent is not None and parent.type == "argument_list":
        parent = parent.parent
    # Now parent should be the .uri() method_invocation; walk up from there
    while parent is not None:
        if parent.type == "method_invocation":
            verb_name = _method_invocation_name(parent)
            if verb_name and verb_name.upper() in _JAVA_NET_HTTP_VERBS:
                return verb_name.upper()
        parent = parent.parent
    return None


def _find_enclosing_symbol(call_line_0: int, sorted_symbols: list[tuple[int, int, str]]) -> str | None:
    """Return the full_name of the innermost symbol whose line range contains call_line_0."""
    best: str | None = None
    for start_0, end_0, full_name in sorted_symbols:
        if start_0 <= call_line_0 <= end_0:
            best = full_name
        elif start_0 > call_line_0:
            break
    return best


# ---------------------------------------------------------------------------
# Generic tree-sitter helpers
# ---------------------------------------------------------------------------

def _find_child_by_type(node, child_type: str):
    """Return the first direct child of node with the given type, or None."""
    for child in node.children:
        if child.type == child_type:
            return child
    return None


def _find_child_text_by_type(node, child_type: str) -> str | None:
    """Return the text of the first direct child with the given type, or None."""
    child = _find_child_by_type(node, child_type)
    return node_text(child) if child is not None else None


def _method_invocation_name(node) -> str | None:
    """Return the method name from a method_invocation node.

    In Java AST, method_invocation can have structure:
      identifier . identifier argument_list   (simple call: foo.bar())
      method_invocation . identifier argument_list  (chained call: a.b().c())
    The method name is the identifier immediately before the argument_list.
    """
    arg_list_idx = None
    for i, child in enumerate(node.children):
        if child.type == "argument_list":
            arg_list_idx = i
            break
    if arg_list_idx is None:
        return None
    # Scan backwards from argument_list to find the method name identifier
    for i in range(arg_list_idx - 1, -1, -1):
        child = node.children[i]
        if child.type == "identifier":
            return node_text(child)
        if child.type == ".":
            continue
        break
    return None
