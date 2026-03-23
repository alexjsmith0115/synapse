from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from synapse.plugin import LanguageRegistry, default_registry


def _make_plugin(name: str, extensions: frozenset[str]) -> MagicMock:
    mock = MagicMock(spec=None)
    mock.name = name
    mock.file_extensions = extensions
    mock.create_lsp_adapter = MagicMock()
    mock.create_call_extractor = MagicMock()
    mock.create_import_extractor = MagicMock()
    mock.create_base_type_extractor = MagicMock()
    mock.create_attribute_extractor = MagicMock()
    mock.create_type_ref_extractor = MagicMock()
    return mock


def test_register_stores_plugin():
    registry = LanguageRegistry()
    plugin = _make_plugin("test", frozenset({".test"}))
    registry.register(plugin)
    assert plugin in registry._plugins


def test_detect_returns_matching_plugin(tmp_path):
    (tmp_path / "Foo.cs").write_text("// hello")
    plugin = _make_plugin("csharp", frozenset({".cs"}))
    registry = LanguageRegistry()
    registry.register(plugin)
    result = registry.detect(str(tmp_path))
    assert result == [plugin]


def test_detect_returns_empty_when_no_match(tmp_path):
    (tmp_path / "notes.txt").write_text("hello")
    plugin = _make_plugin("csharp", frozenset({".cs"}))
    registry = LanguageRegistry()
    registry.register(plugin)
    result = registry.detect(str(tmp_path))
    assert result == []


def test_detect_returns_multiple_plugins(tmp_path):
    (tmp_path / "Foo.cs").write_text("// cs")
    (tmp_path / "bar.py").write_text("# py")
    cs_plugin = _make_plugin("csharp", frozenset({".cs"}))
    py_plugin = _make_plugin("python", frozenset({".py"}))
    registry = LanguageRegistry()
    registry.register(cs_plugin)
    registry.register(py_plugin)
    result = registry.detect(str(tmp_path))
    assert cs_plugin in result
    assert py_plugin in result


def test_detect_case_insensitive(tmp_path):
    (tmp_path / "Foo.CS").write_text("// uppercase ext")
    plugin = _make_plugin("csharp", frozenset({".cs"}))
    registry = LanguageRegistry()
    registry.register(plugin)
    result = registry.detect(str(tmp_path))
    assert result == [plugin]


def test_get_returns_plugin_by_name():
    registry = LanguageRegistry()
    plugin = _make_plugin("csharp", frozenset({".cs"}))
    registry.register(plugin)
    assert registry.get("csharp") is plugin


def test_get_returns_none_for_missing_name():
    registry = LanguageRegistry()
    assert registry.get("nonexistent") is None


def test_all_extensions_returns_union():
    registry = LanguageRegistry()
    registry.register(_make_plugin("a", frozenset({".cs", ".csx"})))
    registry.register(_make_plugin("b", frozenset({".py"})))
    assert registry.all_extensions() == frozenset({".cs", ".csx", ".py"})


def test_default_registry_has_csharp(tmp_path):
    (tmp_path / "Program.cs").write_text("// cs")
    registry = default_registry()
    result = registry.detect(str(tmp_path))
    assert len(result) == 1
    assert result[0].name == "csharp"


def test_detect_typescript_project(tmp_path):
    (tmp_path / "app.ts").write_text("export class App {}")
    registry = default_registry()
    result = registry.detect(str(tmp_path))
    names = [p.name for p in result]
    assert "typescript" in names


def test_detect_with_files_returns_plugin_and_file_list(tmp_path):
    (tmp_path / "foo.py").write_text("x = 1")
    (tmp_path / "bar.ts").write_text("const x = 1")
    registry = default_registry()
    results = registry.detect_with_files(str(tmp_path))
    plugins_by_name = {p.name: files for p, files in results}
    assert "python" in plugins_by_name
    assert "typescript" in plugins_by_name
    assert any("foo.py" in f for f in plugins_by_name["python"])
    assert any("bar.ts" in f for f in plugins_by_name["typescript"])


def test_detect_with_files_skips_git_and_node_modules(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config.py").write_text("x")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "pkg.ts").write_text("x")
    (tmp_path / "real.py").write_text("x = 1")
    registry = default_registry()
    results = registry.detect_with_files(str(tmp_path))
    all_files = [f for _, files in results for f in files]
    assert any("real.py" in f for f in all_files)
    assert not any(".git" in f for f in all_files)
    assert not any("node_modules" in f for f in all_files)


def test_detect_with_files_returns_empty_for_no_matching_files(tmp_path):
    (tmp_path / "readme.txt").write_text("hello")
    registry = default_registry()
    results = registry.detect_with_files(str(tmp_path))
    assert results == []


def test_detect_with_files_filters_excluded_suffixes(tmp_path):
    (tmp_path / "app.ts").write_text("x")
    (tmp_path / "vendor.min.js").write_text("x")
    registry = default_registry()
    results = registry.detect_with_files(str(tmp_path))
    ts_files = [f for p, files in results if p.name == "typescript" for f in files]
    assert any("app.ts" in f for f in ts_files)
    assert not any("vendor.min.js" in f for f in ts_files)


def test_detect_delegates_to_detect_with_files(tmp_path):
    (tmp_path / "foo.py").write_text("x = 1")
    registry = default_registry()
    plugins = registry.detect(str(tmp_path))
    assert any(p.name == "python" for p in plugins)
