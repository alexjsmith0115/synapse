from __future__ import annotations

import logging

from tree_sitter import Tree

from synapse.indexer.tree_sitter_util import node_text

log = logging.getLogger(__name__)

_ABC_NAMES = frozenset({"ABC", "ABCMeta"})
_PROTOCOL_NAMES = frozenset({"Protocol"})


class PythonAttributeExtractor:
    def __init__(self) -> None:
        pass

    def extract(self, file_path: str, tree: Tree) -> list[tuple[str, list[str]]]:
        """Return (symbol_name, [metadata_markers]) pairs for all decorated/async/ABC symbols."""
        results: list[tuple[str, list[str]]] = []
        self._walk(tree.root_node, results)
        return results

    def _walk(self, node, results: list[tuple[str, list[str]]], parent_class: str | None = None) -> None:
        if node.type == "decorated_definition":
            self._handle_decorated(node, results, parent_class)
            # Do NOT recurse further; _handle_decorated processes the inner node
        elif node.type == "class_definition":
            class_name = self._node_name(node)
            self._handle_class(node, [], results)
            # Recurse into class body for nested methods/classes
            for child in node.children:
                if child.type == "block":
                    for block_child in child.children:
                        self._walk(block_child, results, parent_class=class_name)
        elif node.type == "function_definition":
            self._handle_function(node, [], results, parent_class)
        else:
            for child in node.children:
                self._walk(child, results, parent_class)

    def _handle_decorated(self, node, results: list[tuple[str, list[str]]], parent_class: str | None = None) -> None:
        decorators: list[str] = []
        inner = None
        for child in node.children:
            if child.type == "decorator":
                name = self._decorator_name(child)
                if name:
                    decorators.append(name)
            elif child.type == "function_definition":
                inner = child
            elif child.type == "class_definition":
                inner = child

        if inner is None:
            return

        if inner.type == "class_definition":
            class_name = self._node_name(inner)
            self._handle_class(inner, decorators, results)
            # Recurse into class body for nested members
            for child in inner.children:
                if child.type == "block":
                    for block_child in child.children:
                        self._walk(block_child, results, parent_class=class_name)
        else:
            self._handle_function(inner, decorators, results, parent_class)

    def _handle_class(self, node, decorators: list[str], results: list[tuple[str, list[str]]]) -> None:
        name = self._node_name(node)
        if not name:
            return

        markers = list(decorators)

        # Check superclasses for ABC/ABCMeta/Protocol (both direct base and metaclass=ABCMeta syntax)
        for child in node.children:
            if child.type == "argument_list":
                for arg in child.children:
                    if arg.type == "keyword_argument":
                        # metaclass=ABCMeta pattern
                        for kw_child in arg.children:
                            if kw_child.type == "identifier" and node_text(kw_child) in _ABC_NAMES:
                                markers.append("ABC")
                                break
                    else:
                        text = node_text(arg)
                        if text in _ABC_NAMES:
                            markers.append("ABC")
                        elif text in _PROTOCOL_NAMES:
                            markers.append("Protocol")

        if markers:
            results.append((name, markers))

    def _handle_function(self, node, decorators: list[str], results: list[tuple[str, list[str]]], parent_class: str | None = None) -> None:
        name = self._node_name(node)
        if not name:
            return

        markers = list(decorators)

        # In tree-sitter-python, `async def` produces a function_definition node
        # whose first non-whitespace child is an `async` token.
        for child in node.children:
            if child.type == "async":
                markers.append("async")
                break

        if markers:
            qualified = f"{parent_class}.{name}" if parent_class else name
            results.append((qualified, markers))

    def _decorator_name(self, decorator_node) -> str | None:
        """Extract the simple name from a decorator node."""
        for child in decorator_node.children:
            if child.type == "identifier":
                return node_text(child)
            if child.type == "attribute":
                # dotted.name — return last segment
                for attr_child in reversed(child.children):
                    if attr_child.type == "identifier":
                        return node_text(attr_child)
            if child.type == "call":
                # @decorator() — recurse into the function part
                for call_child in child.children:
                    if call_child.type == "identifier":
                        return node_text(call_child)
                    if call_child.type == "attribute":
                        for attr_child in reversed(call_child.children):
                            if attr_child.type == "identifier":
                                return node_text(attr_child)
        return None

    def _node_name(self, node) -> str | None:
        for child in node.children:
            if child.type == "identifier":
                return node_text(child)
        return None
