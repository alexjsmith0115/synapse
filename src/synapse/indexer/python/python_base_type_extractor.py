from __future__ import annotations

import logging

from tree_sitter import Tree

from synapse.indexer.tree_sitter_util import node_text

log = logging.getLogger(__name__)


class PythonBaseTypeExtractor:
    def __init__(self) -> None:
        pass

    def extract(self, file_path: str, tree: Tree) -> list[tuple[str, str, bool]]:
        """Return (class_name, base_name, is_first) triples for all class definitions found."""
        results: list[tuple[str, str, bool]] = []
        self._walk(tree.root_node, results)
        return results

    def _walk(self, node, results: list[tuple[str, str, bool]]) -> None:
        if node.type == "class_definition":
            self._handle_class_def(node, results)
        for child in node.children:
            self._walk(child, results)

    def _handle_class_def(self, node, results: list[tuple[str, str, bool]]) -> None:
        class_name: str | None = None
        superclasses_node = None

        for child in node.children:
            if child.type == "identifier" and class_name is None:
                class_name = node_text(child)
            elif child.type == "argument_list":
                superclasses_node = child

        if class_name is None or superclasses_node is None:
            return

        base_entries = [
            c for c in superclasses_node.children
            if c.type not in ("(", ")", ",")
        ]

        for idx, entry in enumerate(base_entries):
            base_name = _extract_identifier(entry)
            if base_name:
                results.append((class_name, base_name, idx == 0))


def _extract_identifier(node) -> str | None:
    if node.type == "identifier":
        return node_text(node)
    if node.type == "attribute":
        # Dotted name like `mod.Base` — extract rightmost identifier
        last: str | None = None
        for child in node.children:
            if child.type == "identifier":
                last = node_text(child)
        return last
    return None
