from __future__ import annotations

import logging

from tree_sitter import Tree

from synapse.indexer.tree_sitter_util import find_enclosing_scope, node_text
from synapse.indexer.type_ref import TypeRef

log = logging.getLogger(__name__)

_PYTHON_PRIMITIVE_TYPES = frozenset({
    "int", "float", "str", "bool", "bytes", "None",
    "complex", "bytearray", "memoryview",
    "list", "dict", "set", "tuple", "frozenset",
    "type", "object",
})


class PythonTypeRefExtractor:
    """
    Walks a tree-sitter parse tree for Python and extracts TypeRef instances
    for parameter, return, and class-body variable type annotations.
    """

    def __init__(self) -> None:
        pass

    def extract(
        self,
        file_path: str,
        tree: Tree,
        symbol_map: dict[tuple[str, int], str],
        class_lines: list[tuple[int, str]] = (),
    ) -> list[TypeRef]:
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

        if node_type in ("typed_parameter", "typed_default_parameter"):
            self._handle_parameter(node, method_lines, results)

        elif node_type == "function_definition":
            self._handle_return_type(node, method_lines, results)

        elif node_type == "expression_statement":
            self._handle_class_annotation(node, class_lines, results)

        for child in node.children:
            self._walk(child, method_lines, class_lines, results)

    # ------------------------------------------------------------------
    # Node handlers
    # ------------------------------------------------------------------

    def _handle_parameter(self, node, method_lines, results: list[TypeRef]) -> None:
        type_node = self._child_of_type(node, "type")
        if type_node is None:
            return
        line_0 = type_node.start_point[0]
        owner = find_enclosing_scope(line_0, method_lines)
        if owner is None:
            return
        for type_name in self._extract_type_names(type_node):
            results.append(TypeRef(
                owner_full_name=owner,
                type_name=type_name,
                line=type_node.start_point[0],
                col=type_node.start_point[1],
                ref_kind="parameter",
            ))

    def _handle_return_type(self, node, method_lines, results: list[TypeRef]) -> None:
        return_type = node.child_by_field_name("return_type")
        if return_type is None:
            return
        line_0 = return_type.start_point[0]
        owner = find_enclosing_scope(line_0, method_lines)
        if owner is None:
            return
        for type_name in self._extract_type_names(return_type):
            results.append(TypeRef(
                owner_full_name=owner,
                type_name=type_name,
                line=return_type.start_point[0],
                col=return_type.start_point[1],
                ref_kind="return_type",
            ))

    def _handle_class_annotation(self, node, class_lines, results: list[TypeRef]) -> None:
        # Class-body annotations appear as expression_statement containing
        # an assignment node with a "type" child (annotated assignment)
        child = node.children[0] if node.children else None
        if child is None:
            return
        if child.type != "assignment":
            return
        type_node = self._child_of_type(child, "type")
        if type_node is None:
            return
        line_0 = type_node.start_point[0]
        owner = find_enclosing_scope(line_0, class_lines)
        if owner is None:
            return
        for type_name in self._extract_type_names(type_node):
            results.append(TypeRef(
                owner_full_name=owner,
                type_name=type_name,
                line=type_node.start_point[0],
                col=type_node.start_point[1],
                ref_kind="field_type",
            ))

    # ------------------------------------------------------------------
    # Type name extraction
    # ------------------------------------------------------------------

    def _extract_type_names(self, node) -> list[str]:
        """Recursively extract non-primitive type names from a type annotation node."""
        node_type = node.type

        if node_type == "type":
            # Wrapper node -- recurse into the actual type child
            for child in node.children:
                if child.type != ":":
                    return self._extract_type_names(child)
            return []

        if node_type == "identifier":
            name = node_text(node)
            if name not in _PYTHON_PRIMITIVE_TYPES:
                return [name]
            return []

        if node_type == "generic_type":
            # e.g. list[User] or dict[str, Config]
            # Skip the outer name if primitive, recurse into type_parameter children
            names: list[str] = []
            for child in node.children:
                if child.type == "identifier":
                    name = node_text(child)
                    if name not in _PYTHON_PRIMITIVE_TYPES:
                        names.append(name)
                elif child.type == "type_parameter":
                    for sub in child.children:
                        names.extend(self._extract_type_names(sub))
            return names

        if node_type == "binary_operator":
            # PEP 604 union: X | Y
            names = []
            for child in node.children:
                if child.type != "|":
                    names.extend(self._extract_type_names(child))
            return names

        if node_type == "attribute":
            # typing.Optional etc. -- take last identifier segment
            last_id = None
            for child in node.children:
                if child.type == "identifier":
                    last_id = node_text(child)
            if last_id and last_id not in _PYTHON_PRIMITIVE_TYPES:
                return [last_id]
            return []

        if node_type == "none":
            return []

        if node_type == "subscript":
            # typing.Optional[X] after attribute resolution becomes subscript
            # The first child is the attribute/identifier, rest are slice contents
            names = []
            outer = node.children[0] if node.children else None
            outer_name = None
            if outer is not None:
                if outer.type == "attribute":
                    # e.g. typing.Optional
                    extracted = self._extract_type_names(outer)
                    outer_name = extracted[0] if extracted else None
                elif outer.type == "identifier":
                    outer_name = node_text(outer)

            # If outer is a known primitive/container, skip it; recurse into subscript args
            skip_outer = outer_name in _PYTHON_PRIMITIVE_TYPES or outer_name == "Optional"
            if not skip_outer and outer_name and outer_name not in _PYTHON_PRIMITIVE_TYPES:
                names.append(outer_name)

            # Recurse into subscript arguments (skip brackets and the outer name)
            for child in node.children[1:]:
                if child.type not in ("[", "]", ","):
                    names.extend(self._extract_type_names(child))
            return names

        return []

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _child_of_type(node, child_type: str):
        for child in node.children:
            if child.type == child_type:
                return child
        return None
