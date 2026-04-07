from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable


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
    is_classmethod: bool = False
    is_async: bool = False
    base_types: list[str] = field(default_factory=list)
    """Full names of base classes or implemented interfaces."""
    parent_full_name: str | None = None
    """full_name of the enclosing symbol, or None if top-level in the file."""
    type_name: str = ""
    """Declared type for FIELD symbols (e.g. "IAnimal"); empty string for all other kinds."""


@runtime_checkable
class LSPAdapter(Protocol):
    file_extensions: frozenset[str]
    """File extensions handled by this adapter (e.g. frozenset({".cs"}))."""

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


class LSPResolverBackend(Protocol):
    """Raw LSP server interface used by SymbolResolver for call and reference resolution."""

    repository_root_path: str

    def open_file(self, relative_file_path: str) -> AbstractContextManager[Any]:
        """Open a file in the language server (context manager)."""
        ...

    def request_definition(self, relative_file_path: str, line: int, column: int) -> list[Any]:
        """Return definition locations for the symbol at the given position."""
        ...

    def request_containing_symbol(
        self, relative_file_path: str, line: int, column: int | None = None, strict: bool = False,
    ) -> Any:
        """Return the symbol containing the given position, or None."""
        ...

    def request_defining_symbol(
        self, relative_file_path: str, line: int, column: int, include_body: bool = False,
    ) -> Any:
        """Return the symbol that defines the symbol at the given position, or None."""
        ...

    def request_references(self, relative_file_path: str, line: int, column: int) -> list[Any]:
        """Return reference locations for the symbol at the given position."""
        ...

    def set_request_timeout(self, timeout: float | None) -> None:
        """Set per-request timeout for LSP calls. None disables timeout."""
        ...
