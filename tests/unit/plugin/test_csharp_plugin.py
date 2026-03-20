from __future__ import annotations

from unittest.mock import patch

import pytest

from synapse.plugin import LanguagePlugin
from synapse.plugin.csharp import CSharpPlugin
from synapse.indexer.attribute_extractor import CSharpAttributeExtractor
from synapse.indexer.base_type_extractor import CSharpBaseTypeExtractor
from synapse.indexer.call_extractor import TreeSitterCallExtractor
from synapse.indexer.import_extractor import CSharpImportExtractor
from synapse.indexer.type_ref_extractor import TreeSitterTypeRefExtractor


def test_name_returns_csharp():
    assert CSharpPlugin().name == "csharp"


def test_file_extensions_returns_cs():
    assert CSharpPlugin().file_extensions == frozenset({".cs"})


def test_is_language_plugin():
    assert isinstance(CSharpPlugin(), LanguagePlugin)


def test_create_import_extractor_returns_csharp_type():
    extractor = CSharpPlugin().create_import_extractor()
    assert isinstance(extractor, CSharpImportExtractor)


def test_create_base_type_extractor_returns_csharp_type():
    extractor = CSharpPlugin().create_base_type_extractor()
    assert isinstance(extractor, CSharpBaseTypeExtractor)


def test_create_call_extractor_returns_tree_sitter_type():
    extractor = CSharpPlugin().create_call_extractor()
    assert isinstance(extractor, TreeSitterCallExtractor)


def test_create_attribute_extractor_returns_csharp_type():
    extractor = CSharpPlugin().create_attribute_extractor()
    assert isinstance(extractor, CSharpAttributeExtractor)


def test_create_type_ref_extractor_returns_tree_sitter_type():
    extractor = CSharpPlugin().create_type_ref_extractor()
    assert isinstance(extractor, TreeSitterTypeRefExtractor)


def test_create_lsp_adapter_delegates_to_csharp_adapter():
    with patch("synapse.lsp.csharp.CSharpLSPAdapter.create") as mock_create:
        mock_adapter = mock_create.return_value
        result = CSharpPlugin().create_lsp_adapter("/path/to/project")
        mock_create.assert_called_once_with("/path/to/project")
        assert result is mock_adapter


def test_missing_tree_sitter_raises_module_not_found():
    with patch.dict("sys.modules", {"tree_sitter_c_sharp": None}):
        plugin = CSharpPlugin()
        with pytest.raises(ModuleNotFoundError):
            plugin.create_import_extractor()
