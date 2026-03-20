from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

# TSX/JSX files require the TSX grammar; everything else uses the TS grammar
# (TS grammar is a superset of JS for the import/export subset we parse).
_TSX_EXTENSIONS = frozenset({".tsx", ".jsx"})


class TypeScriptImportExtractor:
    def __init__(self, source_root: str = "") -> None:
        import tree_sitter_typescript
        from tree_sitter import Language, Parser

        self._ts_parser = Parser(Language(tree_sitter_typescript.language_typescript()))
        self._tsx_parser = Parser(Language(tree_sitter_typescript.language_tsx()))
        self._source_root = source_root

    def extract(self, file_path: str, source: str) -> list[tuple[str, str | None]]:
        """Return (module_path, imported_symbol_name_or_None) pairs.

        For `import { X } from 'Y'`: returns (resolved_Y, 'X').
        For `import X from 'Y'` (default): returns (resolved_Y, None).
        For `import * as X from 'Y'` (namespace): returns (resolved_Y, None).
        For `export { X } from 'Y'`: returns (resolved_Y, 'X').
        For `export * from 'Y'`: returns (resolved_Y, None).
        For `require('Y')`: returns (resolved_Y, None).
        Relative paths resolved against source_root to forward-slash paths.
        """
        if not source.strip():
            return []
        ext = os.path.splitext(file_path)[1].lower()
        parser = self._tsx_parser if ext in _TSX_EXTENSIONS else self._ts_parser
        try:
            tree = parser.parse(bytes(source, "utf-8"))
        except Exception:
            log.warning("tree-sitter failed to parse %s", file_path)
            return []

        results: list[tuple[str, str | None]] = []
        seen: set[tuple[str, str | None]] = set()
        self._walk(tree.root_node, file_path, results, seen)
        return results

    def _walk(
        self,
        node,
        file_path: str,
        results: list[tuple[str, str | None]],
        seen: set[tuple[str, str | None]],
    ) -> None:
        if node.type == "import_statement":
            self._handle_import_statement(node, file_path, results, seen)
        elif node.type == "export_statement":
            self._handle_export_statement(node, file_path, results, seen)
        elif node.type == "call_expression":
            self._handle_call_expression(node, file_path, results, seen)
        else:
            for child in node.children:
                self._walk(child, file_path, results, seen)

    def _handle_import_statement(
        self,
        node,
        file_path: str,
        results: list[tuple[str, str | None]],
        seen: set[tuple[str, str | None]],
    ) -> None:
        source_path = self._get_string_fragment(node)
        if source_path is None:
            return
        module = self._resolve_specifier(source_path, file_path)

        import_clause = next((c for c in node.children if c.type == "import_clause"), None)
        if import_clause is None:
            # Side-effect import: `import './polyfill'`
            self._add(results, seen, module, None)
            return

        for child in import_clause.children:
            if child.type == "named_imports":
                for spec in child.children:
                    if spec.type == "import_specifier":
                        # Aliased: `{ Dog as D }` has two identifier children; take first (original)
                        ids = [c for c in spec.children if c.type == "identifier"]
                        if ids:
                            self._add(results, seen, module, _text(ids[0]))
            elif child.type == "identifier":
                # Default import: `import Animal from '...'`
                self._add(results, seen, module, None)
            elif child.type == "namespace_import":
                # Namespace import: `import * as Utils from '...'`
                self._add(results, seen, module, None)

    def _handle_export_statement(
        self,
        node,
        file_path: str,
        results: list[tuple[str, str | None]],
        seen: set[tuple[str, str | None]],
    ) -> None:
        # Only handle re-exports: export { X } from '...' and export * from '...'
        source_path = self._get_string_fragment(node)
        if source_path is None:
            return
        module = self._resolve_specifier(source_path, file_path)

        export_clause = next((c for c in node.children if c.type == "export_clause"), None)
        if export_clause is not None:
            # Named re-export: export { Foo, Bar } from '...'
            for spec in export_clause.children:
                if spec.type == "export_specifier":
                    # First identifier child is the original exported name
                    ids = [c for c in spec.children if c.type == "identifier"]
                    if ids:
                        self._add(results, seen, module, _text(ids[0]))
        else:
            # Star re-export: export * from '...'
            self._add(results, seen, module, None)

    def _handle_call_expression(
        self,
        node,
        file_path: str,
        results: list[tuple[str, str | None]],
        seen: set[tuple[str, str | None]],
    ) -> None:
        # CommonJS: require('./foo')
        fn_child = node.children[0] if node.children else None
        if fn_child is None or fn_child.type != "identifier" or _text(fn_child) != "require":
            return
        args = next((c for c in node.children if c.type == "arguments"), None)
        if args is None:
            return
        source_path = self._get_string_fragment(args)
        if source_path is None:
            return
        module = self._resolve_specifier(source_path, file_path)
        self._add(results, seen, module, None)

    def _get_string_fragment(self, node) -> str | None:
        """Return the inner text of the first string child of node."""
        for child in node.children:
            if child.type == "string":
                for sc in child.children:
                    if sc.type == "string_fragment":
                        return _text(sc)
        return None

    def _resolve_specifier(self, specifier: str, file_path: str) -> str:
        """Resolve ./foo or ../bar to a path relative to source_root with forward slashes.

        Package imports (no leading dot) pass through unchanged.
        """
        if specifier.startswith("."):
            dir_path = os.path.dirname(file_path)
            resolved = os.path.normpath(os.path.join(dir_path, specifier))
            rel = (
                os.path.relpath(resolved, self._source_root)
                if self._source_root
                else resolved
            )
            return rel.replace(os.sep, "/")
        return specifier

    @staticmethod
    def _add(
        results: list[tuple[str, str | None]],
        seen: set[tuple[str, str | None]],
        module: str,
        name: str | None,
    ) -> None:
        key = (module, name)
        if key not in seen:
            seen.add(key)
            results.append(key)


def _text(node) -> str:
    raw = node.text
    return raw.decode("utf-8") if isinstance(raw, bytes) else raw
