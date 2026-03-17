"""Tests for PythonLSPAdapter, detect_source_root, _build_python_full_name, and re-export dedup."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from synapse.lsp.interface import SymbolKind


# ---------------------------------------------------------------------------
# detect_source_root
# ---------------------------------------------------------------------------

class TestDetectSourceRoot:
    def test_package_layout_returns_project_root(self, tmp_path: Path) -> None:
        """Standard package layout: proj/synapsepytest/__init__.py -> source root = proj."""
        from synapse.lsp.python import detect_source_root

        pkg = tmp_path / "synapsepytest"
        pkg.mkdir()
        (pkg / "__init__.py").touch()
        (pkg / "animals.py").touch()

        result = detect_source_root(str(pkg / "animals.py"), str(tmp_path))
        assert result == str(tmp_path)

    def test_src_layout_returns_src_dir(self, tmp_path: Path) -> None:
        """src/ layout: proj/src/pkg/mod.py, __init__.py at pkg/ but not src/ -> source root = proj/src."""
        from synapse.lsp.python import detect_source_root

        src = tmp_path / "src"
        pkg = src / "pkg"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").touch()
        (pkg / "mod.py").touch()

        result = detect_source_root(str(pkg / "mod.py"), str(tmp_path))
        assert result == str(src)

    def test_flat_layout_returns_project_root(self, tmp_path: Path) -> None:
        """Flat layout: proj/script.py with no __init__.py -> source root = proj."""
        from synapse.lsp.python import detect_source_root

        (tmp_path / "script.py").touch()

        result = detect_source_root(str(tmp_path / "script.py"), str(tmp_path))
        assert result == str(tmp_path)


# ---------------------------------------------------------------------------
# _build_python_full_name
# ---------------------------------------------------------------------------

class TestBuildPythonFullName:
    def test_simple_class_in_submodule(self, tmp_path: Path) -> None:
        """Module prefix synapsepytest.animals, symbol Dog -> synapsepytest.animals.Dog."""
        from synapse.lsp.python import _build_python_full_name

        source_root = str(tmp_path)
        file_path = str(tmp_path / "synapsepytest" / "animals.py")
        raw = {"name": "Dog", "kind": 5}

        result = _build_python_full_name(raw, file_path, source_root)
        assert result == "synapsepytest.animals.Dog"

    def test_nested_class_includes_parent_chain(self, tmp_path: Path) -> None:
        """Nested class Inner inside Outer -> pkg.mod.Outer.Inner."""
        from synapse.lsp.python import _build_python_full_name

        source_root = str(tmp_path)
        file_path = str(tmp_path / "pkg" / "mod.py")
        outer = {"name": "Outer", "kind": 5}
        raw = {"name": "Inner", "kind": 5, "parent": outer}

        result = _build_python_full_name(raw, file_path, source_root)
        assert result == "pkg.mod.Outer.Inner"

    def test_module_level_function(self, tmp_path: Path) -> None:
        """Module-level function -> synapsepytest.services.version."""
        from synapse.lsp.python import _build_python_full_name

        source_root = str(tmp_path)
        file_path = str(tmp_path / "synapsepytest" / "services.py")
        raw = {"name": "version", "kind": 12}

        result = _build_python_full_name(raw, file_path, source_root)
        assert result == "synapsepytest.services.version"

    def test_init_py_strips_dunder_init(self, tmp_path: Path) -> None:
        """__init__.py module path strips __init__ suffix -> synapsepytest not synapsepytest.__init__."""
        from synapse.lsp.python import _build_python_full_name

        source_root = str(tmp_path)
        file_path = str(tmp_path / "synapsepytest" / "__init__.py")
        raw = {"name": "MyClass", "kind": 5}

        result = _build_python_full_name(raw, file_path, source_root)
        assert result == "synapsepytest.MyClass"

    def test_deeply_nested_method(self, tmp_path: Path) -> None:
        """Method inside nested class: pkg.mod.Outer.Inner.method."""
        from synapse.lsp.python import _build_python_full_name

        source_root = str(tmp_path)
        file_path = str(tmp_path / "pkg" / "mod.py")
        outer = {"name": "Outer", "kind": 5}
        inner = {"name": "Inner", "kind": 5, "parent": outer}
        raw = {"name": "method", "kind": 6, "parent": inner}

        result = _build_python_full_name(raw, file_path, source_root)
        assert result == "pkg.mod.Outer.Inner.method"


# ---------------------------------------------------------------------------
# _convert (LSP kind mapping)
# ---------------------------------------------------------------------------

class TestConvert:
    def _make_adapter(self) -> object:
        from synapse.lsp.python import PythonLSPAdapter
        mock_ls = MagicMock()
        return PythonLSPAdapter(mock_ls, "/proj")

    def _make_raw(self, name: str, kind: int, line: int = 1, end_line: int = 5) -> dict:
        return {
            "name": name,
            "kind": kind,
            "location": {"range": {"start": {"line": line}, "end": {"line": end_line}}},
        }

    def test_kind_5_class_maps_to_class(self) -> None:
        adapter = self._make_adapter()
        raw = self._make_raw("MyClass", 5)
        sym = adapter._convert(raw, "/proj/pkg/mod.py", "/proj", parent_full_name=None)
        assert sym is not None
        assert sym.kind == SymbolKind.CLASS

    def test_kind_2_module_maps_to_class(self) -> None:
        """LSP kind 2 (Module) must map to SymbolKind.CLASS (NOT NAMESPACE) per user decision."""
        adapter = self._make_adapter()
        raw = self._make_raw("mymodule", 2)
        sym = adapter._convert(raw, "/proj/pkg/mod.py", "/proj", parent_full_name=None)
        assert sym is not None
        assert sym.kind == SymbolKind.CLASS

    def test_kind_2_module_sets_signature_module(self) -> None:
        """LSP kind 2 must set signature='module' so Plan 04 can set kind_str='module' on upsert."""
        adapter = self._make_adapter()
        raw = self._make_raw("mymodule", 2)
        sym = adapter._convert(raw, "/proj/pkg/mod.py", "/proj", parent_full_name=None)
        assert sym is not None
        assert sym.signature == "module"

    def test_kind_12_function_maps_to_method(self) -> None:
        adapter = self._make_adapter()
        raw = self._make_raw("my_func", 12)
        sym = adapter._convert(raw, "/proj/pkg/mod.py", "/proj", parent_full_name=None)
        assert sym is not None
        assert sym.kind == SymbolKind.METHOD

    def test_kind_7_property_maps_to_property(self) -> None:
        adapter = self._make_adapter()
        raw = self._make_raw("my_prop", 7)
        sym = adapter._convert(raw, "/proj/pkg/mod.py", "/proj", parent_full_name=None)
        assert sym is not None
        assert sym.kind == SymbolKind.PROPERTY

    def test_dunder_init_maps_to_method(self) -> None:
        """__init__ method -> SymbolKind.METHOD (kind_detail='constructor' set by Plan 04)."""
        adapter = self._make_adapter()
        raw = self._make_raw("__init__", 6)
        sym = adapter._convert(raw, "/proj/pkg/mod.py", "/proj", parent_full_name=None)
        assert sym is not None
        assert sym.kind == SymbolKind.METHOD

    def test_kind_14_constant_returns_none(self) -> None:
        """Constants (LSP kind 14) must be skipped in v1 -> _convert returns None."""
        adapter = self._make_adapter()
        raw = self._make_raw("MY_CONST", 14)
        sym = adapter._convert(raw, "/proj/pkg/mod.py", "/proj", parent_full_name=None)
        assert sym is None


# ---------------------------------------------------------------------------
# get_document_symbols
# ---------------------------------------------------------------------------

class TestGetDocumentSymbols:
    def _make_raw_symbol(self, name: str, kind: int, line: int = 1) -> dict:
        return {
            "name": name,
            "kind": kind,
            "location": {"range": {"start": {"line": line}, "end": {"line": line + 5}}},
            "children": [],
        }

    def test_passes_relpath_to_language_server(self, tmp_path: Path) -> None:
        """get_document_symbols passes os.path.relpath(file_path, root_path) to language server."""
        from synapse.lsp.python import PythonLSPAdapter

        mock_ls = MagicMock()
        mock_ls.request_document_symbols.return_value = None
        adapter = PythonLSPAdapter(mock_ls, str(tmp_path))

        file_path = str(tmp_path / "pkg" / "mod.py")
        adapter.get_document_symbols(file_path)

        expected_relpath = os.path.relpath(file_path, str(tmp_path))
        mock_ls.request_document_symbols.assert_called_once_with(expected_relpath)

    def test_skips_reexported_symbols_in_init_py(self, tmp_path: Path) -> None:
        """Symbols re-exported in __init__.py (from .submod import Cls) must be skipped."""
        from synapse.lsp.python import PythonLSPAdapter

        pkg = tmp_path / "synapsepytest"
        pkg.mkdir()
        init_file = pkg / "__init__.py"
        init_file.write_text("from .animals import Dog\n")

        mock_ls = MagicMock()
        reexport_raw = self._make_raw_symbol("Dog", 5, line=1)
        result_obj = MagicMock()
        result_obj.root_symbols = [reexport_raw]
        mock_ls.request_document_symbols.return_value = result_obj

        adapter = PythonLSPAdapter(mock_ls, str(tmp_path))
        symbols = adapter.get_document_symbols(str(init_file))

        assert all(s.name != "Dog" for s in symbols)

    def test_keeps_symbols_defined_in_init_py(self, tmp_path: Path) -> None:
        """Symbols actually defined in __init__.py (not re-exports) must be kept."""
        from synapse.lsp.python import PythonLSPAdapter

        pkg = tmp_path / "synapsepytest"
        pkg.mkdir()
        init_file = pkg / "__init__.py"
        # No import of ActualClass -> it's defined here
        init_file.write_text("class ActualClass:\n    pass\n")

        mock_ls = MagicMock()
        actual_raw = self._make_raw_symbol("ActualClass", 5, line=1)
        result_obj = MagicMock()
        result_obj.root_symbols = [actual_raw]
        mock_ls.request_document_symbols.return_value = result_obj

        adapter = PythonLSPAdapter(mock_ls, str(tmp_path))
        symbols = adapter.get_document_symbols(str(init_file))

        assert any(s.name == "ActualClass" for s in symbols)


# ---------------------------------------------------------------------------
# PythonLSPAdapter.create() startup readiness
# ---------------------------------------------------------------------------

class TestCreate:
    def test_create_calls_start_before_returning(self) -> None:
        """create() must call ls.start() which internally waits on analysis_complete (PLSP-02)."""
        from synapse.lsp.python import PythonLSPAdapter

        call_order: list[str] = []

        mock_ls = MagicMock()
        mock_ls.start.side_effect = lambda: call_order.append("start")

        class FakeLanguage:
            PYTHON = "python"

        fake_ls_config = MagicMock()
        fake_ls_config.Language = FakeLanguage
        fake_ls_config.LanguageServerConfig = MagicMock(side_effect=lambda **kw: MagicMock())

        fake_pyright_mod = MagicMock()
        fake_pyright_mod.PyrightServer.return_value = mock_ls

        with patch.dict(sys.modules, {
            "solidlsp.language_servers.pyright_server": fake_pyright_mod,
            "solidlsp.ls_config": fake_ls_config,
            "solidlsp.settings": MagicMock(),
        }):
            adapter = PythonLSPAdapter.create("/some/project")

        assert "start" in call_order
        assert adapter._root_path == "/some/project"

    def test_create_passes_root_path_to_pyright_server(self) -> None:
        """create() passes repository_root_path to PyrightServer constructor."""
        from synapse.lsp.python import PythonLSPAdapter

        mock_ls = MagicMock()

        class FakeLanguage:
            PYTHON = "python"

        fake_ls_config = MagicMock()
        fake_ls_config.Language = FakeLanguage
        fake_ls_config.LanguageServerConfig = MagicMock(return_value=MagicMock())

        fake_pyright_mod = MagicMock()
        fake_pyright_mod.PyrightServer.return_value = mock_ls

        with patch.dict(sys.modules, {
            "solidlsp.language_servers.pyright_server": fake_pyright_mod,
            "solidlsp.ls_config": fake_ls_config,
            "solidlsp.settings": MagicMock(),
        }):
            PythonLSPAdapter.create("/my/project")

        _, kwargs = fake_pyright_mod.PyrightServer.call_args
        assert kwargs["repository_root_path"] == "/my/project"


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------

def test_python_adapter_implements_protocol() -> None:
    from synapse.lsp.python import PythonLSPAdapter
    from synapse.lsp.interface import LSPAdapter

    mock_ls = MagicMock()
    adapter = PythonLSPAdapter(mock_ls, "/proj")
    assert isinstance(adapter, LSPAdapter)


def test_find_method_calls_returns_empty() -> None:
    from synapse.lsp.python import PythonLSPAdapter
    from synapse.lsp.interface import IndexSymbol, SymbolKind

    adapter = PythonLSPAdapter(MagicMock(), "/proj")
    sym = IndexSymbol(name="fn", full_name="pkg.fn", kind=SymbolKind.METHOD, file_path="/proj/pkg/mod.py", line=1)
    assert adapter.find_method_calls(sym) == []


def test_find_overridden_method_returns_none() -> None:
    from synapse.lsp.python import PythonLSPAdapter
    from synapse.lsp.interface import IndexSymbol, SymbolKind

    adapter = PythonLSPAdapter(MagicMock(), "/proj")
    sym = IndexSymbol(name="fn", full_name="pkg.fn", kind=SymbolKind.METHOD, file_path="/proj/pkg/mod.py", line=1)
    assert adapter.find_overridden_method(sym) is None


def test_shutdown_calls_stop() -> None:
    from synapse.lsp.python import PythonLSPAdapter

    mock_ls = MagicMock()
    adapter = PythonLSPAdapter(mock_ls, "/proj")
    adapter.shutdown()
    mock_ls.stop.assert_called_once()
