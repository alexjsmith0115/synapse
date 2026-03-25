from __future__ import annotations

import logging
import re

from tree_sitter import Tree

from synapse.indexer.http.interface import HttpClientCall, HttpEndpointDef, HttpExtractionResult
from synapse.indexer.tree_sitter_util import node_text
from synapse.lsp.interface import IndexSymbol

log = logging.getLogger(__name__)

# HTTP verb names shared by FastAPI, Flask 2.0+ shorthand, and requests
_FASTAPI_FLASK_VERBS = frozenset({"get", "post", "put", "delete", "patch"})

# Django REST ViewSet base classes that imply conventional CRUD routes
_VIEWSET_BASES = frozenset({"ModelViewSet", "ViewSet", "ReadOnlyModelViewSet", "GenericViewSet"})

# Django REST APIView base classes whose HTTP methods are mapped 1:1 to routes
_APIVIEW_BASES = frozenset({"APIView", "GenericAPIView"})

# Conventional CRUD routes emitted for ViewSet subclasses; keyed by method name
_VIEWSET_ROUTE_MAP = {
    "list": ("GET", "/{name}"),
    "create": ("POST", "/{name}"),
    "retrieve": ("GET", "/{name}/{id}"),
    "update": ("PUT", "/{name}/{id}"),
    "partial_update": ("PATCH", "/{name}/{id}"),
    "destroy": ("DELETE", "/{name}/{id}"),
}

# HTTP verbs recognised in APIView method definitions
_APIVIEW_HTTP_VERBS = frozenset({"get", "post", "put", "delete", "patch"})

# Normalise Flask route param syntax: <int:name> or <name> -> {name}
_FLASK_PARAM_RE = re.compile(r"<(?:\w+:)?(\w+)>")


def _normalise_flask_route(route: str) -> str:
    return _FLASK_PARAM_RE.sub(r"{\1}", route)


def _class_base_name(name: str) -> str:
    """Derive the conventional route prefix from a ViewSet/View class name."""
    for suffix in ("ViewSet", "View"):
        if name.endswith(suffix) and len(name) > len(suffix):
            return name[: -len(suffix)].lower()
    return name.lower()


