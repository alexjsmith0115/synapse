from __future__ import annotations

import logging

from tree_sitter import Tree

from synapps.indexer.tree_sitter_util import node_text

log = logging.getLogger(__name__)

_CLASS_DECL_TYPES = frozenset({
    "class_declaration",
    "abstract_class_declaration",
})


class TypeScriptBaseTypeExtractor:
    def __init__(self) -> None:
        pass

    def extract(self, file_path: str, tree: Tree) -> list[tuple[str, str, bool, int, int]]:
        """Return (type_name, base_name, is_first, line, col) 5-tuples for all extends/implements entries found."""
        results: list[tuple[str, str, bool, int, int]] = []
        self._walk(tree.root_node, results)
        return results

    def _walk(self, node, results: list[tuple[str, str, bool, int, int]]) -> None:
        stack = [node]
        while stack:
            current = stack.pop()
            if current.type in _CLASS_DECL_TYPES:
                self._handle_class_decl(current, results)
            elif current.type == "interface_declaration":
                self._handle_interface_decl(current, results)
            stack.extend(current.children)

    def _handle_class_decl(self, node, results: list[tuple[str, str, bool, int, int]]) -> None:
        class_name: str | None = None
        heritage_node = None

        for child in node.children:
            if child.type == "type_identifier" and class_name is None:
                class_name = node_text(child)
            elif child.type == "class_heritage":
                heritage_node = child

        if class_name is None or heritage_node is None:
            return

        for child in heritage_node.children:
            if child.type == "extends_clause":
                base_info = _extract_extends_target(child)
                if base_info:
                    name, line, col = base_info
                    # class can only extend one class, so always is_first=True
                    results.append((class_name, name, True, line, col))
            elif child.type == "implements_clause":
                bases = _extract_type_list(child)
                for i, (name, line, col) in enumerate(bases):
                    results.append((class_name, name, i == 0, line, col))

    def _handle_interface_decl(self, node, results: list[tuple[str, str, bool, int, int]]) -> None:
        interface_name: str | None = None

        for child in node.children:
            if child.type == "type_identifier" and interface_name is None:
                interface_name = node_text(child)
            elif child.type == "extends_type_clause":
                if interface_name is None:
                    # name not yet seen — scan for it before this child
                    for sibling in node.children:
                        if sibling.type == "type_identifier":
                            interface_name = node_text(sibling)
                            break
                if interface_name is None:
                    continue
                bases = _extract_type_list(child)
                for i, (name, line, col) in enumerate(bases):
                    results.append((interface_name, name, i == 0, line, col))


def _extract_extends_target(extends_clause_node) -> tuple[str, int, int] | None:
    """Extract the base name and position from a class extends_clause node.

    In extends_clause, the base is an expression (identifier or member_expression),
    NOT a type — so we look for identifier (bare/generic) or member_expression (qualified).
    """
    for child in extends_clause_node.children:
        if child.type == "identifier":
            # Simple extends (e.g. Animal) or generic extends (e.g. Array, followed by type_arguments)
            return (node_text(child), child.start_point[0], child.start_point[1])
        if child.type == "member_expression":
            # Qualified extends: ns.Base → take property_identifier (rightmost)
            return _rightmost_property(child)
    return None


def _extract_type_list(clause_node) -> list[tuple[str, int, int]]:
    """Extract base names and positions from implements_clause or extends_type_clause nodes.

    Both clause types contain type entries as type_identifier, nested_type_identifier,
    or generic_type children (commas and keywords are skipped).
    """
    bases: list[tuple[str, int, int]] = []
    for child in clause_node.children:
        if child.type == "type_identifier":
            bases.append((node_text(child), child.start_point[0], child.start_point[1]))
        elif child.type == "nested_type_identifier":
            # Qualified: ns.IService → take last type_identifier
            info = _last_type_identifier(child)
            if info:
                bases.append(info)
        elif child.type == "generic_type":
            # Generic: Comparable<string> → take the type_identifier child
            for gchild in child.children:
                if gchild.type == "type_identifier":
                    bases.append((node_text(gchild), gchild.start_point[0], gchild.start_point[1]))
                    break
    return bases


def _rightmost_property(member_expression_node) -> tuple[str, int, int] | None:
    """Extract the rightmost name and position from a member_expression (e.g. ns.Base → Base)."""
    for child in member_expression_node.children:
        if child.type == "property_identifier":
            return (node_text(child), child.start_point[0], child.start_point[1])
    return None


def _last_type_identifier(nested_type_identifier_node) -> tuple[str, int, int] | None:
    """Extract the last type_identifier and its position from a nested_type_identifier node."""
    last_node = None
    for child in nested_type_identifier_node.children:
        if child.type == "type_identifier":
            last_node = child
    if last_node is not None:
        return (node_text(last_node), last_node.start_point[0], last_node.start_point[1])
    return None
