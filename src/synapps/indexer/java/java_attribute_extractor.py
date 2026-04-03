from __future__ import annotations

import logging

from tree_sitter import Tree

from synapps.indexer.tree_sitter_util import node_text

log = logging.getLogger(__name__)

# Java declaration node types that can carry annotations/modifiers
_DECLARATION_TYPES = frozenset({
    "class_declaration",
    "interface_declaration",
    "enum_declaration",
    "method_declaration",
    "field_declaration",
    "constructor_declaration",
})

# Modifier keywords we extract as attribute markers (D-19)
_MODIFIER_KEYWORDS = frozenset({
    "abstract", "static", "final", "synchronized", "native",
})


class JavaAttributeExtractor:
    """Extract annotations and modifier keywords from Java declarations.

    Returns (symbol_name, [attribute_strings]) tuples where attribute_strings
    are lowercase annotation/modifier names per D-19.
    """

    def __init__(self) -> None:
        pass

    def extract(self, file_path: str, tree: Tree) -> list[tuple[str, list[str]]]:
        """Return (symbol_name, [metadata_markers]) for annotated/modified declarations."""
        results: list[tuple[str, list[str]]] = []
        self._walk(tree.root_node, results)
        return results

    def _walk(self, node, results: list[tuple[str, list[str]]]) -> None:
        if node.type in _DECLARATION_TYPES:
            self._handle_declaration(node, results)
            # Recurse into class/interface/enum body for nested declarations
            for child in node.children:
                if child.type in ("class_body", "interface_body", "enum_body"):
                    for body_child in child.children:
                        self._walk(body_child, results)
            return

        for child in node.children:
            self._walk(child, results)

    def _handle_declaration(self, node, results: list[tuple[str, list[str]]]) -> None:
        name = self._declaration_name(node)
        if not name:
            return

        markers: list[str] = []

        # Collect annotations and modifiers from the modifiers node
        for child in node.children:
            if child.type == "modifiers":
                self._collect_modifiers(child, markers)
                break

        if markers:
            results.append((name, markers))

    def _collect_modifiers(self, modifiers_node, markers: list[str]) -> None:
        """Extract annotation names and modifier keywords from a modifiers node."""
        for child in modifiers_node.children:
            if child.type == "marker_annotation":
                # @Override, @Deprecated, @FunctionalInterface
                name = self._annotation_name(child)
                if name:
                    markers.append(name.lower())

            elif child.type == "annotation":
                # @SuppressWarnings("unchecked")
                name = self._annotation_name(child)
                if name:
                    markers.append(name.lower())

            elif child.type in _MODIFIER_KEYWORDS:
                markers.append(child.type)

    def _annotation_name(self, annotation_node) -> str | None:
        """Extract the simple name from an annotation or marker_annotation node."""
        for child in annotation_node.children:
            if child.type == "identifier":
                return node_text(child)
            if child.type == "scoped_identifier":
                # e.g. @com.foo.Override -> take last identifier
                for sub in reversed(child.children):
                    if sub.type == "identifier":
                        return node_text(sub)
        return None

    def _declaration_name(self, node) -> str | None:
        """Extract the simple name from a declaration node."""
        if node.type == "field_declaration":
            # Field name lives inside variable_declarator, not as a direct identifier child
            for child in node.children:
                if child.type == "variable_declarator":
                    for vc in child.children:
                        if vc.type == "identifier":
                            return node_text(vc)
            return None
        for child in node.children:
            if child.type == "identifier":
                return node_text(child)
        return None
