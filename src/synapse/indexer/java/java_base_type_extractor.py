from __future__ import annotations

import logging

from synapse.indexer.tree_sitter_util import node_text

log = logging.getLogger(__name__)


class JavaBaseTypeExtractor:
    """
    Parses a Java source file with tree-sitter and returns inheritance
    relationships as (class_name, base_name, is_first_base) tuples per D-18.

    Handles:
    - class extends (single class inheritance)
    - class implements (multiple interface implementation)
    - interface extends (interface extending interfaces)

    is_first_base=True for:
    - the extends target (always)
    - the first implements/extends-interface entry
    """

    def __init__(self) -> None:
        import tree_sitter_java as ts_java
        from tree_sitter import Language, Parser

        self._language = Language(ts_java.language())
        self._parser = Parser(self._language)

    def extract(self, file_path: str, source: str) -> list[tuple[str, str, bool]]:
        """Return (type_name, base_name, is_first_base) triples."""
        if not source.strip():
            return []
        try:
            tree = self._parser.parse(bytes(source, "utf-8"))
        except Exception:
            log.warning("tree-sitter failed to parse %s", file_path)
            return []

        results: list[tuple[str, str, bool]] = []
        self._walk(tree.root_node, results)
        return results

    def _walk(self, node, results: list[tuple[str, str, bool]]) -> None:
        if node.type == "class_declaration":
            self._handle_class_decl(node, results)
        elif node.type == "interface_declaration":
            self._handle_interface_decl(node, results)
        for child in node.children:
            self._walk(child, results)

    def _handle_class_decl(
        self, node, results: list[tuple[str, str, bool]]
    ) -> None:
        class_name: str | None = None
        superclass_name: str | None = None
        implements_names: list[str] = []

        for child in node.children:
            if child.type == "identifier" and class_name is None:
                class_name = node_text(child)
            elif child.type == "superclass":
                superclass_name = _extract_superclass(child)
            elif child.type == "super_interfaces":
                implements_names = _extract_type_list(child)

        if class_name is None:
            return

        if superclass_name:
            results.append((class_name, superclass_name, True))

        for i, iface in enumerate(implements_names):
            results.append((class_name, iface, i == 0))

    def _handle_interface_decl(
        self, node, results: list[tuple[str, str, bool]]
    ) -> None:
        iface_name: str | None = None
        extends_names: list[str] = []

        for child in node.children:
            if child.type == "identifier" and iface_name is None:
                iface_name = node_text(child)
            elif child.type == "extends_interfaces":
                extends_names = _extract_type_list(child)

        if iface_name is None:
            return

        for i, base in enumerate(extends_names):
            results.append((iface_name, base, i == 0))


def _extract_superclass(superclass_node) -> str | None:
    """Extract the base class name from a superclass node (extends clause)."""
    for child in superclass_node.children:
        if child.type == "type_identifier":
            return node_text(child)
        if child.type == "generic_type":
            # Generic superclass like Comparable<String>
            for gchild in child.children:
                if gchild.type == "type_identifier":
                    return node_text(gchild)
        if child.type == "scoped_type_identifier":
            return _last_type_identifier(child)
    return None


def _extract_type_list(clause_node) -> list[str]:
    """Extract type names from super_interfaces or extends_interfaces nodes.

    These contain a type_list child with type_identifier entries.
    """
    names: list[str] = []
    for child in clause_node.children:
        if child.type == "type_list":
            for entry in child.children:
                if entry.type == "type_identifier":
                    names.append(node_text(entry))
                elif entry.type == "generic_type":
                    for gchild in entry.children:
                        if gchild.type == "type_identifier":
                            names.append(node_text(gchild))
                            break
                elif entry.type == "scoped_type_identifier":
                    name = _last_type_identifier(entry)
                    if name:
                        names.append(name)
    return names


def _last_type_identifier(scoped_type_node) -> str | None:
    """Extract the last type_identifier from a scoped_type_identifier (e.g. pkg.Type)."""
    last: str | None = None
    for child in scoped_type_node.children:
        if child.type == "type_identifier":
            last = node_text(child)
    return last
