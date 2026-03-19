from __future__ import annotations

import logging

log = logging.getLogger(__name__)

_CLASS_DECL_TYPES = frozenset({
    "class_declaration",
    "abstract_class_declaration",
})


class TypeScriptBaseTypeExtractor:
    def __init__(self) -> None:
        import tree_sitter_typescript
        from tree_sitter import Language, Parser

        self._ts_parser = Parser(Language(tree_sitter_typescript.language_typescript()))
        self._tsx_parser = Parser(Language(tree_sitter_typescript.language_tsx()))

    def extract(self, file_path: str, source: str) -> list[tuple[str, str, bool]]:
        """Return (type_name, base_name, is_first) triples for all extends/implements entries found."""
        if not source.strip():
            return []
        parser = self._tsx_parser if file_path.endswith(".tsx") else self._ts_parser
        try:
            tree = parser.parse(bytes(source, "utf-8"))
        except Exception:
            log.warning("tree-sitter failed to parse %s", file_path)
            return []

        results: list[tuple[str, str, bool]] = []
        self._walk(tree.root_node, results)
        return results

    def _walk(self, node, results: list[tuple[str, str, bool]]) -> None:
        if node.type in _CLASS_DECL_TYPES:
            self._handle_class_decl(node, results)
        elif node.type == "interface_declaration":
            self._handle_interface_decl(node, results)
        for child in node.children:
            self._walk(child, results)

    def _handle_class_decl(self, node, results: list[tuple[str, str, bool]]) -> None:
        class_name: str | None = None
        heritage_node = None

        for child in node.children:
            if child.type == "type_identifier" and class_name is None:
                class_name = _text(child)
            elif child.type == "class_heritage":
                heritage_node = child

        if class_name is None or heritage_node is None:
            return

        for child in heritage_node.children:
            if child.type == "extends_clause":
                base = _extract_extends_target(child)
                if base:
                    # class can only extend one class, so always is_first=True
                    results.append((class_name, base, True))
            elif child.type == "implements_clause":
                bases = _extract_type_list(child)
                for i, base in enumerate(bases):
                    results.append((class_name, base, i == 0))

    def _handle_interface_decl(self, node, results: list[tuple[str, str, bool]]) -> None:
        interface_name: str | None = None

        for child in node.children:
            if child.type == "type_identifier" and interface_name is None:
                interface_name = _text(child)
            elif child.type == "extends_type_clause":
                if interface_name is None:
                    # name not yet seen — scan for it before this child
                    for sibling in node.children:
                        if sibling.type == "type_identifier":
                            interface_name = _text(sibling)
                            break
                if interface_name is None:
                    continue
                bases = _extract_type_list(child)
                for i, base in enumerate(bases):
                    results.append((interface_name, base, i == 0))


def _extract_extends_target(extends_clause_node) -> str | None:
    """Extract the base name from a class extends_clause node.

    In extends_clause, the base is an expression (identifier or member_expression),
    NOT a type — so we look for identifier (bare/generic) or member_expression (qualified).
    """
    for child in extends_clause_node.children:
        if child.type == "identifier":
            # Simple extends (e.g. Animal) or generic extends (e.g. Array, followed by type_arguments)
            return _text(child)
        if child.type == "member_expression":
            # Qualified extends: ns.Base → take property_identifier (rightmost)
            return _rightmost_property(child)
    return None


def _extract_type_list(clause_node) -> list[str]:
    """Extract base names from implements_clause or extends_type_clause nodes.

    Both clause types contain type entries as type_identifier, nested_type_identifier,
    or generic_type children (commas and keywords are skipped).
    """
    bases: list[str] = []
    for child in clause_node.children:
        if child.type == "type_identifier":
            bases.append(_text(child))
        elif child.type == "nested_type_identifier":
            # Qualified: ns.IService → take last type_identifier
            name = _last_type_identifier(child)
            if name:
                bases.append(name)
        elif child.type == "generic_type":
            # Generic: Comparable<string> → take the type_identifier child
            for gchild in child.children:
                if gchild.type == "type_identifier":
                    bases.append(_text(gchild))
                    break
    return bases


def _rightmost_property(member_expression_node) -> str | None:
    """Extract the rightmost name from a member_expression (e.g. ns.Base → Base)."""
    for child in member_expression_node.children:
        if child.type == "property_identifier":
            return _text(child)
    return None


def _last_type_identifier(nested_type_identifier_node) -> str | None:
    """Extract the last type_identifier from a nested_type_identifier node."""
    last: str | None = None
    for child in nested_type_identifier_node.children:
        if child.type == "type_identifier":
            last = _text(child)
    return last


def _text(node) -> str:
    raw = node.text
    return raw.decode("utf-8") if isinstance(raw, bytes) else raw
