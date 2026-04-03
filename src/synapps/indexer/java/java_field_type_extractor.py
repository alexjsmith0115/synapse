from __future__ import annotations

import logging

from tree_sitter import Tree

from synapps.indexer.tree_sitter_util import node_text

log = logging.getLogger(__name__)

# Primitives to skip — consistent with JavaTypeRefExtractor._PRIMITIVE_TYPES
_PRIMITIVE_TYPES = frozenset({
    "int", "long", "short", "byte", "float", "double", "boolean", "char", "void",
})


class JavaFieldTypeExtractor:
    """Extract (field_simple_name, type_simple_name) pairs from Java field declarations.

    Used to populate Field.type_name in the graph before REFERENCES edges are written.
    Skips primitive types. Handles generics (List<T> -> "List"), arrays (T[] -> "T"),
    and multiple variable declarators on a single field_declaration.
    """

    def extract(self, file_path: str, tree: Tree) -> list[tuple[str, str]]:
        """Return (field_simple_name, type_simple_name) pairs for all non-primitive fields."""
        results: list[tuple[str, str]] = []
        self._walk(tree.root_node, results)
        return results

    def _walk(self, node, results: list[tuple[str, str]]) -> None:
        if node.type == "field_declaration":
            self._handle_field(node, results)
            return  # don't recurse into field_declaration children
        for child in node.children:
            if child.type in ("class_body", "interface_body", "enum_body"):
                for body_child in child.children:
                    self._walk(body_child, results)
            elif child.type != "field_declaration":
                self._walk(child, results)

    def _handle_field(self, node, results: list[tuple[str, str]]) -> None:
        type_name = self._extract_type_name(node)
        if not type_name:
            return
        field_names = self._extract_field_names(node)
        for field_name in field_names:
            results.append((field_name, type_name))

    def _extract_type_name(self, node) -> str | None:
        """Return simple type name from a field_declaration node."""
        for child in node.children:
            if child.type == "type_identifier":
                name = node_text(child)
                return name if name not in _PRIMITIVE_TYPES else None
            elif child.type == "generic_type":
                # List<Order> -> "List"
                for gc in child.children:
                    if gc.type == "type_identifier":
                        name = node_text(gc)
                        return name if name not in _PRIMITIVE_TYPES else None
            elif child.type == "array_type":
                # Animal[] -> "Animal"
                for ac in child.children:
                    if ac.type == "type_identifier":
                        name = node_text(ac)
                        return name if name not in _PRIMITIVE_TYPES else None
                    elif ac.type == "generic_type":
                        for gc in ac.children:
                            if gc.type == "type_identifier":
                                name = node_text(gc)
                                return name if name not in _PRIMITIVE_TYPES else None
        return None

    def _extract_field_names(self, node) -> list[str]:
        """Return all variable names declared on a field_declaration (handles a, b multi-decl)."""
        names: list[str] = []
        for child in node.children:
            if child.type == "variable_declarator":
                for vc in child.children:
                    if vc.type == "identifier":
                        names.append(node_text(vc))
                        break
        return names
