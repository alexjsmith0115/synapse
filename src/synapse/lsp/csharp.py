from __future__ import annotations

import logging
import os
from pathlib import Path
from urllib.parse import urlparse

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


def _build_full_name(raw: dict) -> str:
    """Build a fully-qualified name by walking the parent chain of a UnifiedSymbolInformation."""
    name = raw.get("name", "")
    parent = raw.get("parent")
    base = f"{_build_full_name(parent)}.{name}" if parent is not None else name
    if "overload_idx" in raw:
        detail = raw.get("detail", "") or ""
        if "(" in detail:
            return f"{base}{detail[detail.index('('):]}"
    return base


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
            if raw is None:
                return []
            return [self._convert(s, file_path) for s in raw.iter_symbols()]
        except Exception:
            log.exception("Failed to get symbols for %s", file_path)
            return []

    def find_method_calls(self, symbol: IndexSymbol) -> list[str]:
        # solidlsp exposes outgoing call hierarchy via server.send.prepare_call_hierarchy +
        # server.send.outgoing_calls (LSP 3.16 callHierarchy/outgoingCalls), but the returned
        # CallHierarchyItem dicts contain no full_name and would require cross-file symbol
        # resolution to produce qualified names. This is a known limitation, not a bug.
        log.warning(
            "find_method_calls is not implemented: solidlsp call hierarchy returns raw LSP dicts "
            "without qualified full_names; outgoing call resolution requires cross-file symbol lookup "
            "not yet supported by this adapter. Returning [] for %s",
            symbol.full_name,
        )
        return []

    def find_overridden_method(self, symbol: IndexSymbol) -> str | None:
        if "override" not in symbol.signature.lower():
            return None
        try:
            root = self._ls.repository_root_path
            rel_path = os.path.relpath(symbol.file_path, root)

            class_sym = self._ls.request_containing_symbol(rel_path, symbol.line, 0)
            if class_sym is None:
                return None

            class_loc = class_sym.get("location", {})
            class_uri = class_loc.get("uri", "")
            class_start = class_loc.get("range", {}).get("start", {})

            items = self._ls.server.send.prepare_type_hierarchy({
                "textDocument": {"uri": class_uri},
                "position": class_start,
            })
            if not items:
                return None

            for item in items:
                supertypes = self._ls.server.send.type_hierarchy_supertypes({"item": item})
                if not supertypes:
                    continue
                for supertype in supertypes:
                    abs_path = urlparse(supertype.get("uri", "")).path
                    if not abs_path:
                        continue
                    super_rel = os.path.relpath(abs_path, root)
                    doc_syms = self._ls.request_document_symbols(super_rel)
                    if doc_syms is None:
                        continue
                    for s in doc_syms.iter_symbols():
                        if s.get("name") == symbol.name:
                            return _build_full_name(s)
            return None
        except Exception:
            log.exception("Failed to find overridden method for %s", symbol.full_name)
            return None

    def shutdown(self) -> None:
        try:
            self._ls.shutdown()
        except Exception:
            log.warning("Language server did not shut down cleanly")

    def _convert(self, raw: dict, file_path: str) -> IndexSymbol:
        kind_int = raw.get("kind", 0)
        kind = _LSP_KIND_MAP.get(kind_int)
        if kind is None:
            log.debug("Unmapped LSP SymbolKind %d for symbol %s, defaulting to CLASS", kind_int, raw.get("name", "?"))
            kind = SymbolKind.CLASS
        name = raw.get("name", "")
        line = raw.get("location", {}).get("range", {}).get("start", {}).get("line", 0)
        detail = raw.get("detail", "") or ""
        return IndexSymbol(
            name=name,
            full_name=_build_full_name(raw),
            kind=kind,
            file_path=file_path,
            line=line,
            signature=raw.get("detail", "") or "",
            is_abstract="abstract" in detail.lower(),
            is_static="static" in detail.lower(),
        )
