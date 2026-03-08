from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

# C# built-in type keywords that should not produce REFERENCES edges
_PRIMITIVE_TYPES = frozenset({
    "bool", "byte", "sbyte", "char", "decimal", "double", "float",
    "int", "uint", "long", "ulong", "short", "ushort", "string",
    "object", "void", "nint", "nuint", "dynamic", "var",
})

_RETURN_TYPE_QUERY = """
(method_declaration returns: (_) @return_type name: (identifier) @method_name)
"""

_PARAM_QUERY = """
(parameter type: (_) @param_type)
"""

_PROPERTY_QUERY = """
(property_declaration type: (_) @prop_type name: (identifier) @prop_name)
"""

_FIELD_QUERY = """
(field_declaration (variable_declaration type: (_) @field_type))
"""


@dataclass
class TypeRef:
    owner_full_name: str
    type_name: str
    line: int
    col: int
    ref_kind: str  # "parameter", "return_type", "property_type", "field_type"


class TreeSitterTypeRefExtractor:
    def __init__(self) -> None:
        import tree_sitter_c_sharp
        from tree_sitter import Language, Parser, Query, QueryCursor

        self._language = Language(tree_sitter_c_sharp.language())
        self._parser = Parser(self._language)
        self._return_query = Query(self._language, _RETURN_TYPE_QUERY)
        self._param_query = Query(self._language, _PARAM_QUERY)
        self._property_query = Query(self._language, _PROPERTY_QUERY)
        self._field_query = Query(self._language, _FIELD_QUERY)
        self._QueryCursor = QueryCursor

    def extract(
        self,
        file_path: str,
        source: str,
        symbol_map: dict[tuple[str, int], str],
    ) -> list[TypeRef]:
        if not source.strip():
            return []

        try:
            tree = self._parser.parse(bytes(source, "utf-8"))
        except Exception:
            log.warning("tree-sitter failed to parse %s", file_path)
            return []

        method_lines = sorted(
            (line, full_name)
            for (fp, line), full_name in symbol_map.items()
            if fp == file_path
        )

        results: list[TypeRef] = []
        self._extract_return_types(tree, file_path, method_lines, results)
        self._extract_param_types(tree, file_path, method_lines, results)
        self._extract_property_types(tree, file_path, source, results)
        self._extract_field_types(tree, file_path, source, results)
        return results

    def _extract_return_types(self, tree, file_path, method_lines, results):
        cursor = self._QueryCursor(self._return_query)
        for _pattern_idx, captures in cursor.matches(tree.root_node):
            type_nodes = captures.get("return_type", [])
            for node in type_nodes:
                type_name = self._get_type_name(node)
                if type_name and type_name not in _PRIMITIVE_TYPES:
                    line_0 = node.start_point[0]
                    owner = self._find_enclosing_method(line_0, method_lines)
                    if owner:
                        results.append(TypeRef(
                            owner_full_name=owner, type_name=type_name,
                            line=node.start_point[0], col=node.start_point[1],
                            ref_kind="return_type",
                        ))

    def _extract_param_types(self, tree, file_path, method_lines, results):
        cursor = self._QueryCursor(self._param_query)
        for _pattern_idx, captures in cursor.matches(tree.root_node):
            type_nodes = captures.get("param_type", [])
            for node in type_nodes:
                type_name = self._get_type_name(node)
                if type_name and type_name not in _PRIMITIVE_TYPES:
                    line_0 = node.start_point[0]
                    owner = self._find_enclosing_method(line_0, method_lines)
                    if owner:
                        results.append(TypeRef(
                            owner_full_name=owner, type_name=type_name,
                            line=node.start_point[0], col=node.start_point[1],
                            ref_kind="parameter",
                        ))

    def _extract_property_types(self, tree, file_path, source, results):
        cursor = self._QueryCursor(self._property_query)
        for _pattern_idx, captures in cursor.matches(tree.root_node):
            type_nodes = captures.get("prop_type", [])
            name_nodes = captures.get("prop_name", [])
            for type_node, name_node in zip(type_nodes, name_nodes):
                type_name = self._get_type_name(type_node)
                prop_name = name_node.text.decode("utf-8") if isinstance(name_node.text, bytes) else name_node.text
                if type_name and type_name not in _PRIMITIVE_TYPES:
                    results.append(TypeRef(
                        owner_full_name=prop_name,  # Placeholder — resolved by SymbolResolver
                        type_name=type_name,
                        line=type_node.start_point[0], col=type_node.start_point[1],
                        ref_kind="property_type",
                    ))

    def _extract_field_types(self, tree, file_path, source, results):
        cursor = self._QueryCursor(self._field_query)
        for _pattern_idx, captures in cursor.matches(tree.root_node):
            type_nodes = captures.get("field_type", [])
            for node in type_nodes:
                type_name = self._get_type_name(node)
                if type_name and type_name not in _PRIMITIVE_TYPES:
                    results.append(TypeRef(
                        owner_full_name="",  # Placeholder — resolved by SymbolResolver
                        type_name=type_name,
                        line=node.start_point[0], col=node.start_point[1],
                        ref_kind="field_type",
                    ))

    def _get_type_name(self, node) -> str | None:
        """Extract the simple type name from a type node, handling generic and qualified types."""
        text = node.text.decode("utf-8") if isinstance(node.text, bytes) else node.text
        if not text:
            return None
        # For nullable types like Foo?, extract Foo
        # For arrays like Foo[], extract Foo
        text = text.rstrip("?").rstrip("[]")
        # Strip generic wrapper — we care about the inner type for now
        if "<" in text:
            inner = text[text.index("<") + 1:text.rindex(">")]
            return inner.strip().split(",")[0].strip() if inner else None
        # For qualified names like Ns.Foo, take the last part
        if "." in text:
            return text.rsplit(".", 1)[-1]
        return text

    def _find_enclosing_method(self, line_0: int, method_lines: list[tuple[int, str]]) -> str | None:
        best: str | None = None
        for method_line, full_name in method_lines:
            if method_line <= line_0:
                best = full_name
            else:
                break
        return best
