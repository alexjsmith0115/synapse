from __future__ import annotations

import logging
import re

from tree_sitter import Tree

from synapps.indexer.http.interface import HttpClientCall, HttpEndpointDef, HttpExtractionResult
from synapps.indexer.http.route_utils import normalize_route
from synapps.indexer.tree_sitter_util import node_text
from synapps.lsp.interface import IndexSymbol

log = logging.getLogger(__name__)

_HTTP_VERB_MAP: dict[str, str] = {
    "HttpGet": "GET",
    "HttpPost": "POST",
    "HttpPut": "PUT",
    "HttpDelete": "DELETE",
    "HttpPatch": "PATCH",
}

_CONTROLLER_ATTRS = frozenset({"ApiController"})

_HTTPCLIENT_VERB_MAP: dict[str, str] = {
    "GetAsync": "GET",
    "GetStringAsync": "GET",
    "GetByteArrayAsync": "GET",
    "GetStreamAsync": "GET",
    "GetFromJsonAsync": "GET",
    "PostAsync": "POST",
    "PostAsJsonAsync": "POST",
    "PutAsync": "PUT",
    "PutAsJsonAsync": "PUT",
    "DeleteAsync": "DELETE",
    "PatchAsync": "PATCH",
    "PatchAsJsonAsync": "PATCH",
}

_RESTSHARP_METHOD_MAP: dict[str, str] = {
    "Get": "GET",
    "Post": "POST",
    "Put": "PUT",
    "Delete": "DELETE",
    "Patch": "PATCH",
}

_FASTENDPOINTS_BASE_TYPES = frozenset({
    "Endpoint",
    "EndpointWithoutRequest",
    "EndpointWithMapper",
})

_FASTENDPOINTS_VERB_MAP: dict[str, str] = {
    "Get": "GET",
    "Post": "POST",
    "Put": "PUT",
    "Delete": "DELETE",
    "Patch": "PATCH",
}


