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

_IENDPOINTGROUP_BASE_TYPES = frozenset({
    "IEndpointGroup",
    "EndpointGroupBase",
})

_MAP_VERB_MAP: dict[str, str] = {
    "MapGet": "GET",
    "MapPost": "POST",
    "MapPut": "PUT",
    "MapDelete": "DELETE",
    "MapPatch": "PATCH",
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
        # Track whether _walk is recursing inside a claimed class (IEndpointGroup/FastEndpoints)
        # to prevent _handle_minimal_api_invocation from double-counting those nodes.
        self._in_claimed_class = False
        self._walk(tree.root_node, endpoint_defs, symbol_by_name_line, client_calls, sorted_symbols)
        return HttpExtractionResult(endpoint_defs=endpoint_defs, client_calls=client_calls)

    def _walk(self, node, results, symbol_map, client_results, sorted_symbols):
        if node.type == "class_declaration":
            claimed = self._handle_iendpointgroup(node, results, symbol_map)
            if not claimed:
                claimed = self._handle_fastendpoints(node, results, symbol_map)
            if not claimed:
                self._handle_class(node, results, symbol_map)
            # Recurse into claimed class children with the deduplication flag set so that
            # _handle_minimal_api_invocation skips invocations already handled by the
            # IEndpointGroup/FastEndpoints extractor paths.
            prior = self._in_claimed_class
            if claimed:
                self._in_claimed_class = True
            for child in node.children:
                self._walk(child, results, symbol_map, client_results, sorted_symbols)
            self._in_claimed_class = prior
            return
        if node.type == "invocation_expression":
            self._handle_minimal_api_invocation(node, results, symbol_map, sorted_symbols)
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

    def _handle_iendpointgroup(self, node, results, symbol_map) -> bool:
        """Detect IEndpointGroup / EndpointGroupBase classes and extract endpoints from Map().

        Returns True if this class was claimed (preventing _handle_class from running — mutual
        exclusion mirrors the FastEndpoints pattern).
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
            _extract_simple_base_name(entry) in _IENDPOINTGROUP_BASE_TYPES
            for entry in entries
        )
        if not matched:
            return False

        class_name = _extract_name(node)
        if not class_name:
            return False

        self._parse_map_method(node, class_name, results, symbol_map)
        return True

    def _parse_map_method(self, class_node, class_name, results, symbol_map):
        """Walk Map() body for MapGet/MapPost/etc. invocations and emit HttpEndpointDef entries."""
        for child in class_node.children:
            if child.type != "declaration_list":
                continue
            for member in child.children:
                if member.type != "method_declaration":
                    continue
                if _extract_name(member) != "Map":
                    continue
                body = member.child_by_field_name("body")
                if body is None:
                    return

                # Resolve Map method's full_name for lambda handler fallback
                map_line = member.start_point[0] + 1
                map_full_name: str | None = None
                for (sym_name, _line), sym in symbol_map.items():
                    if sym_name == "Map" and class_name in sym.full_name:
                        map_full_name = sym.full_name
                        break
                if map_full_name is None:
                    # Fallback: scan symbol_map for any Map entry in this class
                    for (_sym_name, _line), sym in symbol_map.items():
                        if class_name in sym.full_name and sym.full_name.endswith(".Map"):
                            map_full_name = sym.full_name
                            break

                self._walk_map_body(body, class_name, map_full_name, results, symbol_map)
                return

    def _walk_map_body(self, body_node, class_name, map_full_name, results, symbol_map):
        """Walk a Map() block and emit HttpEndpointDef for each MapGet/MapPost/etc. invocation."""
        for child in body_node.children:
            if child.type == "expression_statement":
                for expr_child in child.children:
                    if expr_child.type == "invocation_expression":
                        self._extract_map_invocation(
                            expr_child, class_name, map_full_name, results, symbol_map,
                        )
            elif child.type == "invocation_expression":
                self._extract_map_invocation(
                    child, class_name, map_full_name, results, symbol_map,
                )
            else:
                self._walk_map_body(child, class_name, map_full_name, results, symbol_map)

    def _extract_map_invocation(self, invocation_node, class_name, map_full_name, results, symbol_map):
        """Extract a single MapGet/MapPost/etc. call and append an HttpEndpointDef."""
        fn_node = invocation_node.child_by_field_name("function")
        if fn_node is None or fn_node.type != "member_access_expression":
            return

        name_node = fn_node.child_by_field_name("name")
        if name_node is None:
            return
        verb_name = node_text(name_node)
        http_method = _MAP_VERB_MAP.get(verb_name)
        if http_method is None:
            return

        arg_list_node = None
        for child in invocation_node.children:
            if child.type == "argument_list":
                arg_list_node = child
                break
        if arg_list_node is None:
            return

        args = [c for c in arg_list_node.children if c.type == "argument"]
        if not args:
            return

        first_arg = args[0]
        first_child = _first_non_punctuation_child(first_arg)

        if first_child is None:
            return

        if first_child.type in ("string_literal", "verbatim_string_literal"):
            # Route-first: arg[0]=route, arg[1]=handler
            route_str = _try_string_literal(first_child) or ""
            handler_full_name = _resolve_handler(args[1] if len(args) > 1 else None, class_name, map_full_name, symbol_map)
        elif first_child.type == "identifier":
            # Handler-first: arg[0]=handler, arg[1]=route
            handler_name = node_text(first_child)
            handler_full_name = _lookup_handler_full_name(handler_name, class_name, symbol_map) or map_full_name or ""
            route_str = ""
            if len(args) > 1:
                second_child = _first_non_punctuation_child(args[1])
                if second_child is not None:
                    route_str = _try_string_literal(second_child) or ""
        else:
            # Lambda or other expression in first arg position (unusual)
            route_str = ""
            handler_full_name = map_full_name or ""

        if not handler_full_name:
            return

        results.append(HttpEndpointDef(
            route=normalize_route("", route_str),
            http_method=http_method,
            handler_full_name=handler_full_name,
            line=invocation_node.start_point[0] + 1,
        ))

    def _parse_configure_method(self, class_node, handler_full_name, results):
        """Walk Configure() body for FastEndpoints verb calls and build HttpEndpointDef entries.

        Two-bucket strategy (D-04): accumulate simple_endpoints, collected_verbs, and
        collected_routes; emit cross-product of verbs x routes after the walk.
        Direct verb calls (Post("/route")) are always emitted alongside Verbs/Routes results.
        """
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
                simple_endpoints: list[HttpEndpointDef] = []
                collected_verbs: list[str] = []
                collected_routes: list[str] = []
                self._walk_configure_body(
                    body, handler_full_name, simple_endpoints, collected_verbs, collected_routes,
                )
                if collected_verbs and collected_routes:
                    for verb in collected_verbs:
                        for route in collected_routes:
                            results.append(HttpEndpointDef(
                                route=route,
                                http_method=verb,
                                handler_full_name=handler_full_name,
                                line=body.start_point[0] + 1,
                            ))
                results.extend(simple_endpoints)
                return

    def _walk_configure_body(self, body_node, handler_full_name, simple_endpoints, collected_verbs, collected_routes):
        """Recursively walk a Configure() block, routing invocations to the correct bucket."""
        for child in body_node.children:
            if child.type == "expression_statement":
                for expr_child in child.children:
                    if expr_child.type == "invocation_expression":
                        self._classify_invocation(
                            expr_child, handler_full_name, simple_endpoints, collected_verbs, collected_routes,
                        )
            elif child.type == "invocation_expression":
                self._classify_invocation(
                    child, handler_full_name, simple_endpoints, collected_verbs, collected_routes,
                )
            else:
                self._walk_configure_body(
                    child, handler_full_name, simple_endpoints, collected_verbs, collected_routes,
                )

    def _classify_invocation(self, invocation_node, handler_full_name, simple_endpoints, collected_verbs, collected_routes):
        """Route a Configure()-body invocation to simple_endpoints, collected_verbs, or collected_routes."""
        function_node = invocation_node.child_by_field_name("function")
        if function_node is None:
            for child in invocation_node.children:
                if child.type == "identifier":
                    function_node = child
                    break
        if function_node is None or function_node.type != "identifier":
            return

        call_name = node_text(function_node)

        arg_list_node = None
        for child in invocation_node.children:
            if child.type == "argument_list":
                arg_list_node = child
                break
        if arg_list_node is None:
            return

        if call_name == "Verbs":
            for arg in arg_list_node.children:
                if arg.type == "argument":
                    verb = _extract_verb_arg(arg)
                    if verb:
                        collected_verbs.append(verb)
        elif call_name == "Routes":
            for arg in arg_list_node.children:
                if arg.type == "argument":
                    for child in arg.children:
                        route_str = _try_string_literal(child)
                        if route_str is not None:
                            collected_routes.append(normalize_route("", route_str))
                            break
        else:
            http_method = _FASTENDPOINTS_VERB_MAP.get(call_name)
            if http_method is None:
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
            simple_endpoints.append(HttpEndpointDef(
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

    def _handle_minimal_api_invocation(self, node, results, symbol_map, sorted_symbols):
        """Detect standalone MapGet/MapPost/etc. calls and emit HttpEndpointDef entries.

        Skipped if inside a claimed class (IEndpointGroup/FastEndpoints) to prevent
        double-counting endpoints already handled by those dedicated extractor paths.
        """
        if self._in_claimed_class:
            return

        fn_node = node.child_by_field_name("function")
        if fn_node is None or fn_node.type != "member_access_expression":
            return

        name_node = fn_node.child_by_field_name("name")
        if name_node is None:
            return
        verb_name = node_text(name_node)
        http_method = _MAP_VERB_MAP.get(verb_name)
        if http_method is None:
            return

        arg_list_node = None
        for child in node.children:
            if child.type == "argument_list":
                arg_list_node = child
                break
        if arg_list_node is None:
            return

        args = [c for c in arg_list_node.children if c.type == "argument"]
        if not args:
            return

        first_arg = args[0]
        first_child = _first_non_punctuation_child(first_arg)
        if first_child is None:
            return

        call_line_0 = node.start_point[0]

        if first_child.type in ("string_literal", "verbatim_string_literal"):
            # Route-first: arg[0]=route, arg[1]=handler
            route_str = _try_string_literal(first_child) or ""
            handler_full_name = self._resolve_minimal_api_handler(
                args[1] if len(args) > 1 else None, call_line_0, symbol_map, sorted_symbols,
            )
        elif first_child.type in ("lambda_expression", "parenthesized_lambda_expression"):
            # Lambda in first arg position (unusual) — fall back to enclosing method
            route_str = ""
            handler_full_name = _find_enclosing_symbol(call_line_0, sorted_symbols) or ""
        else:
            # Lambda or other expression in route position — skip
            return

        if not handler_full_name:
            return

        results.append(HttpEndpointDef(
            route=normalize_route("", route_str),
            http_method=http_method,
            handler_full_name=handler_full_name,
            line=call_line_0 + 1,
        ))

    def _resolve_minimal_api_handler(
        self,
        handler_arg,
        call_line_0: int,
        symbol_map: dict,
        sorted_symbols: list[tuple[int, int, str]],
    ) -> str:
        """Resolve a handler argument to a full_name for Minimal API endpoints.

        - Identifier: look up in symbol_map using enclosing class as scope prefix
        - Lambda/other: fall back to the enclosing method's full_name
        """
        if handler_arg is None:
            return _find_enclosing_symbol(call_line_0, sorted_symbols) or ""

        child = _first_non_punctuation_child(handler_arg)
        if child is None:
            return _find_enclosing_symbol(call_line_0, sorted_symbols) or ""

        if child.type == "identifier":
            handler_name = node_text(child)
            enclosing = _find_enclosing_symbol(call_line_0, sorted_symbols)
            # Derive class prefix from enclosing method full_name (everything before last '.')
            class_prefix = enclosing.rsplit(".", 1)[0] if enclosing and "." in enclosing else ""
            resolved = _lookup_handler_full_name(handler_name, class_prefix, symbol_map) if class_prefix else None
            return resolved or enclosing or ""

        # Lambda or other expression — use enclosing method
        return _find_enclosing_symbol(call_line_0, sorted_symbols) or ""

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


def _first_non_punctuation_child(arg_node):
    """Return the first meaningful child of an argument node (skipping punctuation)."""
    _SKIP_TYPES = frozenset({"(", ")", ",", "ref", "out", "in", "named_argument_expression"})
    for child in arg_node.children:
        if child.type not in _SKIP_TYPES:
            return child
    return None


def _lookup_handler_full_name(handler_name: str, class_name: str, symbol_map: dict) -> str | None:
    """Resolve a plain handler identifier to its full_name via symbol_map."""
    for (sym_name, _line), sym in symbol_map.items():
        if sym_name == handler_name and class_name in sym.full_name:
            return sym.full_name
    return None


def _resolve_handler(arg_node, class_name: str, map_full_name: str | None, symbol_map: dict) -> str:
    """Resolve a handler argument node to a full_name.

    For identifier args: look up in symbol_map.
    For lambda args: fall back to the enclosing Map method's full_name.
    """
    if arg_node is None:
        return map_full_name or ""
    child = _first_non_punctuation_child(arg_node)
    if child is None:
        return map_full_name or ""
    if child.type == "identifier":
        handler_name = node_text(child)
        resolved = _lookup_handler_full_name(handler_name, class_name, symbol_map)
        return resolved or map_full_name or ""
    # Lambda or other expression — use Map method's full_name
    return map_full_name or ""


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


_VALID_HTTP_VERBS = frozenset({"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"})


def _extract_verb_arg(arg_node) -> str | None:
    """Extract an HTTP verb string from a Verbs() argument node.

    Handles enum-style (Http.POST → member_access_expression → name field)
    and string-style ("POST" → string_literal → content).
    """
    for child in arg_node.children:
        if child.type == "member_access_expression":
            name_node = child.child_by_field_name("name")
            if name_node and name_node.type == "identifier":
                verb = node_text(name_node).upper()
                if verb in _VALID_HTTP_VERBS:
                    return verb
        text = _try_string_literal(child)
        if text is not None:
            verb = text.upper()
            if verb in _VALID_HTTP_VERBS:
                return verb
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
