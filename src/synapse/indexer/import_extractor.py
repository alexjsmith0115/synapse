from __future__ import annotations

import logging

log = logging.getLogger(__name__)


class CSharpImportExtractor:
    """Parses C# source files and returns package names from non-static using directives."""

    def __init__(self) -> None:
        import tree_sitter_c_sharp
        from tree_sitter import Language, Parser

        self._language = Language(tree_sitter_c_sharp.language())
        self._parser = Parser(self._language)

    def extract(self, file_path: str, source: str) -> list[str]:
        """Return deduplicated package names imported by this file."""
        if not source.strip():
            return []
        try:
            tree = self._parser.parse(bytes(source, "utf-8"))
        except Exception:
            log.warning("tree-sitter failed to parse %s", file_path)
            return []

        results: list[str] = []
        seen: set[str] = set()
        self._walk(tree.root_node, results, seen)
        return results

    def _walk(self, node, results: list[str], seen: set[str]) -> None:
        if node.type == "using_directive":
            self._handle_using_directive(node, results, seen)
            return  # using directives don't nest
        for child in node.children:
            self._walk(child, results, seen)

    def _handle_using_directive(self, node, results: list[str], seen: set[str]) -> None:
        child_types = {c.type for c in node.children}
        # Skip: using static ...
        if "static" in child_types:
            return
        # Skip: using Alias = ...  (alias directives have '=' as a child token)
        if "=" in child_types:
            return
        for child in node.children:
            if child.type in ("identifier", "qualified_name"):
                name = child.text.decode("utf-8") if isinstance(child.text, bytes) else child.text
                if name and name not in seen:
                    seen.add(name)
                    results.append(name)
                break