class CSharpHttpExtractor:
    """Extract HTTP endpoint definitions and client calls from C# source files.

    Server-side: detects ASP.NET Core controller methods annotated with [HttpGet], etc.
    Client-side: detects HttpClient.GetAsync/PostAsync/etc. and RestSharp RestRequest constructor calls.
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

        # Build sorted (start_line_0, end_line_0, full_name) for enclosing-method lookup
        sorted_symbols: list[tuple[int, int, str]] = sorted(
            [
                (s.line - 1, s.end_line - 1 if s.end_line else s.line - 1, s.full_name)
                for s in symbols
            ],
            key=lambda t: t[0],
        )

        endpoint_defs: list[HttpEndpointDef] = []
        client_calls: list[HttpClientCall] = []
        self._walk(tree.root_node, endpoint_defs, symbol_by_name_line, client_calls, sorted_symbols)
        return HttpExtractionResult(endpoint_defs=endpoint_defs, client_calls=client_calls)

    def _walk(self, node, results, symbol_map, client_results, sorted_symbols):
        if node.type == "class_declaration":
            claimed = self._handle_fastendpoints(node, results, symbol_map)
            if not claimed:
                self._handle_class(node, results, symbol_map)
        if node.type == "invocation_expression":
            self._handle_invocation(node, client_results, sorted_symbols)
        elif node.type == "object_creation_expression":
            self._handle_object_creation(node, client_results, sorted_symbols)
        for child in node.children:
            self._walk(child, results, symbol_map, client_results, sorted_symbols)

    def _handle_class(self, node, results, symbol_map):
        attrs = _collect_attrs_with_args(node)
        attr_names = {name for name, _ in attrs}

        # A class is a controller if it has [ApiController] directly,
        # OR if it has [Route(...)] (covers the common pattern where
        # [ApiController] is on a base class like BaseApiController).
        has_api_controller = bool(_CONTROLLER_ATTRS & attr_names)
        has_route = any(name == "Route" and arg for name, arg in attrs)
        if not has_api_controller and not has_route:
            return

        class_name = _extract_name(node)
        if not class_name:
            return

        class_route = ""
        for name, arg in attrs:
            if name == "Route" and arg:
                class_route = arg
                controller_name = class_name
                if controller_name.endswith("Controller"):
                    controller_name = controller_name[: -len("Controller")]
                class_route = re.sub(
                    r"\[controller\]", controller_name.lower(), class_route, flags=re.IGNORECASE,
                )
                break

        for child in node.children:
            if child.type == "declaration_list":
                for member in child.children:
                    if member.type == "method_declaration":
                        self._handle_method(member, class_route, results, symbol_map)

    def _handle_method(self, node, class_route, results, symbol_map):
        attrs = _collect_attrs_with_args(node)
        method_name = _extract_name(node)
        if not method_name:
            return

        method_line = node.start_point[0] + 1

        sym = symbol_map.get((method_name, method_line))
        if sym is None:
            # Fall back to name-only match when line numbers don't align
            for (name, _line), s in symbol_map.items():
                if name == method_name:
                    sym = s
                    break
        if sym is None:
            return

        for attr_name, attr_arg in attrs:
            http_method = _HTTP_VERB_MAP.get(attr_name)
            if http_method is None:
                continue
            method_route = attr_arg or ""
            route = normalize_route(class_route, method_route)
            results.append(HttpEndpointDef(
                route=route,
                http_method=http_method,
                handler_full_name=sym.full_name,
                line=method_line,
            ))

    def _handle_fastendpoints(self, node, results, symbol_map) -> bool:
        """Detect FastEndpoints classes and extract endpoint defs from Configure().

        Returns True if this class was claimed as a FastEndpoints endpoint (preventing
        _handle_class from running on the same node — D-03 mutual exclusion).
        """
        base_list_node = None
        for child in node.children:
            if child.type == "base_list":
                base_list_node = child
                break

        if base_list_node is None:
            return False

        entries = [c for c in base_list_node.children if c.type not in (":", ",")]
        matched = any(
            _extract_simple_base_name(entry) in _FASTENDPOINTS_BASE_TYPES
            for entry in entries
        )
        if not matched:
            return False

        class_name = _extract_name(node)
        if not class_name:
            return False

        # Resolve HandleAsync full_name from symbol_map
        handler_full_name: str | None = None
        for (sym_name, _line), sym in symbol_map.items():
            if sym_name == "HandleAsync" and class_name in sym.full_name:
                handler_full_name = sym.full_name
                break

        if handler_full_name is None:
            log.debug("FastEndpoints class %s: HandleAsync not found in symbol_map — skipping", class_name)
            return True

        self._parse_configure_method(node, handler_full_name, results)
        return True

    def _parse_configure_method(self, class_node, handler_full_name, results):
        """Walk Configure() body for FastEndpoints verb calls and build HttpEndpointDef entries."""
        for child in class_node.children:
            if child.type != "declaration_list":
                continue
            for member in child.children:
                if member.type != "method_declaration":
                    continue
                if _extract_name(member) != "Configure":
                    continue
                body = member.child_by_field_name("body")
                if body is None:
                    return
                self._walk_configure_body(body, handler_full_name, results)
                return

    def _walk_configure_body(self, body_node, handler_full_name, results):
        """Recursively walk a Configure() block for verb invocation_expression nodes."""
        for child in body_node.children:
            if child.type == "expression_statement":
                for expr_child in child.children:
                    if expr_child.type == "invocation_expression":
                        self._try_extract_verb_call(expr_child, handler_full_name, results)
            elif child.type == "invocation_expression":
                self._try_extract_verb_call(child, handler_full_name, results)
            else:
                self._walk_configure_body(child, handler_full_name, results)

    def _try_extract_verb_call(self, invocation_node, handler_full_name, results):
        """Check if an invocation_expression is a bare FastEndpoints verb call and emit endpoint."""
        # FastEndpoints verb calls are bare identifiers (not member_access_expression)
        function_node = invocation_node.child_by_field_name("function")
        if function_node is None:
            for child in invocation_node.children:
                if child.type == "identifier":
                    function_node = child
                    break
        if function_node is None or function_node.type != "identifier":
            return

        verb_name = node_text(function_node)
        http_method = _FASTENDPOINTS_VERB_MAP.get(verb_name)
        if http_method is None:
            return

        # Extract the first string argument (the route)
        arg_list_node = None
        for child in invocation_node.children:
            if child.type == "argument_list":
                arg_list_node = child
                break
        if arg_list_node is None:
            return

        first = _first_arg(arg_list_node)
        if first is None:
            return

        route_str: str | None = None
        for child in first.children:
            route_str = _try_string_literal(child)
            if route_str is not None:
                break
        if route_str is None:
            return

        results.append(HttpEndpointDef(
            route=normalize_route("", route_str),
            http_method=http_method,
            handler_full_name=handler_full_name,
            line=invocation_node.start_point[0] + 1,
        ))

    def _handle_invocation(self, node, client_results, sorted_symbols):
        """Detect HttpClient verb calls: _httpClient.GetAsync(url), etc."""
        # invocation_expression children: member_access_expression + argument_list
        member_node = None
        arg_list_node = None
        for child in node.children:
            if child.type == "member_access_expression":
                member_node = child
            elif child.type == "argument_list":
                arg_list_node = child

        if member_node is None or arg_list_node is None:
            return

        # Extract the method name (last identifier in member_access_expression)
        method_name = _extract_last_identifier(member_node)
        if method_name is None:
            return

        http_method = _HTTPCLIENT_VERB_MAP.get(method_name)
        if http_method is None:
            return

        # First argument is the URL
        url_node = _first_arg(arg_list_node)
        if url_node is None:
            return

        route = _resolve_csharp_url(url_node)
        if route is None or "/" not in route:
            return

        call_line_0 = node.start_point[0]
        call_col_0 = node.start_point[1]

        caller = _find_enclosing_symbol(call_line_0, sorted_symbols)
        if caller is None:
            return

        client_results.append(HttpClientCall(
            route=route,
            http_method=http_method,
            caller_full_name=caller,
            line=call_line_0 + 1,
            col=call_col_0,
        ))

    def _handle_object_creation(self, node, client_results, sorted_symbols):
        """Detect RestSharp calls: new RestRequest("/api/users", Method.Get)."""
        # object_creation_expression: new <type> <argument_list>
        type_name = None
        arg_list_node = None
        for child in node.children:
            if child.type == "identifier":
                type_name = node_text(child)
            elif child.type == "argument_list":
                arg_list_node = child

        if type_name != "RestRequest" or arg_list_node is None:
            return

        # Extract positional arguments: (url, Method.Verb)
        args = [c for c in arg_list_node.children if c.type == "argument"]
        if len(args) < 2:
            return

        url_node = args[0]
        method_arg_node = args[1]

        route = _resolve_csharp_url(url_node)
        if route is None or "/" not in route:
            return

        # Method.Get -> member_access_expression -> last identifier
        http_method = _extract_restsharp_method(method_arg_node)
        if http_method is None:
            return

        call_line_0 = node.start_point[0]
        call_col_0 = node.start_point[1]

        caller = _find_enclosing_symbol(call_line_0, sorted_symbols)
        if caller is None:
            return

        client_results.append(HttpClientCall(
            route=route,
            http_method=http_method,
            caller_full_name=caller,
            line=call_line_0 + 1,
            col=call_col_0,
        ))


def _collect_attrs_with_args(node) -> list[tuple[str, str]]:
    attrs: list[tuple[str, str]] = []
    for child in node.children:
        if child.type == "attribute_list":
            for attr_child in child.children:
                if attr_child.type == "attribute":
                    name = _extract_attr_name(attr_child)
                    arg = _extract_first_string_arg(attr_child)
                    if name:
                        name = _normalize_attr_name(name)
                        attrs.append((name, arg))
    return attrs


def _extract_attr_name(attr_node) -> str | None:
    for child in attr_node.children:
        if child.type == "identifier":
            return node_text(child)
        if child.type == "qualified_name":
            return _extract_qualified_text(child)
    return None


def _extract_first_string_arg(attr_node) -> str:
    for child in attr_node.children:
        if child.type == "attribute_argument_list":
            for arg_child in child.children:
                if arg_child.type == "attribute_argument":
                    return _find_string_literal(arg_child)
                text = _try_string_literal(arg_child)
                if text is not None:
                    return text
    return ""


def _find_string_literal(node) -> str:
    text = _try_string_literal(node)
    if text is not None:
        return text
    for child in node.children:
        text = _find_string_literal(child)
        if text is not None:
            return text
    return ""


def _try_string_literal(node) -> str | None:
    if node.type in ("string_literal", "verbatim_string_literal"):
        raw = node_text(node)
        if raw.startswith('"') and raw.endswith('"'):
            return raw[1:-1]
        if raw.startswith('@"') and raw.endswith('"'):
            return raw[2:-1]
    return None


def _extract_name(node) -> str | None:
    # Use the named 'name' field when available (class_declaration, method_declaration, etc.)
    named = node.child_by_field_name("name")
    if named is not None:
        return node_text(named)
    for child in node.children:
        if child.type == "identifier":
            return node_text(child)
    return None


def _normalize_attr_name(name: str) -> str:
    if name.endswith("Attribute") and name != "Attribute":
        parts = name.rsplit(".", 1)
        if parts[-1].endswith("Attribute") and parts[-1] != "Attribute":
            parts[-1] = parts[-1][: -len("Attribute")]
            return ".".join(parts)
    return name


def _extract_qualified_text(node) -> str:
    parts: list[str] = []
    for child in node.children:
        if child.type == "identifier":
            parts.append(node_text(child))
        elif child.type == "qualified_name":
            parts.append(_extract_qualified_text(child))
    return ".".join(parts)


def _extract_last_identifier(node) -> str | None:
    """Extract the rightmost identifier from a member_access_expression (the method name).

    Handles both plain identifiers (GetAsync) and generic names (GetFromJsonAsync<T>)
    where tree-sitter wraps the identifier inside a generic_name node.
    """
    last: str | None = None
    for child in node.children:
        if child.type == "identifier":
            last = node_text(child)
        elif child.type == "generic_name":
            for gc in child.children:
                if gc.type == "identifier":
                    last = node_text(gc)
                    break
    return last


def _extract_simple_base_name(node) -> str | None:
    """Extract the simple (unqualified, non-generic) name from a base_list entry node.

    Handles identifier (EndpointWithoutRequest), generic_name (Endpoint<T>),
    and qualified_name (Ns.Endpoint<T>) node types — mirrors _extract_base_name
    from csharp_base_type_extractor but returns only the name string.
    """
    if node.type == "identifier":
        return node_text(node)
    if node.type == "generic_name":
        for child in node.children:
            if child.type == "identifier":
                return node_text(child)
    if node.type == "qualified_name":
        last: str | None = None
        for child in node.children:
            candidate = _extract_simple_base_name(child)
            if candidate is not None:
                last = candidate
        return last
    return None


def _first_arg(arg_list_node) -> object | None:
    """Return the first argument node from an argument_list."""
    for child in arg_list_node.children:
        if child.type == "argument":
            return child
    return None


def _resolve_csharp_url(node) -> str | None:
    """Resolve a C# URL from an argument node.

    Handles:
    - string_literal: extract inner content
    - interpolated_string_expression: collect text fragments and replace interpolations with {param}
    - Unwraps argument node to its expression child if needed
    """
    # Unwrap argument node
    if node.type == "argument":
        for child in node.children:
            if child.type not in (",", "(", ")", "ref", "out", "in"):
                return _resolve_csharp_url(child)
        return None

    if node.type == "string_literal":
        # Extract string_literal_content child
        for child in node.children:
            if child.type == "string_literal_content":
                return node_text(child)
        return ""

    if node.type == "interpolated_string_expression":
        parts: list[str] = []
        for child in node.children:
            if child.type == "string_content":
                parts.append(node_text(child))
            elif child.type == "interpolation":
                parts.append("{param}")
        return "".join(parts)

    return None


def _extract_restsharp_method(arg_node) -> str | None:
    """Extract HTTP verb from a RestSharp Method.Get argument node."""
    # arg_node is an argument containing member_access_expression (Method.Get)
    for child in arg_node.children:
        if child.type == "member_access_expression":
            verb = _extract_last_identifier(child)
            if verb:
                return _RESTSHARP_METHOD_MAP.get(verb)
    return None


def _find_enclosing_symbol(call_line_0: int, sorted_symbols: list[tuple[int, int, str]]) -> str | None:
    """Return the full_name of the narrowest symbol whose range contains call_line_0."""
    best: str | None = None
    best_span = float("inf")
    for start_0, end_0, full_name in sorted_symbols:
        if start_0 <= call_line_0 <= end_0:
            span = end_0 - start_0
            if span < best_span:
                best_span = span
                best = full_name
        elif start_0 > call_line_0:
            break
    return best
