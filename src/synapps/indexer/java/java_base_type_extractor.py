from __future__ import annotations

import logging

from tree_sitter import Tree

from synapps.indexer.tree_sitter_util import node_text

log = logging.getLogger(__name__)


class JavaBaseTypeExtractor:
    """
    Parses a Java source file with tree-sitter and returns inheritance
    relationships as (class_name, base_name, is_first_base, line, col) 5-tuples per D-18.

    Handles:
    - class extends (single class inheritance)
    - class implements (multiple interface implementation)
    - interface extends (interface extending interfaces)

    is_first_base=True for:
    - the extends target (always)
    - the first implements/extends-interface entry
    """

    def __init__(self) -> None:
        pass

    def extract(self, file_path: str, tree: Tree) -> list[tuple[str, str, bool, int, int]]:
        """Return (type_name, base_name, is_first_base, line, col) 5-tuples."""
        results: list[tuple[str, str, bool, int, int]] = []
        self._walk(tree.root_node, results)
        return results

    def _walk(self, node, results: list[tuple[str, str, bool, int, int]]) -> None:
        if node.type == "class_declaration":
            self._handle_class_decl(node, results)
        elif node.type == "interface_declaration":
            self._handle_interface_decl(node, results)
        for child in node.children:
            self._walk(child, results)

    def _handle_class_decl(
        self, node, results: list[tuple[str, str, bool, int, int]]
    ) -> None:
        class_name: str | None = None
        superclass_data: tuple[str, int, int] | None = None
        implements_data: list[tuple[str, int, int]] = []

        for child in node.children:
            if child.type == "identifier" and class_name is None:
                class_name = node_text(child)
            elif child.type == "superclass":
                superclass_data = _extract_superclass(child)
            elif child.type == "super_interfaces":
                implements_data = _extract_type_list(child)

        if class_name is None:
            return

        if superclass_data:
            name, line, col = superclass_data
            results.append((class_name, name, True, line, col))

        for i, (name, line, col) in enumerate(implements_data):
            results.append((class_name, name, i == 0, line, col))

    def _handle_interface_decl(
        self, node, results: list[tuple[str, str, bool, int, int]]
    ) -> None:
        iface_name: str | None = None
        extends_data: list[tuple[str, int, int]] = []

        for child in node.children:
            if child.type == "identifier" and iface_name is None:
                iface_name = node_text(child)
            elif child.type == "extends_interfaces":
                extends_data = _extract_type_list(child)

        if iface_name is None:
            return

        for i, (name, line, col) in enumerate(extends_data):
            results.append((iface_name, name, i == 0, line, col))


def _extract_superclass(superclass_node) -> tuple[str, int, int] | None:
    """Extract the base class name and position from a superclass node (extends clause)."""
    for child in superclass_node.children:
        if child.type == "type_identifier":
            return (node_text(child), child.start_point[0], child.start_point[1])
        if child.type == "generic_type":
            # Generic superclass like Comparable<String>
            for gchild in child.children:
                if gchild.type == "type_identifier":
                    return (node_text(gchild), gchild.start_point[0], gchild.start_point[1])
        if child.type == "scoped_type_identifier":
            return _last_type_identifier(child)
    return None


def _extract_type_list(clause_node) -> list[tuple[str, int, int]]:
    """Extract type names and positions from super_interfaces or extends_interfaces nodes.

    These contain a type_list child with type_identifier entries.
    """
    names: list[tuple[str, int, int]] = []
    for child in clause_node.children:
        if child.type == "type_list":
            for entry in child.children:
                if entry.type == "type_identifier":
                    names.append((node_text(entry), entry.start_point[0], entry.start_point[1]))
                elif entry.type == "generic_type":
                    for gchild in entry.children:
                        if gchild.type == "type_identifier":
                            names.append((node_text(gchild), gchild.start_point[0], gchild.start_point[1]))
                            break
                elif entry.type == "scoped_type_identifier":
                    info = _last_type_identifier(entry)
                    if info:
                        names.append(info)
    return names


def _last_type_identifier(scoped_type_node) -> tuple[str, int, int] | None:
    """Extract the last type_identifier and its position from a scoped_type_identifier (e.g. pkg.Type)."""
    last_node = None
    for child in scoped_type_node.children:
        if child.type == "type_identifier":
            last_node = child
    if last_node is not None:
        return (node_text(last_node), last_node.start_point[0], last_node.start_point[1])
    return None
