from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from synapse.lsp.interface import LSPAdapter


@runtime_checkable
class LanguagePlugin(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def file_extensions(self) -> frozenset[str]: ...

    def create_lsp_adapter(self, root_path: str) -> LSPAdapter: ...

    def create_call_extractor(self): ...

    def create_import_extractor(self): ...

    def create_base_type_extractor(self): ...

    def create_attribute_extractor(self): ...

    def create_type_ref_extractor(self): ...


class LanguageRegistry:
    def __init__(self) -> None:
        self._plugins: list[LanguagePlugin] = []

    def register(self, plugin: LanguagePlugin) -> None:
        self._plugins.append(plugin)

    def get(self, name: str) -> LanguagePlugin | None:
        return next((p for p in self._plugins if p.name == name), None)

    def detect(self, root_path: str) -> list[LanguagePlugin]:
        found_extensions = {
            path.suffix.lower()
            for path in Path(root_path).rglob("*")
            if path.is_file()
        }
        return [p for p in self._plugins if p.file_extensions & found_extensions]

    def all_extensions(self) -> frozenset[str]:
        result: set[str] = set()
        for plugin in self._plugins:
            result |= plugin.file_extensions
        return frozenset(result)


def default_registry() -> LanguageRegistry:
    from synapse.plugin.csharp import CSharpPlugin
    from synapse.plugin.python import PythonPlugin

    registry = LanguageRegistry()
    registry.register(CSharpPlugin())
    registry.register(PythonPlugin())
    return registry
