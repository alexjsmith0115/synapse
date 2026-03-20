from __future__ import annotations

import logging

log = logging.getLogger(__name__)

_TSX_EXTENSIONS = frozenset({".tsx", ".jsx"})

_DECLARATION_TYPES = frozenset({
    "class_declaration",
    "abstract_class_declaration",
    "function_declaration",
    "interface_declaration",
    "method_definition",
    "abstract_method_signature",
    "public_field_definition",
})


class TypeScriptAttributeExtractor:
    def __init__(self) -> None:
        import tree_sitter_typescript
        from tree_sitter import Language, Parser

        self._ts_parser = Parser(Language(tree_sitter_typescript.language_typescript()))
        self._tsx_parser = Parser(Language(tree_sitter_typescript.language_tsx()))

    def extract(self, file_path: str, source: str) -> list[tuple[str, list[str]]]:
        """Return (symbol_name, [metadata_markers]) pairs for all annotated TypeScript symbols."""
        if not source.strip():
            return []

        ext = "." + file_path.rsplit(".", 1)[-1] if "." in file_path else ""
        parser = self._tsx_parser if ext in _TSX_EXTENSIONS else self._ts_parser

        try:
            tree = parser.parse(bytes(source, "utf-8"))
        except Exception:
            log.warning("tree-sitter failed to parse %s", file_path)
            return []

        results: list[tuple[str, list[str]]] = []
        self._walk(tree.root_node, results, [])
        return results

    def _walk(self, node, results: list[tuple[str, list[str]]], pending_decorators: list[str]) -> None:
        """Walk the AST and emit (symbol_name, markers) pairs."""
        ntype = node.type

        if ntype == "export_statement":
            self._handle_export(node, results)

        elif ntype == "abstract_class_declaration":
            self._handle_class(node, results, pending_decorators, auto_abstract=True)

        elif ntype == "class_declaration":
            self._handle_class(node, results, pending_decorators, auto_abstract=False)

        elif ntype == "interface_declaration":
            self._handle_interface(node, results, pending_decorators)

        elif ntype == "function_declaration":
            self._handle_function(node, results, pending_decorators)

        elif ntype == "method_definition":
            self._handle_method(node, results, pending_decorators, auto_abstract=False)

        elif ntype == "abstract_method_signature":
            self._handle_method(node, results, pending_decorators, auto_abstract=True)

        elif ntype == "public_field_definition":
            self._handle_field(node, results, pending_decorators)

        else:
            for child in node.children:
                self._walk(child, results, [])

    def _handle_export(self, node, results: list[tuple[str, list[str]]]) -> None:
        """Handle export_statement: collect decorators that precede the declaration."""
        decorators: list[str] = []
        declaration = None

        for child in node.children:
            if child.type == "decorator":
                name = self._decorator_name(child)
                if name:
                    decorators.append(name)
            elif child.type in _DECLARATION_TYPES:
                declaration = child

        if declaration is None:
            # Recurse into any non-declaration children (e.g. export default)
            for child in node.children:
                if child.type not in ("decorator", "export", ";"):
                    self._walk(child, results, decorators[:])
            return

        # Pass decorators + ["export"] into the declaration handler
        export_decorators = decorators + ["export"]
        dtype = declaration.type

        if dtype == "abstract_class_declaration":
            self._handle_class(declaration, results, export_decorators, auto_abstract=True)
        elif dtype == "class_declaration":
            self._handle_class(declaration, results, export_decorators, auto_abstract=False)
        elif dtype == "interface_declaration":
            self._handle_interface(declaration, results, export_decorators)
        elif dtype == "function_declaration":
            self._handle_function(declaration, results, export_decorators)
        elif dtype == "method_definition":
            self._handle_method(declaration, results, export_decorators, auto_abstract=False)
        elif dtype == "abstract_method_signature":
            self._handle_method(declaration, results, export_decorators, auto_abstract=True)
        elif dtype == "public_field_definition":
            self._handle_field(declaration, results, export_decorators)

    def _handle_class(
        self,
        node,
        results: list[tuple[str, list[str]]],
        inherited_markers: list[str],
        auto_abstract: bool,
    ) -> None:
        name = self._type_identifier(node)
        if not name:
            return

        markers = list(inherited_markers)
        if auto_abstract and "abstract" not in markers:
            markers.append("abstract")

        # Decorators may appear as direct children of the class node itself
        # (when the class is not inside export_statement)
        for child in node.children:
            if child.type == "decorator":
                dec_name = self._decorator_name(child)
                if dec_name and dec_name not in markers:
                    markers.append(dec_name)

        markers.extend(self._scan_modifiers(node))

        if markers:
            results.append((name, markers))

        # Walk class body for nested members, collecting decorators per-member
        for child in node.children:
            if child.type == "class_body":
                self._walk_class_body(child, results)

    def _handle_interface(
        self,
        node,
        results: list[tuple[str, list[str]]],
        inherited_markers: list[str],
    ) -> None:
        name = self._type_identifier(node)
        if not name:
            return

        markers = list(inherited_markers)
        if markers:
            results.append((name, markers))

        # Walk interface body for nested members
        for child in node.children:
            if child.type in ("interface_body", "object_type"):
                for body_child in child.children:
                    self._walk(body_child, results, [])

    def _handle_function(
        self,
        node,
        results: list[tuple[str, list[str]]],
        inherited_markers: list[str],
    ) -> None:
        name = self._identifier(node)
        if not name:
            return

        markers = list(inherited_markers)
        markers.extend(self._scan_modifiers(node))

        if markers:
            results.append((name, markers))

    def _handle_method(
        self,
        node,
        results: list[tuple[str, list[str]]],
        inherited_markers: list[str],
        auto_abstract: bool,
    ) -> None:
        name = self._property_identifier(node)
        if not name:
            return

        markers = list(inherited_markers)
        if auto_abstract and "abstract" not in markers:
            markers.append("abstract")

        markers.extend(self._scan_modifiers(node))

        if markers:
            results.append((name, markers))

    def _handle_field(
        self,
        node,
        results: list[tuple[str, list[str]]],
        inherited_markers: list[str],
    ) -> None:
        name = self._property_identifier(node)
        if not name:
            return

        markers = list(inherited_markers)
        markers.extend(self._scan_modifiers(node))

        if markers:
            results.append((name, markers))

    def _walk_class_body(self, body_node, results: list[tuple[str, list[str]]]) -> None:
        """Walk class_body children, grouping decorators with their following member."""
        pending: list[str] = []
        for child in body_node.children:
            if child.type == "decorator":
                name = self._decorator_name(child)
                if name:
                    pending.append(name)
            elif child.type in _DECLARATION_TYPES:
                self._walk(child, results, pending)
                pending = []
            else:
                # Non-declaration, non-decorator — flush pending and recurse
                if child.type not in ("{", "}", ";", "comment"):
                    self._walk(child, results, [])
                pending = []

    def _decorator_name(self, decorator_node) -> str | None:
        """Extract simple name from a decorator node."""
        for child in decorator_node.children:
            if child.type == "identifier":
                return _text(child)
            if child.type == "call_expression":
                # @Name(...) — get identifier from call_expression
                for call_child in child.children:
                    if call_child.type == "identifier":
                        return _text(call_child)
                    if call_child.type == "member_expression":
                        return self._rightmost_property(call_child)
            if child.type == "member_expression":
                # @ns.Name — return rightmost
                return self._rightmost_property(child)
        return None

    def _scan_modifiers(self, node) -> list[str]:
        """Scan a node's direct children for modifier tokens."""
        modifiers: list[str] = []
        for child in node.children:
            t = child.type
            if t in ("static", "async", "readonly", "override"):
                modifiers.append(t)
            elif t == "accessibility_modifier":
                text = _text(child).strip()
                if text:
                    modifiers.append(text)
        return modifiers

    def _type_identifier(self, node) -> str | None:
        """Find the first type_identifier child (class/interface name)."""
        for child in node.children:
            if child.type == "type_identifier":
                return _text(child)
        return None

    def _identifier(self, node) -> str | None:
        """Find the first identifier child (function name)."""
        for child in node.children:
            if child.type == "identifier":
                return _text(child)
        return None

    def _property_identifier(self, node) -> str | None:
        """Find the first property_identifier child (method/field name)."""
        for child in node.children:
            if child.type == "property_identifier":
                return _text(child)
        return None

    def _rightmost_property(self, member_expression_node) -> str | None:
        """Extract rightmost name from member_expression (e.g. ns.Name -> Name)."""
        for child in member_expression_node.children:
            if child.type == "property_identifier":
                return _text(child)
        return None


def _text(node) -> str:
    raw = node.text
    return raw.decode("utf-8") if isinstance(raw, bytes) else raw
