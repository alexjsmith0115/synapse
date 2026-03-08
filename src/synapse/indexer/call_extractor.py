from __future__ import annotations

import logging

log = logging.getLogger(__name__)

_CALLS_QUERY = """
(invocation_expression
    function: [
        (identifier) @name
        (member_access_expression name: (identifier) @name)
    ]
)
(object_creation_expression
    type: [
        (identifier) @name
        (qualified_name name: (identifier) @name)
    ]
)
"""


class TreeSitterCallExtractor:
    """
    Parses a C# source file with tree-sitter and returns all call sites as
    (caller_full_name, callee_simple_name, line_1indexed) tuples.

    caller_full_name is resolved by finding the nearest enclosing method
    start line in symbol_map. Callee resolution to a fully-qualified name
    happens in a later LSP pass (CallIndexer).
    """

    def __init__(self) -> None:
        import tree_sitter_c_sharp
        from tree_sitter import Language, Parser, Query, QueryCursor

        self._language = Language(tree_sitter_c_sharp.language())
        self._parser = Parser(self._language)
        self._query = Query(self._language, _CALLS_QUERY)
        self._QueryCursor = QueryCursor

    def extract(
        self,
        file_path: str,
        source: str,
        symbol_map: dict[tuple[str, int], str],
    ) -> list[tuple[str, str, int, int]]:
        """
        :param file_path: absolute path (used as key prefix in symbol_map).
        :param source: full UTF-8 source text.
        :param symbol_map: maps (file_path, 0-indexed line) -> method full_name.
        :returns: list of (caller_full_name, callee_simple_name, 1-indexed call line, 0-indexed call column).
        """
        if not source.strip():
            return []

        try:
            tree = self._parser.parse(bytes(source, "utf-8"))
        except Exception:
            log.warning("tree-sitter failed to parse %s", file_path)
            return []

        method_lines = sorted(
            (line, full_name)
            for (fp, line), full_name in symbol_map.items()
            if fp == file_path
        )

        results: list[tuple[str, str, int, int]] = []
        seen: set[tuple[str, str, int, int]] = set()

        cursor = self._QueryCursor(self._query)
        for _pattern_idx, captures in cursor.matches(tree.root_node):
            nodes = captures.get("name", [])
            for node in nodes:
                call_line_0 = node.start_point[0]
                call_col_0 = node.start_point[1]
                callee_name = node.text.decode("utf-8") if isinstance(node.text, bytes) else node.text
                caller = self._find_enclosing_method(call_line_0, method_lines)
                if caller is None:
                    continue
                entry = (caller, callee_name, call_line_0 + 1, call_col_0)
                if entry not in seen:
                    seen.add(entry)
                    results.append(entry)

        return results

    def _find_enclosing_method(
        self, line_0: int, method_lines: list[tuple[int, str]]
    ) -> str | None:
        best: str | None = None
        for method_line, full_name in method_lines:
            if method_line <= line_0:
                best = full_name
            else:
                break
        return best
