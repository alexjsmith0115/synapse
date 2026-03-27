from __future__ import annotations

import logging

from tree_sitter import Tree

from synapse.indexer.tree_sitter_util import node_text

log = logging.getLogger(__name__)

_DECL_TYPES = frozenset({
    "class_declaration",
    "interface_declaration",
    "record_declaration",
    "struct_declaration",
    "method_declaration",
    "constructor_declaration",
    "property_declaration",
    "field_declaration",
    "enum_declaration",
})

# C# keyword modifiers we extract as metadata markers for set_metadata_flags
_MODIFIER_KEYWORDS = frozenset({
    "abstract", "static", "async", "virtual", "override", "sealed", "readonly",
})


class CSharpAttributeExtractor:
    def __init__(self) -> None:
        pass

    def extract(self, file_path: str, tree: Tree) -> list[tuple[str, list[str]]]:
        """Return (symbol_name, [attribute_names]) pairs for all attributed symbols."""
        results: list[tuple[str, list[str]]] = []
        self._walk(tree.root_node, results)
        return results

    def _walk(self, node, results: list[tuple[str, list[str]]]) -> None:
        if node.type in _DECL_TYPES:
            self._handle_decl(node, results)
        for child in node.children:
            self._walk(child, results)

    def _handle_decl(self, node, results: list[tuple[str, list[str]]]) -> None:
        attrs = self._collect_attributes(node)
        modifiers = self._collect_modifiers(node)
        markers = attrs + modifiers
        if not markers:
            return
        name = self._extract_name(node)
        if name:
            results.append((name, markers))

    def _collect_modifiers(self, node) -> list[str]:
        """Extract keyword modifiers (static, abstract, async, etc.) from a declaration node."""
        modifiers: list[str] = []
        for child in node.children:
            if child.type == "modifier":
                text = node_text(child).strip()
                if text in _MODIFIER_KEYWORDS:
                    modifiers.append(text)
        return modifiers

    def _collect_attributes(self, node) -> list[str]:
        attrs: list[str] = []
        for child in node.children:
            if child.type == "attribute_list":
                for attr_child in child.children:
                    if attr_child.type == "attribute":
                        name = self._extract_attribute_name(attr_child)
                        if name:
                            attrs.append(_normalize_attr_name(name))
        return attrs

    def _extract_attribute_name(self, attr_node) -> str | None:
        for child in attr_node.children:
            if child.type == "identifier":
                return node_text(child)
            if child.type == "qualified_name":
                return _extract_qualified_name(child)
        return None

    def _extract_name(self, node) -> str | None:
        if node.type == "field_declaration":
            for child in node.children:
                if child.type == "variable_declaration":
                    for vc in child.children:
                        if vc.type == "variable_declarator":
                            for id_node in vc.children:
                                if id_node.type == "identifier":
                                    return node_text(id_node)
            return None
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


def _extract_qualified_name(node) -> str:
    parts: list[str] = []
    for child in node.children:
        if child.type == "identifier":
            parts.append(node_text(child))
        elif child.type == "qualified_name":
            parts.append(_extract_qualified_name(child))
    return ".".join(parts)


