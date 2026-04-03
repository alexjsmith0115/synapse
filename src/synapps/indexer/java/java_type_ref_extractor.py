from __future__ import annotations

import logging

from tree_sitter import Tree

from synapps.indexer.tree_sitter_util import find_enclosing_scope, node_text
from synapps.indexer.type_ref import TypeRef

log = logging.getLogger(__name__)

# Java primitive types and void that should not produce REFERENCES edges (D-20)
_PRIMITIVE_TYPES = frozenset({
    "int", "long", "short", "byte", "float", "double", "boolean", "char", "void",
})


class JavaTypeRefExtractor:
    """Extract type references from Java source for REFERENCES edges.

    Finds parameter types, return types, field types, local variable types,
    and generic type arguments. Skips primitives and void per D-20.
    """

    def __init__(self) -> None:
        pass

    def extract(
        self,
        file_path: str,
        tree: Tree,
        symbol_map: dict[tuple[str, int], str],
        class_lines: list[tuple[int, str]] = (),
        *,
        field_symbol_map: dict[tuple[str, int], str] | None = None,
        module_name_resolver=None,
    ) -> list[TypeRef]:
        """Return TypeRef instances for all non-primitive type references."""
        # Build sorted scope lines for find_enclosing_scope
        method_lines = sorted(
            (line, full_name)
            for (fp, line), full_name in symbol_map.items()
            if fp == file_path
        )

        results: list[TypeRef] = []
        self._walk(
            tree.root_node, file_path, method_lines, list(class_lines),
            field_symbol_map or {}, results,
        )
        return results

    # ------------------------------------------------------------------
    # Tree walk
    # ------------------------------------------------------------------

    def _walk(
        self, node, file_path, method_lines, class_lines, field_map, results: list[TypeRef],
    ) -> None:
        node_type = node.type

        if node_type == "formal_parameter":
            self._handle_typed_node(node, file_path, method_lines, results, "parameter")

        elif node_type == "method_declaration":
            self._handle_return_type(node, file_path, method_lines, results)

        elif node_type == "field_declaration":
            # Use field-level owner if available; fall back to class scope for REFERENCES edge source
            field_owner = field_map.get((file_path, node.start_point[0]))
            if field_owner:
                self._handle_typed_node_with_owner(node, field_owner, results, "field_type")
            else:
                self._handle_typed_node(
                    node, file_path, class_lines or method_lines, results, "field_type",
                )

        elif node_type == "local_variable_declaration":
            self._handle_typed_node(node, file_path, method_lines, results, "field_type")

        for child in node.children:
            self._walk(child, file_path, method_lines, class_lines, field_map, results)

    # ------------------------------------------------------------------
    # Node handlers — scope-based (original)
    # ------------------------------------------------------------------

    def _handle_typed_node(
        self, node, file_path, scope_lines, results: list[TypeRef], ref_kind: str,
    ) -> None:
        """Handle nodes that have a type as a direct child (parameters, fields, locals)."""
        for child in node.children:
            if child.type == "type_identifier":
                self._emit_type_ref(child, file_path, scope_lines, results, ref_kind)
            elif child.type == "generic_type":
                self._handle_generic_type(child, file_path, scope_lines, results, ref_kind)
            elif child.type == "array_type":
                self._handle_array_type(child, file_path, scope_lines, results, ref_kind)

    def _handle_return_type(
        self, node, file_path, method_lines, results: list[TypeRef],
    ) -> None:
        """Handle method return types (type_identifier or generic_type before method name)."""
        for child in node.children:
            if child.type == "type_identifier":
                self._emit_type_ref(child, file_path, method_lines, results, "return_type")
                break
            elif child.type == "generic_type":
                self._handle_generic_type(child, file_path, method_lines, results, "return_type")
                break
            elif child.type == "array_type":
                self._handle_array_type(child, file_path, method_lines, results, "return_type")
                break
            elif child.type in ("void_type", "modifiers"):
                continue
            elif child.type == "identifier":
                # Reached the method name -- no return type ref to extract
                break

    def _handle_generic_type(
        self, node, file_path, scope_lines, results: list[TypeRef], ref_kind: str,
    ) -> None:
        """Handle generic types like List<Animal> -- extract both outer and inner type refs."""
        for child in node.children:
            if child.type == "type_identifier":
                self._emit_type_ref(child, file_path, scope_lines, results, ref_kind)
            elif child.type == "type_arguments":
                self._handle_type_arguments(child, file_path, scope_lines, results, ref_kind)

    def _handle_type_arguments(
        self, node, file_path, scope_lines, results: list[TypeRef], ref_kind: str,
    ) -> None:
        """Handle <Type1, Type2> generic type argument lists."""
        for child in node.children:
            if child.type == "type_identifier":
                self._emit_type_ref(child, file_path, scope_lines, results, ref_kind)
            elif child.type == "generic_type":
                self._handle_generic_type(child, file_path, scope_lines, results, ref_kind)
            elif child.type == "wildcard":
                # ? extends Foo -- look for type_identifier inside
                for wc_child in child.children:
                    if wc_child.type == "type_identifier":
                        self._emit_type_ref(wc_child, file_path, scope_lines, results, ref_kind)
                    elif wc_child.type == "generic_type":
                        self._handle_generic_type(wc_child, file_path, scope_lines, results, ref_kind)
            elif child.type == "array_type":
                self._handle_array_type(child, file_path, scope_lines, results, ref_kind)

    def _handle_array_type(
        self, node, file_path, scope_lines, results: list[TypeRef], ref_kind: str,
    ) -> None:
        """Handle array types like Animal[] -- extract the element type."""
        for child in node.children:
            if child.type == "type_identifier":
                self._emit_type_ref(child, file_path, scope_lines, results, ref_kind)
            elif child.type == "generic_type":
                self._handle_generic_type(child, file_path, scope_lines, results, ref_kind)

    # ------------------------------------------------------------------
    # Node handlers — pre-resolved owner (field_symbol_map path)
    # ------------------------------------------------------------------

    def _handle_typed_node_with_owner(
        self, node, owner_full_name: str, results: list[TypeRef], ref_kind: str,
    ) -> None:
        """Like _handle_typed_node but uses a pre-resolved owner rather than scope lookup."""
        for child in node.children:
            if child.type == "type_identifier":
                self._emit_type_ref_with_owner(child, owner_full_name, results, ref_kind)
            elif child.type == "generic_type":
                self._handle_generic_type_with_owner(child, owner_full_name, results, ref_kind)
            elif child.type == "array_type":
                self._handle_array_type_with_owner(child, owner_full_name, results, ref_kind)

    def _handle_generic_type_with_owner(
        self, node, owner_full_name: str, results: list[TypeRef], ref_kind: str,
    ) -> None:
        for child in node.children:
            if child.type == "type_identifier":
                self._emit_type_ref_with_owner(child, owner_full_name, results, ref_kind)
            elif child.type == "type_arguments":
                self._handle_type_arguments_with_owner(child, owner_full_name, results, ref_kind)

    def _handle_type_arguments_with_owner(
        self, node, owner_full_name: str, results: list[TypeRef], ref_kind: str,
    ) -> None:
        for child in node.children:
            if child.type == "type_identifier":
                self._emit_type_ref_with_owner(child, owner_full_name, results, ref_kind)
            elif child.type == "generic_type":
                self._handle_generic_type_with_owner(child, owner_full_name, results, ref_kind)
            elif child.type == "wildcard":
                for wc_child in child.children:
                    if wc_child.type == "type_identifier":
                        self._emit_type_ref_with_owner(wc_child, owner_full_name, results, ref_kind)
                    elif wc_child.type == "generic_type":
                        self._handle_generic_type_with_owner(wc_child, owner_full_name, results, ref_kind)
            elif child.type == "array_type":
                self._handle_array_type_with_owner(child, owner_full_name, results, ref_kind)

    def _handle_array_type_with_owner(
        self, node, owner_full_name: str, results: list[TypeRef], ref_kind: str,
    ) -> None:
        for child in node.children:
            if child.type == "type_identifier":
                self._emit_type_ref_with_owner(child, owner_full_name, results, ref_kind)
            elif child.type == "generic_type":
                self._handle_generic_type_with_owner(child, owner_full_name, results, ref_kind)

    def _emit_type_ref_with_owner(
        self, type_node, owner_full_name: str, results: list[TypeRef], ref_kind: str,
    ) -> None:
        """Create a TypeRef using a pre-resolved owner (bypasses scope lookup)."""
        name = node_text(type_node)
        if name in _PRIMITIVE_TYPES:
            return
        results.append(TypeRef(
            owner_full_name=owner_full_name,
            type_name=name,
            line=type_node.start_point[0],
            col=type_node.start_point[1],
            ref_kind=ref_kind,
        ))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _emit_type_ref(
        self, type_node, file_path, scope_lines, results: list[TypeRef], ref_kind: str,
    ) -> None:
        """Create a TypeRef if the type is not primitive."""
        name = node_text(type_node)
        if name in _PRIMITIVE_TYPES:
            return
        line_0 = type_node.start_point[0]
        owner = find_enclosing_scope(line_0, scope_lines)
        if owner is None:
            return
        results.append(TypeRef(
            owner_full_name=owner,
            type_name=name,
            line=line_0,
            col=type_node.start_point[1],
            ref_kind=ref_kind,
        ))