class PythonHttpExtractor:
    """Extract HTTP endpoint definitions and client calls from Python source files.

    Server-side: FastAPI, Flask (@app.route, @app.get, …), Django REST Framework (ViewSet, APIView, @api_view).
    Client-side: requests library (requests.get, requests.post, …).
    """

    def extract(
        self,
        file_path: str,
        tree: Tree,
        symbols: list[IndexSymbol],
    ) -> HttpExtractionResult:
        # (name, line) -> symbol — used to resolve handler full names
        symbol_by_name_line: dict[tuple[str, int], IndexSymbol] = {}
        for sym in symbols:
            symbol_by_name_line[(sym.name, sym.line)] = sym

        # Sorted (start_0, end_0, full_name) — used for enclosing-scope lookup
        sorted_symbols: list[tuple[int, int, str]] = sorted(
            [
                (s.line - 1, s.end_line - 1 if s.end_line else s.line - 1, s.full_name)
                for s in symbols
            ],
            key=lambda t: t[0],
        )

        # Collect module-level string constants for identifier URL resolution
        constants: dict[str, str] = _collect_string_constants(tree.root_node)

        endpoint_defs: list[HttpEndpointDef] = []
        client_calls: list[HttpClientCall] = []
        self._walk(tree.root_node, endpoint_defs, client_calls, symbol_by_name_line, sorted_symbols, constants)
        return HttpExtractionResult(endpoint_defs=endpoint_defs, client_calls=client_calls)

    def _walk(self, node, endpoint_defs, client_calls, symbol_map, sorted_symbols, constants):
        if node.type == "decorated_definition":
            self._handle_decorated_definition(node, endpoint_defs, symbol_map)
        elif node.type == "class_definition":
            self._handle_class_definition(node, endpoint_defs, symbol_map)
        elif node.type == "call":
            self._handle_call(node, client_calls, sorted_symbols, constants)

        for child in node.children:
            self._walk(child, endpoint_defs, client_calls, symbol_map, sorted_symbols, constants)

    # ─────────────────────────────────────────
    # Server-side: decorator-based endpoints
    # ─────────────────────────────────────────

    def _handle_decorated_definition(self, node, endpoint_defs, symbol_map):
        """Handle @app.get/post/… and @app.route and @api_view decorators."""
        for child in node.children:
            if child.type == "decorator":
                self._process_decorator(child, node, endpoint_defs, symbol_map)

    def _process_decorator(self, decorator_node, definition_node, endpoint_defs, symbol_map):
        # The decorator may be `@name`, `@obj.attr`, or `@obj.attr(args)`
        # Find the inner `call` node (if any) or attribute/identifier
        call_node = None
        for child in decorator_node.children:
            if child.type == "call":
                call_node = child
                break

        if call_node is None:
            return

        # Determine decorator type: attribute call like app.get(…) / api_view(…)
        fn_node = call_node.child_by_field_name("function")
        if fn_node is None:
            return

        if fn_node.type == "attribute":
            attr_name = _attribute_last_identifier(fn_node)
            if attr_name is None:
                return

            if attr_name in _FASTAPI_FLASK_VERBS:
                self._extract_verb_endpoint(attr_name, call_node, definition_node, endpoint_defs, symbol_map)
            elif attr_name == "route":
                self._extract_flask_route(call_node, definition_node, endpoint_defs, symbol_map)

        elif fn_node.type == "identifier" and node_text(fn_node) == "api_view":
            self._extract_api_view_endpoint(call_node, definition_node, endpoint_defs, symbol_map)

    def _extract_verb_endpoint(self, verb: str, call_node, definition_node, endpoint_defs, symbol_map):
        """@app.get('/route') or @router.post('/route') style."""
        route = _extract_first_string_arg(call_node)
        if route is None:
            return
        route = _normalise_flask_route(route)

        handler_sym = _resolve_handler_symbol(definition_node, symbol_map)
        if handler_sym is None:
            return

        endpoint_defs.append(HttpEndpointDef(
            route=route,
            http_method=verb.upper(),
            handler_full_name=handler_sym.full_name,
            line=definition_node.start_point[0] + 1,
        ))

    def _extract_flask_route(self, call_node, definition_node, endpoint_defs, symbol_map):
        """@app.route('/route', methods=['GET', 'POST']) style."""
        route = _extract_first_string_arg(call_node)
        if route is None:
            return
        route = _normalise_flask_route(route)

        methods = _extract_methods_kwarg(call_node)
        if not methods:
            # Flask defaults to GET when methods= is absent
            methods = ["GET"]

        handler_sym = _resolve_handler_symbol(definition_node, symbol_map)
        if handler_sym is None:
            return

        for method in methods:
            endpoint_defs.append(HttpEndpointDef(
                route=route,
                http_method=method.upper(),
                handler_full_name=handler_sym.full_name,
                line=definition_node.start_point[0] + 1,
            ))

    def _extract_api_view_endpoint(self, call_node, definition_node, endpoint_defs, symbol_map):
        """@api_view(['GET']) decorator on a function."""
        methods = _extract_list_strings(call_node)

        handler_sym = _resolve_handler_symbol(definition_node, symbol_map)
        if handler_sym is None:
            return

        fn_line = definition_node.start_point[0] + 1

        # Derive route from function name
        fn_name = _get_function_name(definition_node)
        route = f"/{fn_name}" if fn_name else "/"

        for method in methods:
            endpoint_defs.append(HttpEndpointDef(
                route=route,
                http_method=method.upper(),
                handler_full_name=handler_sym.full_name,
                line=fn_line,
            ))

    # ─────────────────────────────────────────
    # Server-side: Django REST class-based views
    # ─────────────────────────────────────────

    def _handle_class_definition(self, node, endpoint_defs, symbol_map):
        """Handle Django REST ViewSet and APIView subclasses."""
        class_name = _get_class_name(node)
        if class_name is None:
            return

        base_names = _get_base_class_names(node)
        if not base_names:
            return

        route_prefix = f"/{_class_base_name(class_name)}"
        class_line = node.start_point[0] + 1

        if _VIEWSET_BASES & set(base_names):
            self._emit_viewset_routes(node, route_prefix, class_line, endpoint_defs, symbol_map)
        elif _APIVIEW_BASES & set(base_names):
            self._emit_apiview_routes(node, route_prefix, class_line, endpoint_defs, symbol_map)

    def _emit_viewset_routes(self, class_node, route_prefix, class_line, endpoint_defs, symbol_map):
        """Emit conventional CRUD routes for ViewSet subclasses.

        Only emits routes for methods actually defined in the class body.
        """
        defined_methods = _collect_class_method_names(class_node)
        class_name = _get_class_name(class_node) or ""

        for method_name, (http_method, route_template) in _VIEWSET_ROUTE_MAP.items():
            if method_name not in defined_methods:
                continue

            route = route_template.replace("/{name}", route_prefix)

            # Try to resolve the handler symbol for the method
            method_sym = _find_method_symbol(class_name, method_name, symbol_map)
            handler_full_name = method_sym.full_name if method_sym else class_name

            endpoint_defs.append(HttpEndpointDef(
                route=route,
                http_method=http_method,
                handler_full_name=handler_full_name,
                line=class_line,
            ))

    def _emit_apiview_routes(self, class_node, route_prefix, class_line, endpoint_defs, symbol_map):
        """Emit routes for each HTTP verb method defined in an APIView subclass."""
        class_name = _get_class_name(class_node) or ""

        body = class_node.child_by_field_name("body")
        if body is None:
            return

        for child in body.children:
            if child.type not in ("function_definition", "async_function_definition", "decorated_definition"):
                continue

            fn_node = child
            if fn_node.type == "decorated_definition":
                # Navigate to the inner function
                for sub in fn_node.children:
                    if sub.type in ("function_definition", "async_function_definition"):
                        fn_node = sub
                        break

            fn_name = _get_function_name(fn_node)
            if fn_name is None or fn_name not in _APIVIEW_HTTP_VERBS:
                continue

            method_sym = _find_method_symbol(class_name, fn_name, symbol_map)
            handler_full_name = method_sym.full_name if method_sym else class_name

            endpoint_defs.append(HttpEndpointDef(
                route=route_prefix,
                http_method=fn_name.upper(),
                handler_full_name=handler_full_name,
                line=fn_node.start_point[0] + 1,
            ))

    # ─────────────────────────────────────────
    # Client-side: requests calls
    # ─────────────────────────────────────────

    def _handle_call(self, node, client_calls, sorted_symbols, constants):
        fn_node = node.child_by_field_name("function")
        if fn_node is None or fn_node.type != "attribute":
            return

        obj_node = fn_node.child_by_field_name("object")
        attr_node = fn_node.child_by_field_name("attribute")
        if obj_node is None or attr_node is None:
            return

        obj_name = node_text(obj_node)
        method_name = node_text(attr_node)

        if obj_name != "requests" or method_name not in _FASTAPI_FLASK_VERBS:
            return

        args_node = node.child_by_field_name("arguments")
        if args_node is None:
            return

        url_node = _first_arg_node(args_node)
        if url_node is None:
            return

        route = _resolve_url(url_node, constants)
        if route is None or "/" not in route:
            return

        call_line_0 = node.start_point[0]
        call_col_0 = node.start_point[1]

        caller = _find_enclosing_symbol(call_line_0, sorted_symbols)
        if caller is None:
            return

        client_calls.append(HttpClientCall(
            route=route,
            http_method=method_name.upper(),
            caller_full_name=caller,
            line=call_line_0 + 1,
            col=call_col_0,
        ))


