from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol, runtime_checkable

from synapse.indexer.tree_sitter_util import ParsedFile
from synapse.lsp.interface import LSPAdapter


_ALWAYS_SKIP = frozenset({
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "bin", "obj", "dist", "build", ".gradle", ".idea", "target",
    "coverage", ".settings", ".mvn", ".next", ".nuxt", "out",
    ".cache", ".angular", ".svelte-kit",
})


@runtime_checkable
class LanguagePlugin(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def file_extensions(self) -> frozenset[str]: ...

    def create_lsp_adapter(self, root_path: str) -> LSPAdapter: ...

    def create_call_extractor(self): ...

    def create_import_extractor(self, source_root: str = ""): ...

    def create_base_type_extractor(self): ...

    def create_attribute_extractor(self): ...

    def create_type_ref_extractor(self) -> object | None: ...

    def create_assignment_extractor(self) -> object | None: ...

    def parse_file(self, file_path: str, source: str) -> ParsedFile: ...


class LanguageRegistry:
    def __init__(self) -> None:
        self._plugins: list[LanguagePlugin] = []

    def register(self, plugin: LanguagePlugin) -> None:
        self._plugins.append(plugin)

    def get(self, name: str) -> LanguagePlugin | None:
        return next((p for p in self._plugins if p.name == name), None)

    def detect_with_files(self, root_path: str) -> list[tuple[LanguagePlugin, list[str]]]:
        ext_to_plugins: dict[str, list[LanguagePlugin]] = {}
        for p in self._plugins:
            for ext in p.file_extensions:
                ext_to_plugins.setdefault(ext, []).append(p)

        files_by_plugin: dict[str, list[str]] = {p.name: [] for p in self._plugins}
        for dirpath, dirnames, filenames in os.walk(root_path):
            dirnames[:] = [d for d in dirnames if d not in _ALWAYS_SKIP]
            for fname in filenames:
                ext = os.path.splitext(fname)[1].lower()
                for plugin in ext_to_plugins.get(ext, []):
                    full_path = os.path.join(dirpath, fname)
                    excluded = getattr(plugin, "excluded_suffixes", frozenset())
                    if not any(fname.endswith(s) for s in excluded):
                        files_by_plugin[plugin.name].append(full_path)

        return [(p, files_by_plugin[p.name]) for p in self._plugins if files_by_plugin[p.name]]

    def detect(self, root_path: str) -> list[LanguagePlugin]:
        return [p for p, _files in self.detect_with_files(root_path)]

    def all_extensions(self) -> frozenset[str]:
        result: set[str] = set()
        for plugin in self._plugins:
            result |= plugin.file_extensions
        return frozenset(result)


def default_registry() -> LanguageRegistry:
    from synapse.plugin.csharp import CSharpPlugin
    from synapse.plugin.java import JavaPlugin
    from synapse.plugin.python import PythonPlugin
    from synapse.plugin.typescript import TypeScriptPlugin

    registry = LanguageRegistry()
    registry.register(CSharpPlugin())
    registry.register(PythonPlugin())
    registry.register(TypeScriptPlugin())
    registry.register(JavaPlugin())
    return registry
