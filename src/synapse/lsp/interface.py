from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable


class SymbolKind(str, Enum):
    NAMESPACE = "namespace"
    CLASS = "class"
    INTERFACE = "interface"
    ABSTRACT_CLASS = "abstract_class"
    ENUM = "enum"
    RECORD = "record"
    METHOD = "method"
    PROPERTY = "property"
    FIELD = "field"


@dataclass
class IndexSymbol:
    name: str
    full_name: str
    kind: SymbolKind
    file_path: str
    line: int
    end_line: int = 0
    signature: str = ""
    is_abstract: bool = False
    is_static: bool = False
    base_types: list[str] = field(default_factory=list)
    """Full names of base classes or implemented interfaces."""
    parent_full_name: str | None = None
    """full_name of the enclosing symbol, or None if top-level in the file."""


@runtime_checkable
class LSPAdapter(Protocol):
    def get_workspace_files(self, root_path: str) -> list[str]:
        """Return absolute paths of all source files in the workspace."""
        ...

    def get_document_symbols(self, file_path: str) -> list[IndexSymbol]:
        """Return all symbols declared in the given file."""
        ...

    def find_method_calls(self, symbol: IndexSymbol) -> list[str]:
        """Return full_names of methods called by the given method symbol."""
        ...

    def find_overridden_method(self, symbol: IndexSymbol) -> str | None:
        """Return full_name of the base method that this method overrides, or None."""
        ...

    def shutdown(self) -> None:
        """Shut down the language server process."""
        ...
