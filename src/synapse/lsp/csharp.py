from __future__ import annotations

import logging
from pathlib import Path

from synapse.lsp.interface import IndexSymbol, LSPAdapter, SymbolKind

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

    def __init__(self, language_server: object) -> None:
        self._ls = language_server

    @classmethod
    def create(cls, root_path: str) -> CSharpLSPAdapter:
        """Start the C# language server and return a ready adapter."""
        from solidlsp.language_servers.csharp_language_server import CSharpLanguageServer
        from solidlsp.ls_config import Language, LanguageServerConfig
        from solidlsp.settings import SolidLSPSettings

        config = LanguageServerConfig(
            language=Language.CSharp,
            project_root=root_path,
        )
        settings = SolidLSPSettings()
        ls = CSharpLanguageServer(config=config, settings=settings)
        ls.start()
        return cls(ls)

    def get_workspace_files(self, root_path: str) -> list[str]:
        files = []
        for path in Path(root_path).rglob("*.cs"):
            if ".git" not in path.parts and "bin" not in path.parts and "obj" not in path.parts:
                files.append(str(path))
        return files

    def get_document_symbols(self, file_path: str) -> list[IndexSymbol]:
        try:
            raw = self._ls.request_document_symbols(file_path)
            return [self._convert(s, file_path) for s in (raw or [])]
        except Exception:
            log.exception("Failed to get symbols for %s", file_path)
            return []

    def find_method_calls(self, symbol: IndexSymbol) -> list[str]:
        # Resolve via references: find all outgoing calls from this method's location
        try:
            refs = self._ls.find_references(symbol.file_path, symbol.line, 0, include_declaration=False)
            return [r.full_name for r in (refs or []) if hasattr(r, "full_name")]
        except Exception:
            log.exception("Failed to find calls for %s", symbol.full_name)
            return []

    def find_overridden_method(self, symbol: IndexSymbol) -> str | None:
        try:
            result = self._ls.go_to_definition(symbol.file_path, symbol.line, 0)
            if result and hasattr(result, "full_name"):
                return result.full_name
            return None
        except Exception:
            return None

    def shutdown(self) -> None:
        try:
            self._ls.shutdown()
        except Exception:
            log.warning("Language server did not shut down cleanly")

    def _convert(self, raw: object, file_path: str) -> IndexSymbol:
        kind_int = getattr(raw, "kind", 0)
        kind = _LSP_KIND_MAP.get(kind_int, SymbolKind.CLASS)
        return IndexSymbol(
            name=getattr(raw, "name", ""),
            full_name=getattr(raw, "full_name", "") or getattr(raw, "name", ""),
            kind=kind,
            file_path=file_path,
            line=getattr(raw, "line", 0),
            signature=getattr(raw, "signature", ""),
            is_abstract="abstract" in getattr(raw, "detail", "").lower(),
            is_static="static" in getattr(raw, "detail", "").lower(),
        )
