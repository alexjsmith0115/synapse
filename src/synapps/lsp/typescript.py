from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from synapps.lsp.interface import IndexSymbol, LSPAdapter, LSPResolverBackend, SymbolKind
from synapps.lsp.util import symbol_suffix

if TYPE_CHECKING:
    import tree_sitter

log = logging.getLogger(__name__)

_TS_EXTENSIONS = frozenset({".ts", ".tsx", ".js", ".jsx", ".mts", ".cts", ".mjs", ".cjs"})
_EXCLUDE_DIRS = {
    "node_modules", "dist", "build", ".git", "coverage",
    "coveragereport", ".next", ".nuxt", "out", ".cache",
    ".angular", ".svelte-kit",
}
_EXCLUDE_FILE_SUFFIXES = (".min.js", ".min.css", ".bundle.js", ".chunk.js")

# Maps LSP SymbolKind integers to Synapps SymbolKind.
# Kind 2 (Module/ES module) -> CLASS so ES modules become :Class nodes (mirrors Python adapter decision).
# Kinds 13 (Variable) and 14 (Constant) are skipped — too granular for structural graph indexing.
_LSP_KIND_MAP: dict[int, SymbolKind | None] = {
    2: SymbolKind.CLASS,       # Module (ES module)
    3: SymbolKind.NAMESPACE,   # Namespace
    5: SymbolKind.CLASS,       # Class
    6: SymbolKind.METHOD,      # Method
    7: SymbolKind.PROPERTY,    # Property
    8: SymbolKind.FIELD,       # Field
    9: SymbolKind.METHOD,      # Constructor
    10: SymbolKind.ENUM,       # Enum
    11: SymbolKind.INTERFACE,  # Interface
    12: SymbolKind.METHOD,     # Function (top-level)
    13: None,                  # Variable -> skip
    14: None,                  # Constant -> skip
}


def _parse_ts_file(file_path: str) -> tree_sitter.Tree | None:
    """Parse a TypeScript/TSX file with tree-sitter and return the syntax tree.

    Returns None if the file cannot be read or parsed. Uses the TSX grammar for
    .tsx/.jsx files (superset of TypeScript grammar).
    """
    try:
        import tree_sitter_typescript as ts_ts
        from tree_sitter import Language, Parser

        uses_tsx = file_path.endswith((".tsx", ".jsx"))
        lang = Language(ts_ts.language_tsx() if uses_tsx else ts_ts.language_typescript())
        parser = Parser(lang)
        source = Path(file_path).read_bytes()
        return parser.parse(source)
    except Exception:
        log.debug("Failed to parse %s with tree-sitter", file_path)
        return None


def _is_arrow_function_at_line(tree: tree_sitter.Tree, line_0: int) -> bool:
    """Return True if a variable_declarator whose value is an arrow_function starts at line_0.

    TSServer reports top-level ``export const f = (...) => { ... }`` as kind 14
    (Constant) with an empty children list when the body contains no nested
    constants or properties.  This helper uses the tree-sitter AST to confirm
    the value really is an arrow function so we can promote it to a Method node.

    ``line_0`` is the 0-indexed line number taken from the TSServer symbol's
    ``selectionRange.start.line`` (i.e. the line that declares the identifier).
    """
    def _search(node: tree_sitter.Node) -> bool:
        if node.type == "variable_declarator" and node.start_point[0] == line_0:
            return any(child.type == "arrow_function" for child in node.children)
        return any(_search(child) for child in node.children)

    return _search(tree.root_node)


def _is_noise_symbol(raw: dict) -> bool:
    """Detect tsserver-synthesized noise symbols that should not be indexed.

    tsserver reports arrow-function callbacks (.map(), forEach(), describe(), it(), etc.)
    as children with names ending in " callback". It also synthesizes "<unknown>" for
    anonymous JSX fragments, and uses array-literal content (e.g. "[1, 2, 3]") as names
    for inline expressions.  In JSX/TSX files tsserver also reports string-literal attribute
    values (CSS classes, SVG paths, UI text) as Property symbols whose name is the quoted
    string itself.  None of these are meaningful structural symbols.
    """
    name = raw.get("name", "")
    if not name or name == "<unknown>":
        return True
    if name.endswith(" callback"):
        return True
    if name.startswith("["):
        return True
    # String literals surfaced as symbol names (CSS classes, SVG paths, UI text)
    if name[0] in ('"', "'", "`"):
        return True
    return False