# ─────────────────────────────────────────
# Tree-sitter node helpers
# ─────────────────────────────────────────


def _attribute_last_identifier(attr_node) -> str | None:
    """Return the attribute name (last identifier) from an attribute node."""
    attr = attr_node.child_by_field_name("attribute")
    if attr is not None:
        return node_text(attr)
    return None


def _extract_first_string_arg(call_node) -> str | None:
    """Return the string value of the first positional argument of a call node."""
    args_node = call_node.child_by_field_name("arguments")
    if args_node is None:
        return None
    node = _first_arg_node(args_node)
    if node is None:
        return None
    return _extract_string_value(node)


def _first_arg_node(args_node):
    """Return first non-punctuation, non-keyword child of an argument_list."""
    for child in args_node.children:
        if child.type in ("(", ")", ","):
            continue
        if child.type == "keyword_argument":
            continue
        return child
    return None


def _extract_string_value(node) -> str | None:
    """Extract text from a Python string node (handles quoted strings)."""
    if node.type == "string":
        for child in node.children:
            if child.type == "string_content":
                return node_text(child)
        # Empty string
        return ""
    raw = node_text(node)
    # Handles 'text' or "text"
    if len(raw) >= 2 and raw[0] in ('"', "'") and raw[-1] == raw[0]:
        return raw[1:-1]
    return None


