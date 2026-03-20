from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)


class PythonImportExtractor:
    def __init__(self, source_root: str = "") -> None:
        import tree_sitter_python
        from tree_sitter import Language, Parser

        self._language = Language(tree_sitter_python.language())
        self._parser = Parser(self._language)
        self._source_root = source_root

    def extract(self, file_path: str, source: str) -> list[tuple[str, str | None]]:
        """Return (module_dotted_path, imported_symbol_name_or_None) pairs.

        For `from X import Y`: returns (X, Y).
        For `import X`: returns (X, None).
        Star imports skipped. Relative imports resolved using source_root.
        """
        if not source.strip():
            return []
        try:
            tree = self._parser.parse(bytes(source, "utf-8"))
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
            self._handle_import(node, results, seen)
        elif node.type == "import_from_statement":
            self._handle_from_import(node, file_path, results, seen)
        else:
            for child in node.children:
                self._walk(child, file_path, results, seen)

    def _handle_import(
        self,
        node,
        results: list[tuple[str, str | None]],
        seen: set[tuple[str, str | None]],
    ) -> None:
        for child in node.children:
            if child.type == "dotted_name":
                module_name = _text(child)
                self._add(results, seen, module_name, None)

    def _handle_from_import(
        self,
        node,
        file_path: str,
        results: list[tuple[str, str | None]],
        seen: set[tuple[str, str | None]],
    ) -> None:
        # Skip wildcard imports
        for child in node.children:
            if child.type == "wildcard_import":
                return

        module_path: str | None = None
        imported_names: list[str] = []

        children = node.children
        # First dotted_name or relative_import is the module; remaining dotted_names are imports
        module_found = False
        for child in children:
            if not module_found and child.type == "dotted_name":
                module_path = _text(child)
                module_found = True
            elif not module_found and child.type == "relative_import":
                module_path = self._resolve_relative(child, file_path)
                module_found = True
            elif module_found and child.type == "dotted_name":
                imported_names.append(_text(child))
            elif child.type == "aliased_import":
                # `from X import Y as Z` — use original name Y
                for grandchild in child.children:
                    if grandchild.type == "dotted_name":
                        imported_names.append(_text(grandchild))
                        break

        if module_path is None:
            return

        # `from . import foo` — the imported names are in dotted_name children after `import`
        if not imported_names:
            # No names found yet; names follow `import` keyword
            past_import_kw = False
            for child in children:
                if child.type == "import":
                    past_import_kw = True
                elif past_import_kw and child.type == "dotted_name":
                    imported_names.append(_text(child))

        if imported_names:
            for name in imported_names:
                self._add(results, seen, module_path, name)
        else:
            self._add(results, seen, module_path, None)

    def _resolve_relative(self, relative_import_node, file_path: str) -> str:
        """Convert a relative_import node to an absolute module path."""
        prefix_node = None
        suffix_node = None
        for child in relative_import_node.children:
            if child.type == "import_prefix":
                prefix_node = child
            elif child.type == "dotted_name":
                suffix_node = child

        dots = len(prefix_node.text) if prefix_node else 0
        module_suffix = _text(suffix_node) if suffix_node else ""

        return _compute_absolute_module(dots, module_suffix, file_path, self._source_root)

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


def _compute_absolute_module(dots: int, module_suffix: str, file_path: str, source_root: str) -> str:
    if source_root:
        rel = os.path.relpath(file_path, source_root)
    else:
        rel = file_path
    parts = rel.replace(os.sep, ".").removesuffix(".py").split(".")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    # Go up `dots` levels from the current package (not module for regular files)
    package_parts = parts[:-dots] if dots <= len(parts) else []
    if module_suffix:
        package_parts.append(module_suffix)
    return ".".join(package_parts)


def _text(node) -> str:
    raw = node.text
    return raw.decode("utf-8") if isinstance(raw, bytes) else raw
