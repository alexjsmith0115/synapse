from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from synapps.lsp.interface import IndexSymbol, LSPAdapter, LSPResolverBackend, SymbolKind
from synapps.lsp.util import symbol_suffix

log = logging.getLogger(__name__)

# Maps LSP SymbolKind integers to Synapps SymbolKind.
# Key user decision: LSP kind 2 (Module) -> SymbolKind.CLASS (NOT NAMESPACE).
# This ensures Module symbols become :Class nodes with kind='module' in the graph,
# per locked decision "MODULE -> :Class with kind='module'".
_LSP_KIND_MAP: dict[int, SymbolKind | None] = {
    2: SymbolKind.CLASS,      # Module -> :Class with kind='module' (per user decision)
    3: SymbolKind.NAMESPACE,  # Namespace
    5: SymbolKind.CLASS,      # Class
    6: SymbolKind.METHOD,     # Method
    7: SymbolKind.PROPERTY,   # Property
    8: SymbolKind.FIELD,      # Field
    9: SymbolKind.METHOD,     # Constructor (__init__)
    12: SymbolKind.METHOD,    # Function (standalone)
    14: None,                 # Constant -> skip in v1
}

_RE_IMPORT_NAME = re.compile(r"^\s*from\s+\S+\s+import\s+(.+)", re.MULTILINE)


def detect_source_root(file_path: str, project_root: str) -> str:
    """Walk up from file's directory; source root is the first directory without __init__.py."""
    current = Path(file_path).parent
    project = Path(project_root)
    while current != project.parent:
        if not (current / "__init__.py").exists():
            return str(current)
        current = current.parent
    return str(project)


def _build_python_full_name(raw: dict, file_path: str, source_root: str) -> str:
    """Build a module-qualified full name from file path + symbol parent chain."""
    rel = os.path.relpath(file_path, source_root)
    module_prefix = rel.replace(os.sep, ".").removesuffix(".py").removesuffix(".__init__")
    suffix = symbol_suffix(raw)
    if suffix:
        return f"{module_prefix}.{suffix}"
    return module_prefix


def _parse_reexported_names(source: str) -> set[str]:
    """Extract names imported via 'from ... import ...' in __init__.py source."""
    names: set[str] = set()
    for match in _RE_IMPORT_NAME.finditer(source):
        imports_str = match.group(1)
        # Handle parenthesised multi-line imports by stripping parens/newlines
        imports_str = imports_str.strip("() \t\n")
        for part in imports_str.split(","):
            name = part.strip().split(" as ")[0].strip()
            if name:
                names.add(name)
    return names


class PythonLSPAdapter:
    """Wraps a PyrightServer instance to provide the LSPAdapter interface for Python."""

    file_extensions: frozenset[str] = frozenset({".py"})

    def __init__(self, language_server: LSPResolverBackend, root_path: str) -> None:
        self._ls = language_server
        self._root_path = root_path
        self._source_root: str | None = None

    @property
    def language_server(self) -> LSPResolverBackend:
        return self._ls

    @classmethod
    def create(cls, root_path: str) -> PythonLSPAdapter:
        """Start PyrightServer, wait for analysis_complete, return a ready adapter (PLSP-02)."""
        from solidlsp.language_servers.pyright_server import PyrightServer
        from solidlsp.ls_config import Language, LanguageServerConfig
        from solidlsp.settings import SolidLSPSettings

        config = LanguageServerConfig(code_language=Language.PYTHON)
        ls = PyrightServer(
            config=config,
            repository_root_path=root_path,
            solidlsp_settings=SolidLSPSettings(),
        )
        ls.start()
        return cls(ls, root_path)

    def get_workspace_files(self, root_path: str) -> list[str]:
        from synapps.util.file_system import load_synignore

        _exclude = {"__pycache__", ".venv", "venv", ".git", "node_modules"}
        synignore = load_synignore(root_path)
        files: list[str] = []
        for path in Path(root_path).rglob("*.py"):
            if not any(part in _exclude for part in path.parts):
                abs_path = str(path)
                if synignore is not None and synignore.is_file_ignored(abs_path):
                    continue
                files.append(abs_path)
        return files

    def get_document_symbols(self, file_path: str) -> list[IndexSymbol]:
        if self._source_root is None:
            self._source_root = detect_source_root(file_path, self._root_path)

        reexported: set[str] = set()
        if Path(file_path).name == "__init__.py":
            try:
                source = Path(file_path).read_text(encoding="utf-8")
                reexported = _parse_reexported_names(source)
            except OSError:
                pass

        try:
            rel_path = os.path.relpath(file_path, self._root_path)
            raw_result = self._ls.request_document_symbols(rel_path)
            if raw_result is None:
                return []
            result: list[IndexSymbol] = []
            for root_sym in raw_result.root_symbols:
                self._traverse(root_sym, file_path, parent_full_name=None, result=result,
                               reexported=reexported)
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
        reexported: set[str],
    ) -> None:
        sym = self._convert(raw, file_path, self._source_root or self._root_path,
                            parent_full_name=parent_full_name)
        if sym is not None:
            if reexported and sym.name in reexported and parent_full_name is None:
                # Skip re-exported top-level symbols in __init__.py
                return
            result.append(sym)
            for child in raw.get("children", []):
                self._traverse(child, file_path, parent_full_name=sym.full_name,
                               result=result, reexported=reexported)

    def _convert(
        self,
        raw: dict,
        file_path: str,
        source_root: str,
        parent_full_name: str | None,
    ) -> IndexSymbol | None:
        kind_int = raw.get("kind", 0)
        kind = _LSP_KIND_MAP.get(kind_int)
        if kind is None:
            log.debug("Skipping LSP SymbolKind %d for symbol %s", kind_int, raw.get("name", "?"))
            return None

        name = raw.get("name", "")
        range_obj = raw.get("location", {}).get("range", {})
        line = range_obj.get("start", {}).get("line", 0) + 1
        end_line = range_obj.get("end", {}).get("line", 0) + 1

        # Signature carries 'module' marker for LSP kind 2 so Plan 04 can call upsert_class(kind='module').
        signature = "module" if kind_int == 2 else raw.get("detail", "") or ""

        return IndexSymbol(
            name=name,
            full_name=_build_python_full_name(raw, file_path, source_root),
            kind=kind,
            file_path=file_path,
            line=line,
            end_line=end_line,
            signature=signature,
            parent_full_name=parent_full_name,
        )

    def find_method_calls(self, symbol: IndexSymbol) -> list[str]:
        return []

    def find_overridden_method(self, symbol: IndexSymbol) -> str | None:
        return None

    def shutdown(self) -> None:
        self._ls.stop()
