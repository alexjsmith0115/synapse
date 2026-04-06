from __future__ import annotations

from unittest.mock import patch

import pytest

from synapps.plugin import LanguagePlugin
from synapps.plugin.csharp import CSharpPlugin
from synapps.indexer.csharp.csharp_attribute_extractor import CSharpAttributeExtractor
from synapps.indexer.csharp.csharp_base_type_extractor import CSharpBaseTypeExtractor
from synapps.indexer.csharp.csharp_call_extractor import CSharpCallExtractor
from synapps.indexer.csharp.csharp_import_extractor import CSharpImportExtractor
from synapps.indexer.csharp.csharp_type_ref_extractor import CSharpTypeRefExtractor


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


def test_create_call_extractor_returns_none():
    """create_call_extractor() returning None is the migration gate for ReferencesResolver dispatch."""
    extractor = CSharpPlugin().create_call_extractor()
    assert extractor is None


def test_create_attribute_extractor_returns_csharp_type():
    extractor = CSharpPlugin().create_attribute_extractor()
    assert isinstance(extractor, CSharpAttributeExtractor)


def test_create_type_ref_extractor_returns_tree_sitter_type():
    extractor = CSharpPlugin().create_type_ref_extractor()
    assert isinstance(extractor, CSharpTypeRefExtractor)


def test_create_lsp_adapter_delegates_to_csharp_adapter():
    with patch("synapps.lsp.csharp.CSharpLSPAdapter.create") as mock_create:
        mock_adapter = mock_create.return_value
        result = CSharpPlugin().create_lsp_adapter("/path/to/project")
        mock_create.assert_called_once_with("/path/to/project")
        assert result is mock_adapter


def test_missing_tree_sitter_raises_module_not_found():
    with patch.dict("sys.modules", {"tree_sitter_c_sharp": None}):
        with pytest.raises(ModuleNotFoundError):
            CSharpPlugin()
