from __future__ import annotations

import logging
from collections.abc import Callable

from tree_sitter import Tree

from synapse.indexer.tree_sitter_util import find_enclosing_scope, node_text

log = logging.getLogger(__name__)

_PYTHON_CALLS_QUERY = """
(call
  function: [
    (identifier) @name
    (attribute attribute: (identifier) @name)
  ]
)
"""

# tree-sitter node types that introduce a new scope enclosing a call
_FUNCTION_SCOPE_TYPES = {"function_definition", "async_function_definition", "lambda"}
_CLASS_SCOPE_TYPES = {"class_definition"}


class PythonCallExtractor:
    """
    Parses a Python source file with tree-sitter and returns call sites as
    (caller_full_name, callee_simple_name, line_1indexed, col_0indexed) tuples.

    Scope classification uses tree-sitter parent traversal instead of line-range
    lookups, which correctly handles nested classes and functions and skips
    class-body assignments.
    """

    def __init__(
        self,
        module_name_resolver: Callable[[str], str | None] | None = None,
    ) -> None:
        import tree_sitter_python
        from tree_sitter import Language, Query, QueryCursor

        self._module_name_resolver = module_name_resolver
        self._language = Language(tree_sitter_python.language())
        self._query = Query(self._language, _PYTHON_CALLS_QUERY)
        self._QueryCursor = QueryCursor
        self._sites_seen: int = 0

    def extract(
        self,
        file_path: str,
        tree: "Tree",
        symbol_map: dict[tuple[str, int], str],
    ) -> list[tuple[str, str, int, int]]:
        """
        :param file_path: absolute path (used as key prefix in symbol_map).
        :param tree: pre-parsed tree-sitter Tree.
        :param symbol_map: maps (file_path, 0-indexed line) -> method full_name.
        :returns: list of (caller_full_name, callee_simple_name, 1-indexed call line, 0-indexed call column).
        """
        self._sites_seen = 0

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
                callee_name = node_text(node)

                scope_type, scope_func_line = self._get_call_scope(node)

                if scope_type == "class":
                    continue

                if scope_type == "function":
                    caller = find_enclosing_scope(call_line_0, method_lines)
                    if caller is None:
                        continue
                else:
                    # module scope
                    if self._module_name_resolver is None:
                        continue
                    caller = self._module_name_resolver(file_path)
                    if caller is None:
                        continue

                self._sites_seen += 1

                entry = (caller, callee_name, call_line_0 + 1, call_col_0)
                if entry not in seen:
                    seen.add(entry)
                    results.append(entry)

        return results

    def _get_call_scope(self, node) -> tuple[str, int | None]:
        """
        Walk the parent chain to determine what scope this call node lives in.

        Returns ('function', start_line_0) if inside a function/method/lambda,
        ('class', None) if directly inside a class body (no function in between),
        ('module', None) if at module top level.
        """
        parent = node.parent
        while parent is not None:
            node_type = parent.type
            if node_type in _FUNCTION_SCOPE_TYPES:
                start_line = parent.start_point[0]
                return ("function", start_line)
            if node_type in _CLASS_SCOPE_TYPES:
                return ("class", None)
            parent = parent.parent
        return ("module", None)

