from __future__ import annotations

import logging

from synapse.indexer.tree_sitter_util import node_text

log = logging.getLogger(__name__)


class JavaImportExtractor:
    """
    Parses a Java source file with tree-sitter and returns fully qualified
    import paths as list[str] per D-06.

    Handles single imports (java.util.List), wildcard imports (java.util.*),
    and static imports (static java.lang.Math.PI).
    """

    def __init__(self, source_root: str = "") -> None:
        import tree_sitter_java as ts_java
        from tree_sitter import Language, Parser

        self._language = Language(ts_java.language())
        self._parser = Parser(self._language)
        self._source_root = source_root

    def extract(self, file_path: str, source: str) -> list[str]:
        """Return deduplicated fully qualified import paths from this file."""
        if not source.strip():
            return []
        try:
            tree = self._parser.parse(bytes(source, "utf-8"))
        except Exception:
            log.warning("tree-sitter failed to parse %s", file_path)
            return []

        results: list[str] = []
        seen: set[str] = set()

        for child in tree.root_node.children:
            if child.type == "import_declaration":
                self._handle_import(child, results, seen)

        return results

    def _handle_import(
        self, node, results: list[str], seen: set[str]
    ) -> None:
        # Collect scoped_identifier text and check for wildcard
        scoped_id = None
        has_asterisk = False

        for child in node.children:
            if child.type == "scoped_identifier":
                scoped_id = node_text(child)
            elif child.type == "asterisk":
                has_asterisk = True

        if scoped_id is None:
            return

        if has_asterisk:
            import_path = f"{scoped_id}.*"
        else:
            import_path = scoped_id

        if import_path not in seen:
            seen.add(import_path)
            results.append(import_path)
