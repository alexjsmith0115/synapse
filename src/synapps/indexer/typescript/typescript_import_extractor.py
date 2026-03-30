from __future__ import annotations

import json
import logging
import os
import re

from tree_sitter import Tree

from synapps.indexer.tree_sitter_util import node_text

log = logging.getLogger(__name__)

# TSX/JSX files require the TSX grammar; everything else uses the TS grammar
# (TS grammar is a superset of JS for the import/export subset we parse).
_TSX_EXTENSIONS = frozenset({".tsx", ".jsx"})

_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")


def _strip_jsonc_comments(text: str) -> str:
    """Strip // and /* */ comments from JSONC text, preserving strings.

    Also strips trailing commas before } and ] for tsconfig.json compatibility.
    Uses a state machine to avoid stripping comment-like sequences inside strings.
    """
    result: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        # String literal — copy verbatim until closing quote
        if c == '"':
            result.append(c)
            i += 1
            while i < n:
                sc = text[i]
                result.append(sc)
                i += 1
                if sc == '\\' and i < n:
                    result.append(text[i])
                    i += 1
                elif sc == '"':
                    break
        # Line comment — skip to end of line
        elif c == '/' and i + 1 < n and text[i + 1] == '/':
            i += 2
            while i < n and text[i] != '\n':
                i += 1
        # Block comment — skip to */
        elif c == '/' and i + 1 < n and text[i + 1] == '*':
            i += 2
            while i < n:
                if text[i] == '*' and i + 1 < n and text[i + 1] == '/':
                    i += 2
                    break
                i += 1
        else:
            result.append(c)
            i += 1

    return _TRAILING_COMMA_RE.sub(r"\1", "".join(result))


def _load_tsconfig_paths(source_root: str) -> list[tuple[str, str]]:
    """Load path alias mappings from tsconfig.json compilerOptions.paths.

    Searches source_root and its immediate subdirectories (for monorepos
    where tsconfig.json is in frontend/, packages/app/, etc.).

    Returns a list of (prefix, replacement_dir) tuples, e.g.,
    [("@/", "src/")] for {"@/*": ["./src/*"]}.
    """
    if not source_root:
        return []

    candidates: list[str] = []
    # Check source_root itself first
    for name in ("tsconfig.json", "tsconfig.app.json"):
        candidates.append(os.path.join(source_root, name))
    # Check immediate subdirectories (monorepo: frontend/, app/, etc.)
    try:
        for entry in os.scandir(source_root):
            if entry.is_dir() and not entry.name.startswith("."):
                for name in ("tsconfig.json", "tsconfig.app.json"):
                    candidates.append(os.path.join(entry.path, name))
    except OSError:
        pass

    for config_path in candidates:
        if not os.path.isfile(config_path):
            continue
        try:
            with open(config_path, encoding="utf-8") as f:
                raw = json.loads(_strip_jsonc_comments(f.read()))
            paths = raw.get("compilerOptions", {}).get("paths", {})
            if not paths:
                continue
            config_dir = os.path.relpath(os.path.dirname(config_path), source_root)
            result: list[tuple[str, str]] = []
            for alias_pattern, targets in paths.items():
                if not targets or not alias_pattern.endswith("/*"):
                    continue
                prefix = alias_pattern[:-1]  # "@/*" → "@/"
                target = targets[0]
                if target.endswith("/*"):
                    target = target[:-1]  # "./src/*" → "./src/"
                if target.startswith("./"):
                    target = target[2:]  # "./src/" → "src/"
                # Prepend tsconfig directory for subdirectory configs
                if config_dir and config_dir != ".":
                    target = config_dir + "/" + target
                result.append((prefix, target))
            if result:
                return result
        except (json.JSONDecodeError, OSError):
            continue
    return []


def build_import_map(
    extractor: TypeScriptImportExtractor,
    file_trees: dict[str, Tree],
) -> dict[str, dict[str, str]]:
    """Build {file_path: {imported_symbol_name: module_path}} from import extraction.

    Only includes named imports (where imported_name is not None).
    Package imports (no leading dot, no alias match) are included — the
    module_path won't match any graph node, so they're harmlessly ignored
    during fallback resolution.
    """
    result: dict[str, dict[str, str]] = {}
    for file_path, tree in file_trees.items():
        imports = extractor.extract(file_path, tree)
        file_map: dict[str, str] = {}
        for module_path, imported_name in imports:
            if imported_name is not None:
                file_map[imported_name] = module_path
        if file_map:
            result[file_path] = file_map
    return result


class TypeScriptImportExtractor:
    def __init__(self, source_root: str = "") -> None:
        self._source_root = source_root
        self._path_aliases: list[tuple[str, str]] | None = None

    def extract(self, file_path: str, tree: Tree) -> list[tuple[str, str | None]]:
        """Return (module_path, imported_symbol_name_or_None) pairs.

        For `import { X } from 'Y'`: returns (resolved_Y, 'X').
        For `import X from 'Y'` (default): returns (resolved_Y, None).
        For `import * as X from 'Y'` (namespace): returns (resolved_Y, None).
        For `export { X } from 'Y'`: returns (resolved_Y, 'X').
        For `export * from 'Y'`: returns (resolved_Y, None).
        For `require('Y')`: returns (resolved_Y, None).
        Relative paths resolved against source_root to forward-slash paths.
        """
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
                            self._add(results, seen, module, node_text(ids[0]))
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
                        self._add(results, seen, module, node_text(ids[0]))
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
        if fn_child is None or fn_child.type != "identifier" or node_text(fn_child) != "require":
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
                        return node_text(sc)
        return None

    def _get_path_aliases(self) -> list[tuple[str, str]]:
        """Lazily load path aliases — must wait until _source_root is set."""
        if self._path_aliases is None:
            self._path_aliases = _load_tsconfig_paths(self._source_root)
        return self._path_aliases

    def _resolve_specifier(self, specifier: str, file_path: str) -> str:
        """Resolve import specifiers to paths relative to source_root.

        Handles: relative paths (./foo, ../bar), tsconfig path aliases (@/foo).
        Package imports (no leading dot, no alias match) pass through unchanged.
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
        # Check tsconfig path aliases (e.g., "@/" → "src/")
        for prefix, replacement in self._get_path_aliases():
            if specifier.startswith(prefix):
                remainder = specifier[len(prefix):]
                return (replacement + remainder).replace(os.sep, "/")
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