def _build_ts_full_name(raw: dict, file_path: str, root_path: str) -> str:
    """Build a forward-slash path-prefixed full name from file path + symbol parent chain.

    Result format: src/services/auth.AuthService.login
    Uses forward slashes on all platforms for consistent graph node identity.
    """
    rel = os.path.relpath(file_path, root_path)
    # Strip extension and convert OS separators to forward slashes
    path_prefix = Path(rel).with_suffix("").as_posix()
    suffix = symbol_suffix(raw)
    if suffix:
        return f"{path_prefix}.{suffix}"
    return path_prefix


class TypeScriptLSPAdapter:
    """Wraps a TypeScriptLanguageServer instance to provide the LSPAdapter interface."""

    file_extensions: frozenset[str] = _TS_EXTENSIONS

    def __init__(self, language_server: LSPResolverBackend, root_path: str) -> None:
        self._ls = language_server
        self._root_path = root_path

    @property
    def language_server(self) -> LSPResolverBackend:
        return self._ls

    @classmethod
    def create(cls, root_path: str) -> TypeScriptLSPAdapter:
        """Start TypeScriptLanguageServer and return a ready adapter."""
        from solidlsp.language_servers.typescript_language_server import TypeScriptLanguageServer
        from solidlsp.ls_config import Language, LanguageServerConfig
        from solidlsp.settings import SolidLSPSettings

        config = LanguageServerConfig(code_language=Language.TYPESCRIPT)
        ls = TypeScriptLanguageServer(
            config=config,
            repository_root_path=root_path,
            solidlsp_settings=SolidLSPSettings(),
        )
        ls.start()
        return cls(ls, root_path)

    def get_workspace_files(self, root_path: str) -> list[str]:
        from synapps.util.file_system import load_synignore

        synignore = load_synignore(root_path)
        files: list[str] = []
        for path in Path(root_path).rglob("*"):
            if path.suffix.lower() in _TS_EXTENSIONS:
                if not any(part in _EXCLUDE_DIRS for part in path.parts):
                    if not path.name.endswith(_EXCLUDE_FILE_SUFFIXES):
                        abs_path = str(path)
                        if synignore is not None and synignore.is_file_ignored(abs_path):
                            continue
                        files.append(abs_path)
        return files

    def get_document_symbols(self, file_path: str) -> list[IndexSymbol]:
        try:
            rel_path = os.path.relpath(file_path, self._root_path)
            raw_result = self._ls.request_document_symbols(rel_path)
            if raw_result is None:
                return []
            # Parse once per file; passed to _traverse so arrow-function detection
            # doesn't re-parse the file for every top-level Variable/Constant symbol.
            ts_tree = _parse_ts_file(file_path)
            result: list[IndexSymbol] = []
            for root_sym in raw_result.root_symbols:
                self._traverse(root_sym, file_path, parent_full_name=None, result=result, ts_tree=ts_tree)
            return result
        except Exception:
            log.exception("Failed to get symbols for %s", file_path)
            return []

    def _traverse(
        self,
        raw: dict,
        file_path: str,
        parent_full_name: str | None,
        result: list[IndexSymbol],
        ts_tree: tree_sitter.Tree | None = None,
    ) -> None:
        if _is_noise_symbol(raw):
            return
        sym = self._convert(raw, file_path, self._root_path, parent_full_name=parent_full_name)
        if sym is not None:
            result.append(sym)
            for child in raw.get("children", []):
                self._traverse(child, file_path, parent_full_name=sym.full_name, result=result, ts_tree=ts_tree)
        elif raw.get("kind", 0) in (13, 14) and parent_full_name is None:
            # Top-level Variable/Constant — may be an arrow function component, hook,
            # or utility that TSServer reports with zero or more children.
            children = raw.get("children") or []
            if children:
                # Has children: distinguish object literals from arrow functions.
                #   - Children include Method/Function (kind 6/12) → object literal → CLASS
                #   - No Method/Function children → arrow function/component → METHOD
                _METHOD_KINDS = {6, 12}
                has_method_children = any(c.get("kind", 0) in _METHOD_KINDS for c in children)
                if has_method_children:
                    sym = self._convert_as_class(raw, file_path, self._root_path, parent_full_name)
                else:
                    sym = self._convert_as_method(raw, file_path, self._root_path, parent_full_name)
            else:
                # No children: TSServer omits children for simple arrow functions whose
                # bodies contain no nested const/property symbols (e.g. single-expression
                # or if/return-only bodies).  Use tree-sitter to confirm the declarator's
                # value really is an arrow_function before promoting to METHOD.
                sel_range = raw.get("selectionRange", raw.get("location", {}).get("range", {}))
                line_0 = sel_range.get("start", {}).get("line", -1)
                if ts_tree is not None and line_0 >= 0 and _is_arrow_function_at_line(ts_tree, line_0):
                    sym = self._convert_as_method(raw, file_path, self._root_path, parent_full_name)
                else:
                    sym = None
            if sym is not None:
                result.append(sym)
                for child in children:
                    self._traverse(child, file_path, parent_full_name=sym.full_name, result=result, ts_tree=ts_tree)

    def _convert(
        self,
        raw: dict,
        file_path: str,
        root_path: str,
        parent_full_name: str | None,
    ) -> IndexSymbol | None:
        kind_int = raw.get("kind", 0)
        kind = _LSP_KIND_MAP.get(kind_int)
        if kind is None:
            log.debug("Skipping LSP SymbolKind %d for symbol %s", kind_int, raw.get("name", "?"))
            return None

        name = raw.get("name", "")
        range_obj = raw.get("location", {}).get("range", {})
        sel_range = raw.get("selectionRange", range_obj)
        line = sel_range.get("start", {}).get("line", 0) + 1
        col = sel_range.get("start", {}).get("character", 0)
        end_line = range_obj.get("end", {}).get("line", 0) + 1

        # Signature carries 'module' marker for ES module symbols (kind 2).
        signature = "module" if kind_int == 2 else ""

        return IndexSymbol(
            name=name,
            full_name=_build_ts_full_name(raw, file_path, root_path),
            kind=kind,
            file_path=file_path,
            line=line,
            end_line=end_line,
            col=col,
            signature=signature,
            parent_full_name=parent_full_name,
        )

    def _convert_as_method(
        self,
        raw: dict,
        file_path: str,
        root_path: str,
        parent_full_name: str | None,
    ) -> IndexSymbol:
        """Convert a Variable/Constant symbol to METHOD for arrow functions, components, and hooks."""
        name = raw.get("name", "")
        range_obj = raw.get("location", {}).get("range", {})
        sel_range = raw.get("selectionRange", range_obj)
        line = sel_range.get("start", {}).get("line", 0) + 1
        col = sel_range.get("start", {}).get("character", 0)
        end_line = range_obj.get("end", {}).get("line", 0) + 1
        return IndexSymbol(
            name=name,
            full_name=_build_ts_full_name(raw, file_path, root_path),
            kind=SymbolKind.METHOD,
            file_path=file_path,
            line=line,
            end_line=end_line,
            col=col,
            signature="const_function",
            parent_full_name=parent_full_name,
        )

    def _convert_as_class(
        self,
        raw: dict,
        file_path: str,
        root_path: str,
        parent_full_name: str | None,
    ) -> IndexSymbol:
        """Convert a Variable/Constant symbol to CLASS for object literals with methods."""
        name = raw.get("name", "")
        range_obj = raw.get("location", {}).get("range", {})
        sel_range = raw.get("selectionRange", range_obj)
        line = sel_range.get("start", {}).get("line", 0) + 1
        col = sel_range.get("start", {}).get("character", 0)
        end_line = range_obj.get("end", {}).get("line", 0) + 1
        return IndexSymbol(
            name=name,
            full_name=_build_ts_full_name(raw, file_path, root_path),
            kind=SymbolKind.CLASS,
            file_path=file_path,
            line=line,
            end_line=end_line,
            col=col,
            signature="const_object",
            parent_full_name=parent_full_name,
        )

    def find_method_calls(self, symbol: IndexSymbol) -> list[str]:
        return []

    def find_overridden_method(self, symbol: IndexSymbol) -> str | None:
        return None

    def shutdown(self) -> None:
        self._ls.stop()
