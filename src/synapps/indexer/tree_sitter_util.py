"""Shared tree-sitter utilities used by all language extractors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tree_sitter


@dataclass(frozen=True)
class ParsedFile:
    """A source file with its tree-sitter parse tree. Created once, shared across all extractors."""
    file_path: str
    source: str
    tree: tree_sitter.Tree


# All method-like node types across the four indexed languages.
# Used by find_enclosing_method_ast to identify scope boundaries via AST parent traversal.
_METHOD_NODE_TYPES: frozenset[str] = frozenset({
    # Python
    "function_definition",
    "async_function_definition",
    "lambda",
    # TypeScript / JavaScript
    "function_declaration",
    "method_definition",
    "arrow_function",
    "function_expression",
    "generator_function_declaration",
    "generator_function",
    # Java
    "method_declaration",
    "constructor_declaration",
    # C# (method_declaration and constructor_declaration already covered above)
    "local_function_statement",
    "anonymous_method_expression",
    "lambda_expression",
})


def node_text(node) -> str:
    """Decode a tree-sitter node's text to a Python str."""
    raw = node.text
    return raw.decode("utf-8") if isinstance(raw, bytes) else raw


def find_enclosing_scope(
    line_0: int, sorted_lines: list[tuple[int, str]]
) -> str | None:
    """Return the full_name of the innermost scope whose start line <= line_0.

    Works for both method and class scope lookups. ``sorted_lines`` must be
    sorted ascending by line number.
    """
    best: str | None = None
    for scope_line, full_name in sorted_lines:
        if scope_line <= line_0:
            best = full_name
        else:
            break
    return best


def find_enclosing_method_ast(
    file_path: str,
    line_0: int,
    col_0: int,
    parsed_cache: dict[str, ParsedFile],
    symbol_map: dict[tuple[str, int], str],
) -> str | None:
    """Return the full_name of the innermost method/function enclosing (line_0, col_0).

    Uses AST parent-chain traversal instead of line-based bisect, so nested functions
    and lambdas are attributed to the correct innermost scope.

    Args:
        file_path: Absolute path of the source file.
        line_0: 0-based line number of the position.
        col_0: 0-based column number of the position.
        parsed_cache: Maps file_path -> ParsedFile (tree-sitter parse trees).
        symbol_map: Maps (file_path, 1-based line) -> method full_name.

    Returns:
        The full_name of the innermost enclosing method, or None if the position
        is outside all indexed methods (e.g., module-level code, imports).
    """
    pf = parsed_cache.get(file_path)
    if pf is None:
        return None

    node = pf.tree.root_node.descendant_for_point_range((line_0, col_0), (line_0, col_0))
    current = node
    while current is not None:
        if current.type in _METHOD_NODE_TYPES:
            # Prefer the name node's line for the lookup: tree-sitter includes
            # annotations/attributes in the declaration node, but symbol_map is
            # keyed by selectionRange (name line) from the language server.
            name_node = current.child_by_field_name("name")
            lookup_line = (name_node.start_point[0] if name_node is not None else current.start_point[0]) + 1
            full_name = symbol_map.get((file_path, lookup_line))
            if full_name is not None:
                return full_name
        current = current.parent
    return None
