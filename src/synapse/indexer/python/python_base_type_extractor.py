from __future__ import annotations

import logging

log = logging.getLogger(__name__)


class PythonBaseTypeExtractor:
    def __init__(self) -> None:
        import tree_sitter_python
        from tree_sitter import Language, Parser

        self._language = Language(tree_sitter_python.language())
        self._parser = Parser(self._language)

    def extract(self, file_path: str, source: str) -> list[tuple[str, str, bool]]:
        """Return (class_name, base_name, is_first) triples for all class definitions found."""
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
        if node.type == "class_definition":
            self._handle_class_def(node, results)
        for child in node.children:
            self._walk(child, results)

    def _handle_class_def(self, node, results: list[tuple[str, str, bool]]) -> None:
        class_name: str | None = None
        superclasses_node = None

        for child in node.children:
            if child.type == "identifier" and class_name is None:
                class_name = child.text.decode("utf-8") if isinstance(child.text, bytes) else child.text
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
        raw = node.text
        return raw.decode("utf-8") if isinstance(raw, bytes) else raw
    if node.type == "attribute":
        # Dotted name like `mod.Base` — extract rightmost identifier
        last: str | None = None
        for child in node.children:
            if child.type == "identifier":
                raw = child.text
                last = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        return last
    return None
