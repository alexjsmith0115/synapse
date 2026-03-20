from __future__ import annotations

import logging
from collections.abc import Callable

log = logging.getLogger(__name__)

_TS_CALLS_QUERY = """
(call_expression
  function: [
    (identifier) @name
    (member_expression property: (property_identifier) @name)
  ]
)
(new_expression
  constructor: (identifier) @name
)
"""

# tree-sitter node types that introduce a new function scope
_FUNCTION_SCOPE_TYPES = frozenset({
    "function_declaration",
    "function_expression",
    "arrow_function",
    "method_definition",
    "generator_function_declaration",
    "generator_function",
})

# tree-sitter node types that indicate a class-body field definition (not a function scope)
_CLASS_BODY_DIRECT_TYPES = frozenset({
    "public_field_definition",
    "field_definition",
})

# file extensions that require the TSX parser (JSX-aware)
_TSX_EXTENSIONS = frozenset({".tsx", ".jsx"})


class TypeScriptCallExtractor:
    """
    Parses a TypeScript/JavaScript source file with tree-sitter and returns call
    sites as (caller_full_name, callee_simple_name, line_1indexed, col_0indexed) tuples.

    .tsx and .jsx files use the TSX grammar; all other extensions use the TypeScript
    grammar (which is a superset of JavaScript for call/import extraction purposes).
    """

    def __init__(
        self,
        module_name_resolver: Callable[[str], str | None] | None = None,
    ) -> None:
        import tree_sitter_typescript
        from tree_sitter import Language, Parser, Query, QueryCursor

        self._module_name_resolver = module_name_resolver

        self._ts_lang = Language(tree_sitter_typescript.language_typescript())
        self._tsx_lang = Language(tree_sitter_typescript.language_tsx())
        self._ts_parser = Parser(self._ts_lang)
        self._tsx_parser = Parser(self._tsx_lang)

        self._ts_query = Query(self._ts_lang, _TS_CALLS_QUERY)
        self._tsx_query = Query(self._tsx_lang, _TS_CALLS_QUERY)

        self._QueryCursor = QueryCursor
        self._sites_seen: int = 0

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

        self._sites_seen = 0

        uses_tsx = any(file_path.endswith(ext) for ext in _TSX_EXTENSIONS)
        parser = self._tsx_parser if uses_tsx else self._ts_parser
        query = self._tsx_query if uses_tsx else self._ts_query

        try:
            tree = parser.parse(bytes(source, "utf-8"))
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

        cursor = self._QueryCursor(query)
        for _pattern_idx, captures in cursor.matches(tree.root_node):
            nodes = captures.get("name", [])
            for node in nodes:
                call_line_0 = node.start_point[0]
                call_col_0 = node.start_point[1]
                callee_name = node.text.decode("utf-8") if isinstance(node.text, bytes) else node.text

                scope_type, _scope_func_line = self._get_call_scope(node)

                if scope_type == "class":
                    continue

                if scope_type == "function":
                    caller = self._find_enclosing_method(call_line_0, method_lines)
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

        Returns ('function', start_line_0) if inside a function/method/arrow_function,
        ('class', None) if directly inside a class field definition (no function in between),
        ('module', None) if at module top level.
        """
        parent = node.parent
        while parent is not None:
            node_type = parent.type
            if node_type in _FUNCTION_SCOPE_TYPES:
                start_line = parent.start_point[0]
                return ("function", start_line)
            if node_type in _CLASS_BODY_DIRECT_TYPES:
                return ("class", None)
            parent = parent.parent
        return ("module", None)

    def _find_enclosing_method(
        self, line_0: int, method_lines: list[tuple[int, str]]
    ) -> str | None:
        """Return the full_name of the innermost method whose start line <= line_0."""
        best: str | None = None
        for method_line, full_name in method_lines:
            if method_line <= line_0:
                best = full_name
            else:
                break
        return best