def _extract_methods_kwarg(call_node) -> list[str]:
    """Extract the methods list from Flask @app.route(..., methods=['GET', 'POST'])."""
    args_node = call_node.child_by_field_name("arguments")
    if args_node is None:
        return []
    for child in args_node.children:
        if child.type == "keyword_argument":
            key_node = child.child_by_field_name("name")
            val_node = child.child_by_field_name("value")
            if key_node is None or val_node is None:
                continue
            if node_text(key_node) == "methods":
                return _extract_list_strings_from_node(val_node)
    return []


def _extract_list_strings(call_node) -> list[str]:
    """Extract string values from the first list argument of a call node."""
    args_node = call_node.child_by_field_name("arguments")
    if args_node is None:
        return []
    node = _first_arg_node(args_node)
    if node is None:
        return []
    return _extract_list_strings_from_node(node)


def _extract_list_strings_from_node(node) -> list[str]:
    """Collect all string literals from a list node."""
    result: list[str] = []
    if node.type in ("list", "tuple"):
        for child in node.children:
            if child.type == "string":
                val = _extract_string_value(child)
                if val:
                    result.append(val)
    return result


def _resolve_handler_symbol(definition_node, symbol_map: dict[tuple[str, int], IndexSymbol]) -> IndexSymbol | None:
    """Resolve the IndexSymbol for the function/class defined in definition_node."""
    # Navigate past the decorated_definition to find the actual function/class
    fn_node = definition_node
    for child in definition_node.children:
        if child.type in ("function_definition", "async_function_definition", "class_definition"):
            fn_node = child
            break

    fn_name = _get_function_name(fn_node)
    if fn_name is None:
        return None

    fn_line = fn_node.start_point[0] + 1
    sym = symbol_map.get((fn_name, fn_line))
    if sym is not None:
        return sym

    # Fallback: match by name only
    for (name, _), s in symbol_map.items():
        if name == fn_name:
            return s
    return None


def _get_function_name(node) -> str | None:
    """Return the name identifier of a function_definition or async_function_definition node."""
    name_node = node.child_by_field_name("name")
    if name_node is not None:
        return node_text(name_node)
    return None


def _get_class_name(node) -> str | None:
    """Return the name identifier of a class_definition node."""
    name_node = node.child_by_field_name("name")
    if name_node is not None:
        return node_text(name_node)
    return None


def _get_base_class_names(class_node) -> list[str]:
    """Return the list of base class names from a class_definition node."""
    args_node = class_node.child_by_field_name("superclasses")
    if args_node is None:
        return []
    names: list[str] = []
    for child in args_node.children:
        if child.type == "identifier":
            names.append(node_text(child))
        elif child.type == "attribute":
            # e.g. rest_framework.views.APIView
            attr = child.child_by_field_name("attribute")
            if attr is not None:
                names.append(node_text(attr))
    return names


