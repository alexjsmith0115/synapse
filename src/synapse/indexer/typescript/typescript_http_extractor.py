from __future__ import annotations

import logging
import re

from tree_sitter import Tree

from synapse.indexer.http.interface import HttpClientCall, HttpEndpointDef, HttpExtractionResult
from synapse.indexer.tree_sitter_util import node_text
from synapse.lsp.interface import IndexSymbol

log = logging.getLogger(__name__)

_HTTP_VERB_METHODS = frozenset({"get", "post", "put", "delete", "patch"})

_METHOD_MAP = {
    "get": "GET",
    "post": "POST",
    "put": "PUT",
    "delete": "DELETE",
    "patch": "PATCH",
}

# Converts Express :param syntax to {param} format
_EXPRESS_PARAM_RE = re.compile(r":(\w+)")


class TypeScriptHttpExtractor:
    """Extract HTTP server routes and client calls from TypeScript/JavaScript source files.

    Server-side (SERVES): Express/Fastify/Hono route registrations.
    Client-side (HTTP_CALLS): api.get(...), fetch(...), axios.post(...), etc.
    """

    def extract(
        self,
        file_path: str,
        tree: Tree,
        symbols: list[IndexSymbol],
    ) -> HttpExtractionResult:
        # Collect file-local string constants for Tier 2 resolution
        constants = _collect_string_constants(tree.root_node)

        # Build sorted (start_0, end_0, full_name) list for enclosing scope lookup
        sorted_symbols = sorted(
            [
                (s.line - 1, s.end_line - 1 if s.end_line else s.line - 1, s.full_name)
                for s in symbols
            ],
            key=lambda t: t[0],
        )

        endpoint_defs: list[HttpEndpointDef] = []
        client_calls: list[HttpClientCall] = []
        _walk(tree.root_node, constants, sorted_symbols, endpoint_defs, client_calls)
        return HttpExtractionResult(endpoint_defs=endpoint_defs, client_calls=client_calls)


def _walk(
    node,
    constants: dict[str, str],
    sorted_symbols,
    endpoint_defs: list[HttpEndpointDef],
    client_calls: list[HttpClientCall],
) -> None:
    if node.type == "call_expression":
        _handle_call_expression(node, constants, sorted_symbols, endpoint_defs, client_calls)
    for child in node.children:
        _walk(child, constants, sorted_symbols, endpoint_defs, client_calls)


def _handle_call_expression(
    node,
    constants: dict[str, str],
    sorted_symbols,
    endpoint_defs: list[HttpEndpointDef],
    client_calls: list[HttpClientCall],
) -> None:
    fn_node = node.child_by_field_name("function")
    if fn_node is None:
        return

    # Unwrap await_expression — tree-sitter wraps `await` inside the call
    # when generics are present: `await api.post<T>(...)` parses as
    # call_expression(function=await_expression(member_expression), ...)
    if fn_node.type == "await_expression":
        for child in fn_node.children:
            if child.type == "member_expression":
                fn_node = child
                break

    http_method: str | None = None

    if fn_node.type == "member_expression":
        prop = fn_node.child_by_field_name("property")
        if prop is None:
            return
        method_name = node_text(prop)

        # Handle Fastify .route({ method, url, handler }) config object pattern
        if method_name == "route":
            args_node = node.child_by_field_name("arguments")
            if args_node is not None:
                _handle_fastify_route_config(node, args_node, sorted_symbols, endpoint_defs)
            return

        if method_name not in _HTTP_VERB_METHODS:
            return
        http_method = _METHOD_MAP[method_name]
    elif fn_node.type == "identifier" and node_text(fn_node) == "fetch":
        # Pattern: fetch(url) or fetch(url, { method: 'POST' })
        http_method = _extract_fetch_method(node)
    else:
        return

    args_node = node.child_by_field_name("arguments")
    if args_node is None:
        return

    positional = [c for c in args_node.children if c.type not in (",", "(", ")")]

    # First positional argument is the URL
    if not positional:
        return
    url_node = positional[0]

    route = _resolve_url(url_node, constants)
    if route is None or "/" not in route:
        # Not a URL path — reject to avoid false positives like map.get('some-key')
        return

    call_line_0 = node.start_point[0]
    caller = _find_enclosing_symbol(call_line_0, sorted_symbols)
    if caller is None:
        return

    # Server route: second arg is a function/arrow_function -> SERVES
    if len(positional) >= 2 and _is_handler_arg(positional[1]):
        normalized_route = _EXPRESS_PARAM_RE.sub(r"{\1}", route)
        endpoint_defs.append(HttpEndpointDef(
            route=normalized_route,
            http_method=http_method,
            handler_full_name=caller,
            line=call_line_0 + 1,
        ))
        return

    # Client call -> HTTP_CALLS
    call_col_0 = node.start_point[1]
    client_calls.append(HttpClientCall(
        route=route,
        http_method=http_method,
        caller_full_name=caller,
        line=call_line_0 + 1,
        col=call_col_0,
    ))


def _is_handler_arg(node) -> bool:
    """Return True if the node is a function literal (arrow or named), indicating a server route handler."""
    return node.type in ("arrow_function", "function_expression", "function")


