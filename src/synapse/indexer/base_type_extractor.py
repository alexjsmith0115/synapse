from __future__ import annotations

import logging

log = logging.getLogger(__name__)

_DECL_TYPES = frozenset({
    "class_declaration",
    "interface_declaration",
    "record_declaration",
    "struct_declaration",
})


class CSharpBaseTypeExtractor:
    def __init__(self) -> None:
        import tree_sitter_c_sharp
        from tree_sitter import Language, Parser

        self._language = Language(tree_sitter_c_sharp.language())
        self._parser = Parser(self._language)

    def extract(self, file_path: str, source: str) -> list[tuple[str, str, bool]]:
        """Return (type_name, base_name, is_first) triples for all base type entries found."""
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
        if node.type in _DECL_TYPES:
            self._handle_decl(node, results)
        for child in node.children:
            self._walk(child, results)

    def _handle_decl(self, node, results: list[tuple[str, str, bool]]) -> None:
        type_name: str | None = None
        base_list_node = None

        for child in node.children:
            if child.type == "identifier" and type_name is None:
                type_name = _text(child)
            elif child.type == "base_list":
                base_list_node = child

        if type_name is None or base_list_node is None:
            return

        base_entries = [
            c for c in base_list_node.children
            if c.type not in (":", ",")
        ]

        for idx, entry in enumerate(base_entries):
            base_name = _extract_base_name(entry)
            if base_name:
                results.append((type_name, base_name, idx == 0))


def _extract_base_name(node) -> str | None:
    if node.type == "identifier":
        return _text(node)
    if node.type == "generic_name":
        # First child is the unqualified identifier before the type argument list
        for child in node.children:
            if child.type == "identifier":
                return _text(child)
    return None


def _text(node) -> str:
    raw = node.text
    return raw.decode("utf-8") if isinstance(raw, bytes) else raw
