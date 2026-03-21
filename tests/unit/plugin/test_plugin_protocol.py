from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from synapse.plugin import LanguagePlugin


def _make_complete_mock() -> MagicMock:
    mock = MagicMock(spec=None)
    mock.name = "test"
    mock.file_extensions = frozenset({".test"})
    mock.create_lsp_adapter = MagicMock()
    mock.create_call_extractor = MagicMock()
    mock.create_import_extractor = MagicMock()
    mock.create_base_type_extractor = MagicMock()
    mock.create_attribute_extractor = MagicMock()
    mock.create_type_ref_extractor = MagicMock()
    mock.create_assignment_extractor = MagicMock()
    return mock


def test_language_plugin_is_runtime_checkable():
    mock = _make_complete_mock()
    assert isinstance(mock, LanguagePlugin)


def test_language_plugin_rejects_incomplete():
    mock = MagicMock(spec=None)
    mock.name = "test"
    # Missing all factory methods and file_extensions
    assert not isinstance(mock, LanguagePlugin)


def test_protocol_has_name_property():
    assert hasattr(LanguagePlugin, "name")


def test_protocol_has_file_extensions_property():
    assert hasattr(LanguagePlugin, "file_extensions")


def test_protocol_has_create_lsp_adapter():
    assert hasattr(LanguagePlugin, "create_lsp_adapter")


def test_protocol_has_create_call_extractor():
    assert hasattr(LanguagePlugin, "create_call_extractor")


def test_protocol_has_create_import_extractor():
    assert hasattr(LanguagePlugin, "create_import_extractor")


def test_protocol_has_create_base_type_extractor():
    assert hasattr(LanguagePlugin, "create_base_type_extractor")


def test_protocol_has_create_attribute_extractor():
    assert hasattr(LanguagePlugin, "create_attribute_extractor")


def test_protocol_has_create_type_ref_extractor():
    assert hasattr(LanguagePlugin, "create_type_ref_extractor")


def test_protocol_has_create_assignment_extractor():
    assert hasattr(LanguagePlugin, "create_assignment_extractor")