def _handle_fastify_route_config(
    call_node,
    args_node,
    sorted_symbols,
    endpoint_defs: list[HttpEndpointDef],
) -> None:
    """Handle fastify.route({ method: 'POST', url: '/items', handler: fn }) pattern."""
    positional = [c for c in args_node.children if c.type not in (",", "(", ")")]
    if not positional or positional[0].type != "object":
        return

    obj_node = positional[0]
    method_val: str | None = None
    url_val: str | None = None

    for pair in obj_node.children:
        if pair.type != "pair":
            continue
        key_node = pair.child_by_field_name("key")
        val_node = pair.child_by_field_name("value")
        if key_node is None or val_node is None:
            continue
        key = node_text(key_node).strip("\"'")
        if key == "method":
            raw = _extract_string_value(val_node)
            if raw:
                method_val = raw.upper()
        elif key == "url":
            url_val = _extract_string_value(val_node)

    if method_val is None or url_val is None or "/" not in url_val:
        return

    call_line_0 = call_node.start_point[0]
    caller = _find_enclosing_symbol(call_line_0, sorted_symbols)
    if caller is None:
        return

    normalized_route = _EXPRESS_PARAM_RE.sub(r"{\1}", url_val)
    endpoint_defs.append(HttpEndpointDef(
        route=normalized_route,
        http_method=method_val,
        handler_full_name=caller,
        line=call_line_0 + 1,
    ))


def _extract_fetch_method(call_node) -> str:
    """Extract HTTP method from fetch(url, { method: 'DELETE' }) options or default to GET."""
    args_node = call_node.child_by_field_name("arguments")
    if args_node is None:
        return "GET"

    # Second argument is the options object
    positional = [c for c in args_node.children if c.type not in (",", "(", ")")]
    if len(positional) < 2:
        return "GET"

    options_node = positional[1]
    if options_node.type != "object":
        return "GET"

    for pair in options_node.children:
        if pair.type != "pair":
            continue
        key_node = pair.child_by_field_name("key")
        val_node = pair.child_by_field_name("value")
        if key_node is None or val_node is None:
            continue
        key = node_text(key_node).strip('"\'')
        if key != "method":
            continue
        method_text = _extract_string_value(val_node)
        if method_text:
            return method_text.upper()

    return "GET"


def _resolve_url(node, constants: dict[str, str]) -> str | None:
    """Three-tier URL resolution.

    Tier 1: string literal → extract directly.
    Tier 1: template literal → replace ${expr} with {expr}.
    Tier 2: identifier → look up in file-local constants map.
    Tier 3: binary expression (concatenation) → resolve parts.
    Returns None if the URL cannot be statically resolved.
    """
    if node.type == "string":
        return _extract_string_value(node)

    if node.type == "template_string":
        return _extract_template_string(node)

    if node.type == "identifier":
        name = node_text(node)
        return constants.get(name)

    if node.type == "binary_expression":
        return _resolve_binary_expression(node, constants)

    return None


def _extract_string_value(node) -> str | None:
    """Extract the inner text of a string node (strips surrounding quotes)."""
    if node.type == "string":
        for child in node.children:
            if child.type == "string_fragment":
                return node_text(child)
        # Empty string literal
        return ""
    # Single-quoted string handled as raw text
    raw = node_text(node)
    if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
        return raw[1:-1]
    return None


def _extract_template_string(node) -> str:
    """Convert a template_string node to a route string, replacing ${expr} with {expr}."""
    parts: list[str] = []
    for child in node.children:
        if child.type == "string_fragment":
            parts.append(node_text(child))
        elif child.type == "template_substitution":
            # Extract the expression text from inside ${ ... }
            expr_parts = [node_text(c) for c in child.children if c.type not in ("${", "}")]
            parts.append("{" + "".join(expr_parts) + "}")
    return "".join(parts)


def _resolve_binary_expression(node, constants: dict[str, str]) -> str | None:
    """Resolve a string concatenation expression, using {param} for dynamic parts."""
    left = node.child_by_field_name("left")
    right = node.child_by_field_name("right")
    if left is None or right is None:
        return None

    left_val = _resolve_url(left, constants)
    right_val = _resolve_url(right, constants)

    # At least one side must resolve to something useful
    if left_val is None and right_val is None:
        return None

    left_str = left_val if left_val is not None else "{param}"
    right_str = right_val if right_val is not None else "{param}"
    return left_str + right_str


def _collect_string_constants(root_node) -> dict[str, str]:
    """Walk top-level variable declarations and collect const string assignments.

    Builds a map of identifier name → string value for Tier 2 resolution.
    """
    constants: dict[str, str] = {}
    _collect_constants_walk(root_node, constants, depth=0)
    return constants


def _collect_constants_walk(node, constants: dict[str, str], depth: int) -> None:
    # Only scan top-level declarations (depth 0 = program, depth 1 = direct children)
    if node.type in ("lexical_declaration", "variable_declaration"):
        for child in node.children:
            if child.type == "variable_declarator":
                name_node = child.child_by_field_name("name")
                val_node = child.child_by_field_name("value")
                if name_node is None or val_node is None:
                    continue
                if name_node.type != "identifier":
                    continue
                val = _extract_string_value(val_node)
                if val is not None:
                    constants[node_text(name_node)] = val
        return

    if depth <= 1:
        for child in node.children:
            _collect_constants_walk(child, constants, depth + 1)


def _find_enclosing_symbol(call_line_0: int, sorted_symbols: list[tuple[int, int, str]]) -> str | None:
    """Return the full_name of the innermost symbol whose line range contains call_line_0."""
    best: str | None = None
    for start_0, end_0, full_name in sorted_symbols:
        if start_0 <= call_line_0 <= end_0:
            best = full_name
        elif start_0 > call_line_0:
            break
    return best
