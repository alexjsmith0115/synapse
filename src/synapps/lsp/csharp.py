from __future__ import annotations

import logging
from pathlib import Path

from synapps.lsp.interface import IndexSymbol, LSPAdapter, LSPResolverBackend, SymbolKind
from synapps.lsp.util import build_full_name

log = logging.getLogger(__name__)

# Maps LSP SymbolKind integers to our SymbolKind enum
# https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#symbolKind
_LSP_KIND_MAP: dict[int, SymbolKind] = {
    3: SymbolKind.NAMESPACE,
    5: SymbolKind.CLASS,
    11: SymbolKind.INTERFACE,
    10: SymbolKind.ENUM,
    6: SymbolKind.METHOD,
    7: SymbolKind.PROPERTY,
    8: SymbolKind.FIELD,
    9: SymbolKind.METHOD,  # Constructor → Method
    12: SymbolKind.METHOD,  # Function → Method
}



class CSharpLSPAdapter:
    """Wraps a SolidLanguageServer instance to provide the LSPAdapter interface for C#."""

    file_extensions: frozenset[str] = frozenset({".cs"})

    def __init__(self, language_server: LSPResolverBackend) -> None:
        self._ls = language_server

    @property
    def language_server(self) -> LSPResolverBackend:
        return self._ls

    @classmethod
    def create(cls, root_path: str) -> CSharpLSPAdapter:
        """Start the C# language server and return a ready adapter."""
        from solidlsp.language_servers.csharp_language_server import CSharpLanguageServer
        from solidlsp.ls_config import Language, LanguageServerConfig
        from solidlsp.settings import SolidLSPSettings

        config = LanguageServerConfig(code_language=Language.CSHARP)
        settings = SolidLSPSettings()
        ls = CSharpLanguageServer(config=config, repository_root_path=root_path, solidlsp_settings=settings)
        ls.start()
        return cls(ls)

    def get_workspace_files(self, root_path: str) -> list[str]:
        from synapps.util.file_system import load_synignore

        synignore = load_synignore(root_path)
        files = []
        for path in Path(root_path).rglob("*.cs"):
            if ".git" not in path.parts and "bin" not in path.parts and "obj" not in path.parts:
                abs_path = str(path)
                if synignore is not None and synignore.is_file_ignored(abs_path):
                    continue
                files.append(abs_path)
        return files

    def get_document_symbols(self, file_path: str) -> list[IndexSymbol]:
        try:
            raw = self._ls.request_document_symbols(file_path)
            if raw is None:
                return []
            result: list[IndexSymbol] = []
            for root in raw.root_symbols:
                self._traverse(root, file_path, parent_full_name=None, result=result)
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
    ) -> None:
        sym = self._convert(raw, file_path, parent_full_name)
        result.append(sym)
        for child in raw.get("children", []):
            self._traverse(child, file_path, parent_full_name=sym.full_name, result=result)

    def find_method_calls(self, symbol: IndexSymbol) -> list[str]:
        return []

    def find_overridden_method(self, symbol: IndexSymbol) -> str | None:
        return None

    def shutdown(self) -> None:
        self._ls.stop()

    def _convert(self, raw: dict, file_path: str, parent_full_name: str | None) -> IndexSymbol:
        kind_int = raw.get("kind", 0)
        kind = _LSP_KIND_MAP.get(kind_int)
        if kind is None:
            log.debug("Unmapped LSP SymbolKind %d for symbol %s, defaulting to CLASS", kind_int, raw.get("name", "?"))
            kind = SymbolKind.CLASS
        name = raw.get("name", "")
        range_obj = raw.get("location", {}).get("range", {})
        line = range_obj.get("start", {}).get("line", 0) + 1
        end_line = range_obj.get("end", {}).get("line", 0) + 1
        detail = raw.get("detail", "") or ""
        return IndexSymbol(
            name=name,
            full_name=build_full_name(raw),
            kind=kind,
            file_path=file_path,
            line=line,
            end_line=end_line,
            signature=detail,
            is_abstract="abstract" in detail.lower(),
            is_static="static" in detail.lower(),
            parent_full_name=parent_full_name,
        )
