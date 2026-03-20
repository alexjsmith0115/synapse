from __future__ import annotations

import logging
from pathlib import Path

from synapse.indexer.type_ref import TypeRef

log = logging.getLogger(__name__)

# TypeScript built-in / primitive types that should not produce REFERENCES edges
_TS_PRIMITIVE_TYPES = frozenset({
    "string", "number", "boolean", "void", "any", "unknown",
    "never", "null", "undefined", "bigint", "symbol", "object",
})

# Extensions that require the TSX parser (JSX-aware)
_TSX_EXTENSIONS = frozenset({".tsx", ".jsx"})

# Tree-sitter node types that hold function/method return type annotations
_RETURN_TYPE_PARENTS = frozenset({
    "function_declaration",
    "function_expression",
    "arrow_function",
    "method_definition",
    "generator_function_declaration",
    "generator_function",
})

# Tree-sitter node types that hold parameter type annotations
_PARAM_PARENT_TYPES = frozenset({
    "required_parameter",
    "optional_parameter",
})


class TypeScriptTypeRefExtractor:
    """
    Walks a tree-sitter parse tree for TypeScript/TSX and extracts TypeRef
    instances for parameter, return, field, and property type annotations.

    Uses the same extract() signature as TreeSitterTypeRefExtractor so that
    SymbolResolver can treat C# and TypeScript extractors interchangeably.
    """

    def __init__(self) -> None:
        import tree_sitter_typescript
        from tree_sitter import Language, Parser

        self._ts_parser = Parser(Language(tree_sitter_typescript.language_typescript()))
        self._tsx_parser = Parser(Language(tree_sitter_typescript.language_tsx()))

    def extract(
        self,
        file_path: str,
        source: str,
        symbol_map: dict[tuple[str, int], str],
        class_lines: list[tuple[int, str]] = (),
    ) -> list[TypeRef]:
        if not source.strip():
            return []

        uses_tsx = Path(file_path).suffix in _TSX_EXTENSIONS
        parser = self._tsx_parser if uses_tsx else self._ts_parser

        try:
            tree = parser.parse(bytes(source, "utf-8"))
        except Exception:
            log.warning("tree-sitter failed to parse %s", file_path)
            return []

        method_lines = sorted(
            (line, full_name)
            for (fp, line), full_name in symbol_map.items()
            if fp == file_path
        )

        results: list[TypeRef] = []
        self._walk(tree.root_node, method_lines, list(class_lines), results)
        return results

    # ------------------------------------------------------------------
    # Tree walk
    # ------------------------------------------------------------------

    def _walk(self, node, method_lines, class_lines, results: list[TypeRef]) -> None:
        node_type = node.type

        if node_type in _PARAM_PARENT_TYPES:
            self._handle_parameter(node, method_lines, results)
            # Still recurse — parameters can be nested in other structures

        elif node_type in _RETURN_TYPE_PARENTS:
            self._handle_return_type(node, method_lines, results)

        elif node_type == "public_field_definition":
            self._handle_field(node, class_lines, results)

        elif node_type == "property_signature":
            self._handle_property_sig(node, class_lines, results)

        for child in node.children:
            self._walk(child, method_lines, class_lines, results)

    # ------------------------------------------------------------------
    # Node handlers
    # ------------------------------------------------------------------

    def _handle_parameter(self, node, method_lines, results: list[TypeRef]) -> None:
        type_node = self._child_of_type(node, "type_annotation")
        if type_node is None:
            return
        # type_annotation: first child is ':', second child is the actual type
        actual_type = self._type_annotation_type(type_node)
        if actual_type is None:
            return
        line_0 = actual_type.start_point[0]
        owner = self._find_enclosing_method(line_0, method_lines)
        if owner is None:
            return
        for type_name in self._extract_type_names(actual_type):
            results.append(TypeRef(
                owner_full_name=owner,
                type_name=type_name,
                line=actual_type.start_point[0],
                col=actual_type.start_point[1],
                ref_kind="parameter",
            ))

    def _handle_return_type(self, node, method_lines, results: list[TypeRef]) -> None:
        # return_type is a named field on function/method declarations
        type_annotation = node.child_by_field_name("return_type")
        if type_annotation is None or type_annotation.type != "type_annotation":
            return
        actual_type = self._type_annotation_type(type_annotation)
        if actual_type is None:
            return
        line_0 = actual_type.start_point[0]
        owner = self._find_enclosing_method(line_0, method_lines)
        if owner is None:
            return
        for type_name in self._extract_type_names(actual_type):
            results.append(TypeRef(
                owner_full_name=owner,
                type_name=type_name,
                line=actual_type.start_point[0],
                col=actual_type.start_point[1],
                ref_kind="return_type",
            ))

    def _handle_field(self, node, class_lines, results: list[TypeRef]) -> None:
        type_annotation = self._child_of_type(node, "type_annotation")
        if type_annotation is None:
            return
        actual_type = self._type_annotation_type(type_annotation)
        if actual_type is None:
            return
        line_0 = actual_type.start_point[0]
        owner = self._find_enclosing_class(line_0, class_lines)
        if owner is None:
            return
        for type_name in self._extract_type_names(actual_type):
            results.append(TypeRef(
                owner_full_name=owner,
                type_name=type_name,
                line=actual_type.start_point[0],
                col=actual_type.start_point[1],
                ref_kind="field_type",
            ))

    def _handle_property_sig(self, node, class_lines, results: list[TypeRef]) -> None:
        type_annotation = self._child_of_type(node, "type_annotation")
        if type_annotation is None:
            return
        actual_type = self._type_annotation_type(type_annotation)
        if actual_type is None:
            return
        line_0 = actual_type.start_point[0]
        owner = self._find_enclosing_class(line_0, class_lines)
        if owner is None:
            return
        for type_name in self._extract_type_names(actual_type):
            results.append(TypeRef(
                owner_full_name=owner,
                type_name=type_name,
                line=actual_type.start_point[0],
                col=actual_type.start_point[1],
                ref_kind="property_type",
            ))

    # ------------------------------------------------------------------
    # Type name extraction
    # ------------------------------------------------------------------

    def _extract_type_names(self, node) -> list[str]:
        """
        Recursively extract non-primitive type names from a type node.

        Handles: type_identifier, predefined_type, generic_type, union_type,
        intersection_type, array_type, parenthesized_type.
        """
        node_type = node.type

        if node_type == "type_identifier":
            name = _text(node)
            if name not in _TS_PRIMITIVE_TYPES:
                return [name]
            return []

        if node_type == "predefined_type":
            # Always primitive (string, number, boolean, void, etc.)
            return []

        if node_type == "generic_type":
            # generic_type: type_identifier + type_arguments
            # Extract the outer name AND recurse into type arguments
            names: list[str] = []
            for child in node.children:
                if child.type == "type_identifier":
                    name = _text(child)
                    if name not in _TS_PRIMITIVE_TYPES:
                        names.append(name)
                elif child.type == "type_arguments":
                    for arg in child.children:
                        names.extend(self._extract_type_names(arg))
            return names

        if node_type in ("union_type", "intersection_type"):
            names = []
            for child in node.children:
                names.extend(self._extract_type_names(child))
            return names

        if node_type == "array_type":
            # array_type: first meaningful child is the element type
            for child in node.children:
                if child.type not in ("[", "]"):
                    return self._extract_type_names(child)
            return []

        if node_type == "parenthesized_type":
            for child in node.children:
                if child.type not in ("(", ")"):
                    return self._extract_type_names(child)
            return []

        return []

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _type_annotation_type(type_annotation_node):
        """Return the actual type child of a type_annotation node (skip the ':' token)."""
        for child in type_annotation_node.children:
            if child.type != ":":
                return child
        return None

    @staticmethod
    def _child_of_type(node, child_type: str):
        for child in node.children:
            if child.type == child_type:
                return child
        return None

    @staticmethod
    def _find_enclosing_method(line_0: int, method_lines: list[tuple[int, str]]) -> str | None:
        best: str | None = None
        for method_line, full_name in method_lines:
            if method_line <= line_0:
                best = full_name
            else:
                break
        return best

    @staticmethod
    def _find_enclosing_class(line_0: int, class_lines: list[tuple[int, str]]) -> str | None:
        best: str | None = None
        for class_line, full_name in class_lines:
            if class_line <= line_0:
                best = full_name
            else:
                break
        return best


def _text(node) -> str:
    raw = node.text
    return raw.decode("utf-8") if isinstance(raw, bytes) else raw