def _collect_class_method_names(class_node) -> set[str]:
    """Return the set of method names defined directly in a class body."""
    body = class_node.child_by_field_name("body")
    if body is None:
        return set()
    names: set[str] = set()
    for child in body.children:
        fn = child
        if fn.type == "decorated_definition":
            for sub in fn.children:
                if sub.type in ("function_definition", "async_function_definition"):
                    fn = sub
                    break
        if fn.type in ("function_definition", "async_function_definition"):
            fn_name = _get_function_name(fn)
            if fn_name:
                names.add(fn_name)
    return names


def _find_method_symbol(class_name: str, method_name: str, symbol_map: dict[tuple[str, int], IndexSymbol]) -> IndexSymbol | None:
    """Find a method symbol by matching the combination of class and method name in full_name."""
    for sym in symbol_map.values():
        if sym.name == method_name and class_name in sym.full_name:
            return sym
    return None


# ─────────────────────────────────────────
# URL resolution helpers (for requests calls)
# ─────────────────────────────────────────


def _resolve_url(node, constants: dict[str, str]) -> str | None:
    """Resolve a URL from a call argument node.

    Handles: string literals, f-strings, identifiers (constant lookup).
    """
    if node.type == "string":
        # Detect f-strings by checking for interpolation children
        has_interpolation = any(c.type == "interpolation" for c in node.children)
        if has_interpolation:
            return _extract_fstring_value(node)
        return _extract_string_value(node)

    if node.type == "concatenated_string":
        return _resolve_concatenated_string(node, constants)

    if node.type == "identifier":
        return constants.get(node_text(node))

    return None


def _resolve_concatenated_string(node, constants: dict[str, str]) -> str | None:
    """Resolve a Python f-string or concatenated string to a route pattern."""
    parts: list[str] = []
    for child in node.children:
        if child.type == "string":
            val = _extract_fstring_value(child)
            if val is None:
                return None
            parts.append(val)
        elif child.type == "concatenated_string":
            sub = _resolve_concatenated_string(child, constants)
            if sub is None:
                return None
            parts.append(sub)
    return "".join(parts) if parts else None


def _extract_fstring_value(string_node) -> str | None:
    """Extract route string from a Python string node, including f-strings.

    F-string interpolations are replaced with {expr} placeholders.
    """
    parts: list[str] = []
    is_fstring = False
    for child in string_node.children:
        if child.type == "string_start":
            text = node_text(child)
            if "f" in text.lower():
                is_fstring = True
        elif child.type == "string_content":
            parts.append(node_text(child))
        elif child.type == "interpolation":
            # Extract the expression text inside { ... }
            expr_parts: list[str] = []
            for sub in child.children:
                if sub.type not in ("{", "}"):
                    expr_parts.append(node_text(sub))
            parts.append("{" + "".join(expr_parts) + "}")
        elif child.type == "string_end":
            pass
    if parts:
        return "".join(parts)
    # Plain string fallback
    return _extract_string_value(string_node)


def _collect_string_constants(root_node) -> dict[str, str]:
    """Collect module-level string assignments for identifier URL resolution."""
    constants: dict[str, str] = {}
    for child in root_node.children:
        if child.type == "expression_statement":
            for sub in child.children:
                if sub.type == "assignment":
                    _collect_assignment(sub, constants)
    return constants


def _collect_assignment(node, constants: dict[str, str]) -> None:
    """Extract a name = "string" assignment into constants dict."""
    left = node.child_by_field_name("left")
    right = node.child_by_field_name("right")
    if left is None or right is None:
        return
    if left.type != "identifier":
        return
    val = _extract_string_value(right)
    if val is not None:
        constants[node_text(left)] = val


def _find_enclosing_symbol(call_line_0: int, sorted_symbols: list[tuple[int, int, str]]) -> str | None:
    """Return the full_name of the innermost symbol whose range contains call_line_0."""
    best: str | None = None
    for start_0, end_0, full_name in sorted_symbols:
        if start_0 <= call_line_0 <= end_0:
            best = full_name
        elif start_0 > call_line_0:
            break
    return best
