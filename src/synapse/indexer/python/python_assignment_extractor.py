from __future__ import annotations

import logging
from collections.abc import Callable

from tree_sitter import Tree

from synapse.indexer.assignment_ref import AssignmentRef
from synapse.indexer.tree_sitter_util import node_text

log = logging.getLogger(__name__)

# Matches: self.<field> = <call>(...)
_SELF_ASSIGNMENT_QUERY = """
(assignment
  left: (attribute
    object: (identifier) @obj
    attribute: (identifier) @field)
  right: (call) @source
) @assign
"""

# Matches: <name> = <call>(...) at any scope (filtered to module scope in code)
_MODULE_ASSIGNMENT_QUERY = """
(assignment
  left: (identifier) @field
  right: (call) @source
) @assign
"""

_FUNCTION_SCOPE_TYPES = {"function_definition", "async_function_definition", "lambda"}
_CLASS_SCOPE_TYPES = {"class_definition"}


class PythonAssignmentExtractor:
    """
    Parses Python source with tree-sitter and extracts assignment statements
    where the RHS is a call expression (e.g., self._handler = create_handler()).
    """

    def __init__(self) -> None:
        import tree_sitter_python
        from tree_sitter import Language, Query, QueryCursor

        self._language = Language(tree_sitter_python.language())
        self._self_query = Query(self._language, _SELF_ASSIGNMENT_QUERY)
        self._module_query = Query(self._language, _MODULE_ASSIGNMENT_QUERY)
        self._QueryCursor = QueryCursor

    def extract(
        self,
        file_path: str,
        tree: Tree,
        symbol_map: dict[tuple[str, int], str],
        class_lines: list[tuple[int, str]] | None = None,
        module_name_resolver: Callable[[str], str | None] | None = None,
    ) -> list[AssignmentRef]:
        results: list[AssignmentRef] = []

        self._extract_self_assignments(
            tree, file_path, class_lines or [], results
        )
        self._extract_module_assignments(
            tree, file_path, module_name_resolver, results
        )

        return results

    def _extract_self_assignments(
        self,
        tree,
        file_path: str,
        class_lines: list[tuple[int, str]],
        results: list[AssignmentRef],
    ) -> None:
        cursor = self._QueryCursor(self._self_query)
        for _pattern_idx, captures in cursor.matches(tree.root_node):
            obj_nodes = captures.get("obj", [])
            field_nodes = captures.get("field", [])
            source_nodes = captures.get("source", [])

            if not obj_nodes or not field_nodes or not source_nodes:
                continue

            obj_text = node_text(obj_nodes[0])
            if obj_text != "self":
                continue

            field_name = node_text(field_nodes[0])
            source_node = source_nodes[0]

            # source position is the start of the call's function expression
            func_node = source_node.children[0] if source_node.children else source_node
            source_line = func_node.start_point[0]
            source_col = func_node.start_point[1]

            class_full_name = self._find_enclosing_class(
                source_node, class_lines
            )
            if class_full_name is None:
                continue

            results.append(
                AssignmentRef(
                    class_full_name=class_full_name,
                    field_name=field_name,
                    source_file=file_path,
                    source_line=source_line,
                    source_col=source_col,
                )
            )

    def _extract_module_assignments(
        self,
        tree,
        file_path: str,
        module_name_resolver: Callable[[str], str | None] | None,
        results: list[AssignmentRef],
    ) -> None:
        if module_name_resolver is None:
            return

        cursor = self._QueryCursor(self._module_query)
        for _pattern_idx, captures in cursor.matches(tree.root_node):
            field_nodes = captures.get("field", [])
            source_nodes = captures.get("source", [])

            if not field_nodes or not source_nodes:
                continue

            field_node = field_nodes[0]
            source_node = source_nodes[0]

            if not self._is_module_scope(field_node):
                continue

            field_name = node_text(field_node)

            func_node = source_node.children[0] if source_node.children else source_node
            source_line = func_node.start_point[0]
            source_col = func_node.start_point[1]

            module_name = module_name_resolver(file_path)
            if module_name is None:
                continue

            results.append(
                AssignmentRef(
                    class_full_name=module_name,
                    field_name=field_name,
                    source_file=file_path,
                    source_line=source_line,
                    source_col=source_col,
                )
            )

    def _find_enclosing_class(
        self, node, class_lines: list[tuple[int, str]]
    ) -> str | None:
        """Walk parent chain to find enclosing class_definition, then resolve via class_lines."""
        class_name = self._get_enclosing_class_name(node)
        if class_name is None:
            return None

        # Find the class_definition node to get its line
        class_node_line = self._get_enclosing_class_line(node)
        if class_node_line is None:
            return None

        # Match against class_lines by line number
        for line, full_name in class_lines:
            if line == class_node_line:
                return full_name

        # Fallback: match by suffix
        for _line, full_name in class_lines:
            if full_name.endswith("." + class_name) or full_name == class_name:
                return full_name

        return None

    @staticmethod
    def _get_enclosing_class_name(node) -> str | None:
        parent = node.parent
        while parent is not None:
            if parent.type in _CLASS_SCOPE_TYPES:
                name_node = next(
                    (c for c in parent.children if c.type == "identifier"), None
                )
                return node_text(name_node) if name_node else None
            parent = parent.parent
        return None

    @staticmethod
    def _get_enclosing_class_line(node) -> int | None:
        parent = node.parent
        while parent is not None:
            if parent.type in _CLASS_SCOPE_TYPES:
                return parent.start_point[0]
            parent = parent.parent
        return None

    @staticmethod
    def _is_module_scope(node) -> bool:
        parent = node.parent
        while parent is not None:
            if parent.type in _FUNCTION_SCOPE_TYPES or parent.type in _CLASS_SCOPE_TYPES:
                return False
            parent = parent.parent
        return True

