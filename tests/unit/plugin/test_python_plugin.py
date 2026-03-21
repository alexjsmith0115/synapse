from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from synapse.graph.connection import GraphConnection
from synapse.plugin import LanguagePlugin, LanguageRegistry, default_registry
from synapse.plugin.python import PythonPlugin
from synapse.indexer.python.python_base_type_extractor import PythonBaseTypeExtractor
from synapse.indexer.python.python_import_extractor import PythonImportExtractor


def test_name_returns_python():
    assert PythonPlugin().name == "python"


def test_file_extensions_returns_py():
    assert PythonPlugin().file_extensions == frozenset({".py"})


def test_is_language_plugin():
    assert isinstance(PythonPlugin(), LanguagePlugin)


def test_create_base_type_extractor_returns_python_type():
    extractor = PythonPlugin().create_base_type_extractor()
    assert isinstance(extractor, PythonBaseTypeExtractor)


def test_create_import_extractor_default_source_root():
    extractor = PythonPlugin().create_import_extractor()
    assert isinstance(extractor, PythonImportExtractor)
    assert extractor._source_root == ""


def test_create_import_extractor_with_source_root():
    extractor = PythonPlugin().create_import_extractor(source_root="/some/path")
    assert isinstance(extractor, PythonImportExtractor)
    assert extractor._source_root == "/some/path"


def test_create_call_extractor_returns_python_call_extractor():
    from synapse.indexer.python.python_call_extractor import PythonCallExtractor
    extractor = PythonPlugin().create_call_extractor()
    assert isinstance(extractor, PythonCallExtractor)


def test_create_attribute_extractor_returns_python_attribute_extractor():
    from synapse.indexer.python.python_attribute_extractor import PythonAttributeExtractor
    extractor = PythonPlugin().create_attribute_extractor()
    assert isinstance(extractor, PythonAttributeExtractor)


def test_create_type_ref_extractor_returns_python_type():
    from synapse.indexer.python.python_type_ref_extractor import PythonTypeRefExtractor
    extractor = PythonPlugin().create_type_ref_extractor()
    assert isinstance(extractor, PythonTypeRefExtractor)


def test_default_registry_includes_python():
    registry = default_registry()
    assert registry.get("python") is not None


def test_detect_returns_python_plugin_for_py_directory(tmp_path):
    (tmp_path / "main.py").write_text("print('hello')")
    registry = default_registry()
    result = registry.detect(str(tmp_path))
    names = [p.name for p in result]
    assert "python" in names


def test_upsert_symbol_imports_creates_imports_edge():
    from synapse.graph.edges import upsert_symbol_imports

    conn = MagicMock(spec=GraphConnection)
    upsert_symbol_imports(conn, "/proj/main.py", "mypackage.MyClass")

    conn.execute.assert_called_once()
    cypher, params = conn.execute.call_args[0]
    assert "IMPORTS" in cypher
    assert "full_name" in cypher
    assert "$sym" in cypher
    assert params["file"] == "/proj/main.py"
    assert params["sym"] == "mypackage.MyClass"


def test_create_lsp_adapter_delegates_to_python_adapter():
    with patch("synapse.lsp.python.PythonLSPAdapter.create") as mock_create:
        mock_adapter = mock_create.return_value
        result = PythonPlugin().create_lsp_adapter("/path/to/project")
        mock_create.assert_called_once_with("/path/to/project")
        assert result is mock_adapter


def test_missing_tree_sitter_raises_module_not_found():
    with patch.dict("sys.modules", {"tree_sitter_python": None}):
        plugin = PythonPlugin()
        with pytest.raises(ModuleNotFoundError):
            plugin.create_import_extractor()
