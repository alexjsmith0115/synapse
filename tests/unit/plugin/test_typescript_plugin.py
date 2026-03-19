"""Tests for TypeScriptPlugin and default_registry TypeScript registration."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from synapse.plugin import LanguagePlugin, default_registry


def test_name_returns_typescript() -> None:
    from synapse.plugin.typescript import TypeScriptPlugin
    assert TypeScriptPlugin().name == "typescript"


def test_file_extensions_returns_all_eight() -> None:
    from synapse.plugin.typescript import TypeScriptPlugin
    assert TypeScriptPlugin().file_extensions == frozenset({
        ".ts", ".tsx", ".js", ".jsx", ".mts", ".cts", ".mjs", ".cjs"
    })


def test_is_language_plugin() -> None:
    from synapse.plugin.typescript import TypeScriptPlugin
    assert isinstance(TypeScriptPlugin(), LanguagePlugin)


def test_create_lsp_adapter_delegates_to_typescript_adapter(tmp_path) -> None:
    from synapse.plugin.typescript import TypeScriptPlugin

    with patch("synapse.lsp.typescript.TypeScriptLSPAdapter.create") as mock_create:
        mock_adapter = mock_create.return_value
        result = TypeScriptPlugin().create_lsp_adapter(str(tmp_path))
        mock_create.assert_called_once_with(str(tmp_path))
        assert result is mock_adapter


def test_create_call_extractor_returns_typescript_call_extractor() -> None:
    from synapse.plugin.typescript import TypeScriptPlugin
    from synapse.indexer.typescript_call_extractor import TypeScriptCallExtractor
    result = TypeScriptPlugin().create_call_extractor()
    assert isinstance(result, TypeScriptCallExtractor)


def test_create_import_extractor_returns_typescript_import_extractor() -> None:
    from synapse.plugin.typescript import TypeScriptPlugin
    from synapse.indexer.typescript_import_extractor import TypeScriptImportExtractor
    result = TypeScriptPlugin().create_import_extractor(source_root="src")
    assert isinstance(result, TypeScriptImportExtractor)


def test_create_base_type_extractor_returns_typescript_base_type_extractor() -> None:
    from synapse.plugin.typescript import TypeScriptPlugin
    from synapse.indexer.typescript_base_type_extractor import TypeScriptBaseTypeExtractor
    result = TypeScriptPlugin().create_base_type_extractor()
    assert isinstance(result, TypeScriptBaseTypeExtractor)


def test_create_attribute_extractor_returns_typescript_attribute_extractor() -> None:
    from synapse.plugin.typescript import TypeScriptPlugin
    from synapse.indexer.typescript_attribute_extractor import TypeScriptAttributeExtractor
    result = TypeScriptPlugin().create_attribute_extractor()
    assert isinstance(result, TypeScriptAttributeExtractor)


def test_create_type_ref_extractor_returns_typescript_type_ref_extractor() -> None:
    from synapse.plugin.typescript import TypeScriptPlugin
    from synapse.indexer.typescript_type_ref_extractor import TypeScriptTypeRefExtractor
    result = TypeScriptPlugin().create_type_ref_extractor()
    assert isinstance(result, TypeScriptTypeRefExtractor)


def test_default_registry_includes_typescript() -> None:
    registry = default_registry()
    assert registry.get("typescript") is not None


def test_detect_returns_typescript_for_ts_directory(tmp_path) -> None:
    (tmp_path / "index.ts").write_text("export const x = 1;")
    registry = default_registry()
    result = registry.detect(str(tmp_path))
    names = [p.name for p in result]
    assert "typescript" in names
