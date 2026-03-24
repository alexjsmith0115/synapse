from __future__ import annotations

import logging
import re

from tree_sitter import Tree

from synapse.indexer.http.interface import HttpEndpointDef, HttpExtractionResult
from synapse.indexer.http.route_utils import normalize_route
from synapse.indexer.tree_sitter_util import node_text
from synapse.lsp.interface import IndexSymbol

log = logging.getLogger(__name__)

_HTTP_VERB_MAP: dict[str, str] = {
    "HttpGet": "GET",
    "HttpPost": "POST",
    "HttpPut": "PUT",
    "HttpDelete": "DELETE",
    "HttpPatch": "PATCH",
}

_CONTROLLER_ATTRS = frozenset({"ApiController"})


class CSharpHttpExtractor:
    """Extract HTTP endpoint definitions from ASP.NET Core controllers."""

    def extract(
        self,
        file_path: str,
        tree: Tree,
        symbols: list[IndexSymbol],
    ) -> HttpExtractionResult:
        symbol_by_name_line: dict[tuple[str, int], IndexSymbol] = {}
        for sym in symbols:
            symbol_by_name_line[(sym.name, sym.line)] = sym

        endpoint_defs: list[HttpEndpointDef] = []
        self._walk(tree.root_node, endpoint_defs, symbol_by_name_line)
        return HttpExtractionResult(endpoint_defs=endpoint_defs)

    def _walk(self, node, results, symbol_map):
        if node.type == "class_declaration":
            self._handle_class(node, results, symbol_map)
        for child in node.children:
            self._walk(child, results, symbol_map)

    def _handle_class(self, node, results, symbol_map):
        attrs = _collect_attrs_with_args(node)
        attr_names = {name for name, _ in attrs}
        if not (_CONTROLLER_ATTRS & attr_names):
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
