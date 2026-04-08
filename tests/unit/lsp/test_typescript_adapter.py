"""Tests for TypeScriptLSPAdapter, _build_ts_full_name, and SymbolKind mapping."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from synapps.lsp.interface import SymbolKind


# ---------------------------------------------------------------------------
# _build_ts_full_name
# ---------------------------------------------------------------------------

class TestBuildTsFullName:
    def test_class_in_subdir(self, tmp_path: Path) -> None:
        """src/services/auth.ts with class AuthService -> 'src/services/auth.AuthService'."""
        from synapps.lsp.typescript import _build_ts_full_name

        root = str(tmp_path)
        file_path = str(tmp_path / "src" / "services" / "auth.ts")
        raw = {"name": "AuthService", "kind": 5}

        result = _build_ts_full_name(raw, file_path, root)
        assert result == "src/services/auth.AuthService"

    def test_function_in_tsx_file(self, tmp_path: Path) -> None:
        """src/utils/helpers.tsx with function helper -> 'src/utils/helpers.helper'."""
        from synapps.lsp.typescript import _build_ts_full_name

        root = str(tmp_path)
        file_path = str(tmp_path / "src" / "utils" / "helpers.tsx")
        raw = {"name": "helper", "kind": 12}

        result = _build_ts_full_name(raw, file_path, root)
        assert result == "src/utils/helpers.helper"

    def test_nested_method_inside_class(self, tmp_path: Path) -> None:
        """Nested method inside class -> 'src/mod.MyClass.myMethod'."""
        from synapps.lsp.typescript import _build_ts_full_name

        root = str(tmp_path)
        file_path = str(tmp_path / "src" / "mod.ts")
        parent = {"name": "MyClass", "kind": 5}
        raw = {"name": "myMethod", "kind": 6, "parent": parent}

        result = _build_ts_full_name(raw, file_path, root)
        assert result == "src/mod.MyClass.myMethod"

    def test_forward_slashes_on_all_platforms(self, tmp_path: Path) -> None:
        """Full name uses forward slashes regardless of OS path separator."""
        from synapps.lsp.typescript import _build_ts_full_name

        root = str(tmp_path)
        file_path = str(tmp_path / "a" / "b" / "c.ts")
        raw = {"name": "Foo", "kind": 5}

        result = _build_ts_full_name(raw, file_path, root)
        assert "\\" not in result
        assert result == "a/b/c.Foo"


# ---------------------------------------------------------------------------
# _convert (LSP kind mapping)
# ---------------------------------------------------------------------------

class TestConvert:
    def _make_adapter(self) -> object:
        from synapps.lsp.typescript import TypeScriptLSPAdapter
        mock_ls = MagicMock()
        return TypeScriptLSPAdapter(mock_ls, "/proj")

    def _make_raw(self, name: str, kind: int, line: int = 1, end_line: int = 5) -> dict:
        return {
            "name": name,
            "kind": kind,
            "location": {"range": {"start": {"line": line}, "end": {"line": end_line}}},
        }

    def test_kind_5_class_maps_to_class(self) -> None:
        adapter = self._make_adapter()
        raw = self._make_raw("MyClass", 5)
        sym = adapter._convert(raw, "/proj/src/mod.ts", "/proj", parent_full_name=None)
        assert sym is not None
        assert sym.kind == SymbolKind.CLASS

    def test_kind_6_method_maps_to_method(self) -> None:
        adapter = self._make_adapter()
        raw = self._make_raw("myMethod", 6)
        sym = adapter._convert(raw, "/proj/src/mod.ts", "/proj", parent_full_name=None)
        assert sym is not None
        assert sym.kind == SymbolKind.METHOD

    def test_kind_7_property_maps_to_property(self) -> None:
        adapter = self._make_adapter()
        raw = self._make_raw("myProp", 7)
        sym = adapter._convert(raw, "/proj/src/mod.ts", "/proj", parent_full_name=None)
        assert sym is not None
        assert sym.kind == SymbolKind.PROPERTY

    def test_kind_8_field_maps_to_field(self) -> None:
        adapter = self._make_adapter()
        raw = self._make_raw("myField", 8)
        sym = adapter._convert(raw, "/proj/src/mod.ts", "/proj", parent_full_name=None)
        assert sym is not None
        assert sym.kind == SymbolKind.FIELD

    def test_kind_9_constructor_maps_to_method(self) -> None:
        adapter = self._make_adapter()
        raw = self._make_raw("constructor", 9)
        sym = adapter._convert(raw, "/proj/src/mod.ts", "/proj", parent_full_name=None)
        assert sym is not None
        assert sym.kind == SymbolKind.METHOD

    def test_kind_10_enum_maps_to_enum(self) -> None:
        adapter = self._make_adapter()
        raw = self._make_raw("MyEnum", 10)
        sym = adapter._convert(raw, "/proj/src/mod.ts", "/proj", parent_full_name=None)
        assert sym is not None
        assert sym.kind == SymbolKind.ENUM

    def test_kind_11_interface_maps_to_interface(self) -> None:
        adapter = self._make_adapter()
        raw = self._make_raw("IMyInterface", 11)
        sym = adapter._convert(raw, "/proj/src/mod.ts", "/proj", parent_full_name=None)
        assert sym is not None
        assert sym.kind == SymbolKind.INTERFACE

    def test_kind_12_function_maps_to_method(self) -> None:
        adapter = self._make_adapter()
        raw = self._make_raw("myFunc", 12)
        sym = adapter._convert(raw, "/proj/src/mod.ts", "/proj", parent_full_name=None)
        assert sym is not None
        assert sym.kind == SymbolKind.METHOD

    def test_kind_2_module_maps_to_class(self) -> None:
        adapter = self._make_adapter()
        raw = self._make_raw("myModule", 2)
        sym = adapter._convert(raw, "/proj/src/mod.ts", "/proj", parent_full_name=None)
        assert sym is not None
        assert sym.kind == SymbolKind.CLASS

    def test_kind_2_module_sets_signature_module(self) -> None:
        adapter = self._make_adapter()
        raw = self._make_raw("myModule", 2)
        sym = adapter._convert(raw, "/proj/src/mod.ts", "/proj", parent_full_name=None)
        assert sym is not None
        assert sym.signature == "module"

    def test_kind_3_namespace_maps_to_namespace(self) -> None:
        adapter = self._make_adapter()
        raw = self._make_raw("MyNamespace", 3)
        sym = adapter._convert(raw, "/proj/src/mod.ts", "/proj", parent_full_name=None)
        assert sym is not None
        assert sym.kind == SymbolKind.NAMESPACE

    def test_kind_13_variable_returns_none(self) -> None:
        adapter = self._make_adapter()
        raw = self._make_raw("myVar", 13)
        sym = adapter._convert(raw, "/proj/src/mod.ts", "/proj", parent_full_name=None)
        assert sym is None

    def test_kind_14_constant_returns_none(self) -> None:
        adapter = self._make_adapter()
        raw = self._make_raw("MY_CONST", 14)
        sym = adapter._convert(raw, "/proj/src/mod.ts", "/proj", parent_full_name=None)
        assert sym is None


# ---------------------------------------------------------------------------
# get_workspace_files — file extensions
# ---------------------------------------------------------------------------

class TestGetWorkspaceFiles:
    def test_returns_ts_files(self, tmp_path: Path) -> None:
        from synapps.lsp.typescript import TypeScriptLSPAdapter
        adapter = TypeScriptLSPAdapter(MagicMock(), str(tmp_path))
        (tmp_path / "app.ts").touch()
        files = adapter.get_workspace_files(str(tmp_path))
        assert str(tmp_path / "app.ts") in files

    def test_returns_tsx_files(self, tmp_path: Path) -> None:
        from synapps.lsp.typescript import TypeScriptLSPAdapter
        adapter = TypeScriptLSPAdapter(MagicMock(), str(tmp_path))
        (tmp_path / "comp.tsx").touch()
        files = adapter.get_workspace_files(str(tmp_path))
        assert str(tmp_path / "comp.tsx") in files

    def test_returns_js_files(self, tmp_path: Path) -> None:
        from synapps.lsp.typescript import TypeScriptLSPAdapter
        adapter = TypeScriptLSPAdapter(MagicMock(), str(tmp_path))
        (tmp_path / "util.js").touch()
        files = adapter.get_workspace_files(str(tmp_path))
        assert str(tmp_path / "util.js") in files

    def test_returns_jsx_files(self, tmp_path: Path) -> None:
        from synapps.lsp.typescript import TypeScriptLSPAdapter
        adapter = TypeScriptLSPAdapter(MagicMock(), str(tmp_path))
        (tmp_path / "comp.jsx").touch()
        files = adapter.get_workspace_files(str(tmp_path))
        assert str(tmp_path / "comp.jsx") in files

    def test_returns_mts_files(self, tmp_path: Path) -> None:
        from synapps.lsp.typescript import TypeScriptLSPAdapter
        adapter = TypeScriptLSPAdapter(MagicMock(), str(tmp_path))
        (tmp_path / "mod.mts").touch()
        files = adapter.get_workspace_files(str(tmp_path))
        assert str(tmp_path / "mod.mts") in files

    def test_returns_cts_files(self, tmp_path: Path) -> None:
        from synapps.lsp.typescript import TypeScriptLSPAdapter
        adapter = TypeScriptLSPAdapter(MagicMock(), str(tmp_path))
        (tmp_path / "mod.cts").touch()
        files = adapter.get_workspace_files(str(tmp_path))
        assert str(tmp_path / "mod.cts") in files

    def test_returns_mjs_files(self, tmp_path: Path) -> None:
        from synapps.lsp.typescript import TypeScriptLSPAdapter
        adapter = TypeScriptLSPAdapter(MagicMock(), str(tmp_path))
        (tmp_path / "mod.mjs").touch()
        files = adapter.get_workspace_files(str(tmp_path))
        assert str(tmp_path / "mod.mjs") in files

    def test_returns_cjs_files(self, tmp_path: Path) -> None:
        from synapps.lsp.typescript import TypeScriptLSPAdapter
        adapter = TypeScriptLSPAdapter(MagicMock(), str(tmp_path))
        (tmp_path / "mod.cjs").touch()
        files = adapter.get_workspace_files(str(tmp_path))
        assert str(tmp_path / "mod.cjs") in files

    def test_excludes_non_ts_files(self, tmp_path: Path) -> None:
        from synapps.lsp.typescript import TypeScriptLSPAdapter
        adapter = TypeScriptLSPAdapter(MagicMock(), str(tmp_path))
        (tmp_path / "readme.md").touch()
        (tmp_path / "style.css").touch()
        files = adapter.get_workspace_files(str(tmp_path))
        assert not any(f.endswith(".md") or f.endswith(".css") for f in files)


# ---------------------------------------------------------------------------
# get_workspace_files — exclusions
# ---------------------------------------------------------------------------

class TestExclusions:
    def _make_file_in_dir(self, tmp_path: Path, subdir: str) -> Path:
        d = tmp_path / subdir
        d.mkdir(parents=True)
        f = d / "index.ts"
        f.touch()
        return f

    def test_excludes_node_modules(self, tmp_path: Path) -> None:
        from synapps.lsp.typescript import TypeScriptLSPAdapter
        adapter = TypeScriptLSPAdapter(MagicMock(), str(tmp_path))
        excluded = self._make_file_in_dir(tmp_path, "node_modules")
        files = adapter.get_workspace_files(str(tmp_path))
        assert str(excluded) not in files

    def test_excludes_dist(self, tmp_path: Path) -> None:
        from synapps.lsp.typescript import TypeScriptLSPAdapter
        adapter = TypeScriptLSPAdapter(MagicMock(), str(tmp_path))
        excluded = self._make_file_in_dir(tmp_path, "dist")
        files = adapter.get_workspace_files(str(tmp_path))
        assert str(excluded) not in files

    def test_excludes_build(self, tmp_path: Path) -> None:
        from synapps.lsp.typescript import TypeScriptLSPAdapter
        adapter = TypeScriptLSPAdapter(MagicMock(), str(tmp_path))
        excluded = self._make_file_in_dir(tmp_path, "build")
        files = adapter.get_workspace_files(str(tmp_path))
        assert str(excluded) not in files

    def test_excludes_git(self, tmp_path: Path) -> None:
        from synapps.lsp.typescript import TypeScriptLSPAdapter
        adapter = TypeScriptLSPAdapter(MagicMock(), str(tmp_path))
        excluded = self._make_file_in_dir(tmp_path, ".git")
        files = adapter.get_workspace_files(str(tmp_path))
        assert str(excluded) not in files

    def test_excludes_coverage(self, tmp_path: Path) -> None:
        from synapps.lsp.typescript import TypeScriptLSPAdapter
        adapter = TypeScriptLSPAdapter(MagicMock(), str(tmp_path))
        excluded = self._make_file_in_dir(tmp_path, "coverage")
        files = adapter.get_workspace_files(str(tmp_path))
        assert str(excluded) not in files

    def test_included_file_alongside_excluded_dirs(self, tmp_path: Path) -> None:
        from synapps.lsp.typescript import TypeScriptLSPAdapter
        adapter = TypeScriptLSPAdapter(MagicMock(), str(tmp_path))
        self._make_file_in_dir(tmp_path, "node_modules")
        included = tmp_path / "src" / "main.ts"
        included.parent.mkdir()
        included.touch()
        files = adapter.get_workspace_files(str(tmp_path))
        assert str(included) in files

    def test_excludes_coveragereport(self, tmp_path: Path) -> None:
        from synapps.lsp.typescript import TypeScriptLSPAdapter
        adapter = TypeScriptLSPAdapter(MagicMock(), str(tmp_path))
        excluded = self._make_file_in_dir(tmp_path, "coveragereport")
        files = adapter.get_workspace_files(str(tmp_path))
        assert str(excluded) not in files

    def test_excludes_dot_next(self, tmp_path: Path) -> None:
        from synapps.lsp.typescript import TypeScriptLSPAdapter
        adapter = TypeScriptLSPAdapter(MagicMock(), str(tmp_path))
        excluded = self._make_file_in_dir(tmp_path, ".next")
        files = adapter.get_workspace_files(str(tmp_path))
        assert str(excluded) not in files

    def test_excludes_dot_nuxt(self, tmp_path: Path) -> None:
        from synapps.lsp.typescript import TypeScriptLSPAdapter
        adapter = TypeScriptLSPAdapter(MagicMock(), str(tmp_path))
        excluded = self._make_file_in_dir(tmp_path, ".nuxt")
        files = adapter.get_workspace_files(str(tmp_path))
        assert str(excluded) not in files

    def test_excludes_out(self, tmp_path: Path) -> None:
        from synapps.lsp.typescript import TypeScriptLSPAdapter
        adapter = TypeScriptLSPAdapter(MagicMock(), str(tmp_path))
        excluded = self._make_file_in_dir(tmp_path, "out")
        files = adapter.get_workspace_files(str(tmp_path))
        assert str(excluded) not in files

    def test_excludes_dot_cache(self, tmp_path: Path) -> None:
        from synapps.lsp.typescript import TypeScriptLSPAdapter
        adapter = TypeScriptLSPAdapter(MagicMock(), str(tmp_path))
        excluded = self._make_file_in_dir(tmp_path, ".cache")
        files = adapter.get_workspace_files(str(tmp_path))
        assert str(excluded) not in files

    def test_excludes_min_js_suffix(self, tmp_path: Path) -> None:
        from synapps.lsp.typescript import TypeScriptLSPAdapter
        adapter = TypeScriptLSPAdapter(MagicMock(), str(tmp_path))
        (tmp_path / "vendor.min.js").touch()
        files = adapter.get_workspace_files(str(tmp_path))
        assert not any(f.endswith(".min.js") for f in files)

    def test_excludes_bundle_js_suffix(self, tmp_path: Path) -> None:
        from synapps.lsp.typescript import TypeScriptLSPAdapter
        adapter = TypeScriptLSPAdapter(MagicMock(), str(tmp_path))
        (tmp_path / "app.bundle.js").touch()
        files = adapter.get_workspace_files(str(tmp_path))
        assert not any(f.endswith(".bundle.js") for f in files)


# ---------------------------------------------------------------------------
# get_document_symbols
# ---------------------------------------------------------------------------

class TestGetDocumentSymbols:
    def test_passes_relpath_to_language_server(self, tmp_path: Path) -> None:
        from synapps.lsp.typescript import TypeScriptLSPAdapter

        mock_ls = MagicMock()
        mock_ls.request_document_symbols.return_value = None
        adapter = TypeScriptLSPAdapter(mock_ls, str(tmp_path))

        file_path = str(tmp_path / "src" / "mod.ts")
        adapter.get_document_symbols(file_path)

        expected_relpath = os.path.relpath(file_path, str(tmp_path))
        mock_ls.request_document_symbols.assert_called_once_with(expected_relpath)

    def test_returns_empty_list_when_lsp_returns_none(self, tmp_path: Path) -> None:
        from synapps.lsp.typescript import TypeScriptLSPAdapter

        mock_ls = MagicMock()
        mock_ls.request_document_symbols.return_value = None
        adapter = TypeScriptLSPAdapter(mock_ls, str(tmp_path))

        result = adapter.get_document_symbols(str(tmp_path / "src" / "mod.ts"))
        assert result == []

    def test_converts_root_symbols(self, tmp_path: Path) -> None:
        from synapps.lsp.typescript import TypeScriptLSPAdapter

        mock_ls = MagicMock()
        raw_sym = {
            "name": "MyClass",
            "kind": 5,
            "location": {"range": {"start": {"line": 1}, "end": {"line": 10}}},
            "children": [],
        }
        result_obj = MagicMock()
        result_obj.root_symbols = [raw_sym]
        mock_ls.request_document_symbols.return_value = result_obj

        adapter = TypeScriptLSPAdapter(mock_ls, str(tmp_path))
        symbols = adapter.get_document_symbols(str(tmp_path / "src" / "mod.ts"))

        assert len(symbols) == 1
        assert symbols[0].name == "MyClass"
        assert symbols[0].kind == SymbolKind.CLASS


# ---------------------------------------------------------------------------
# TypeScriptLSPAdapter.create() startup
# ---------------------------------------------------------------------------

class TestCreate:
    def test_create_calls_start_before_returning(self) -> None:
        """create() must call ls.start()."""
        from synapps.lsp.typescript import TypeScriptLSPAdapter

        call_order: list[str] = []

        mock_ls = MagicMock()
        mock_ls.start.side_effect = lambda: call_order.append("start")

        class FakeLanguage:
            TYPESCRIPT = "typescript"

        fake_ls_config = MagicMock()
        fake_ls_config.Language = FakeLanguage
        fake_ls_config.LanguageServerConfig = MagicMock(side_effect=lambda **kw: MagicMock())

        fake_ts_mod = MagicMock()
        fake_ts_mod.TypeScriptLanguageServer.return_value = mock_ls

        with patch.dict(sys.modules, {
            "solidlsp.language_servers.typescript_language_server": fake_ts_mod,
            "solidlsp.ls_config": fake_ls_config,
            "solidlsp.settings": MagicMock(),
        }):
            adapter = TypeScriptLSPAdapter.create("/some/project")

        assert "start" in call_order
        assert adapter._root_path == "/some/project"

    def test_create_passes_root_path_to_language_server(self) -> None:
        """create() passes repository_root_path to TypeScriptLanguageServer constructor."""
        from synapps.lsp.typescript import TypeScriptLSPAdapter

        mock_ls = MagicMock()

        class FakeLanguage:
            TYPESCRIPT = "typescript"

        fake_ls_config = MagicMock()
        fake_ls_config.Language = FakeLanguage
        fake_ls_config.LanguageServerConfig = MagicMock(return_value=MagicMock())

        fake_ts_mod = MagicMock()
        fake_ts_mod.TypeScriptLanguageServer.return_value = mock_ls

        with patch.dict(sys.modules, {
            "solidlsp.language_servers.typescript_language_server": fake_ts_mod,
            "solidlsp.ls_config": fake_ls_config,
            "solidlsp.settings": MagicMock(),
        }):
            TypeScriptLSPAdapter.create("/my/project")

        _, kwargs = fake_ts_mod.TypeScriptLanguageServer.call_args
        assert kwargs["repository_root_path"] == "/my/project"


# ---------------------------------------------------------------------------
# Protocol conformance and stubs
# ---------------------------------------------------------------------------

def test_protocol_conformance() -> None:
    from synapps.lsp.typescript import TypeScriptLSPAdapter
    from synapps.lsp.interface import LSPAdapter

    mock_ls = MagicMock()
    adapter = TypeScriptLSPAdapter(mock_ls, "/proj")
    assert isinstance(adapter, LSPAdapter)


def test_language_server_property() -> None:
    from synapps.lsp.typescript import TypeScriptLSPAdapter

    mock_ls = MagicMock()
    adapter = TypeScriptLSPAdapter(mock_ls, "/proj")
    assert adapter.language_server is mock_ls


def test_find_method_calls_returns_empty() -> None:
    from synapps.lsp.typescript import TypeScriptLSPAdapter
    from synapps.lsp.interface import IndexSymbol, SymbolKind

    adapter = TypeScriptLSPAdapter(MagicMock(), "/proj")
    sym = IndexSymbol(name="fn", full_name="src/mod.fn", kind=SymbolKind.METHOD, file_path="/proj/src/mod.ts", line=1)
    assert adapter.find_method_calls(sym) == []


def test_find_overridden_method_returns_none() -> None:
    from synapps.lsp.typescript import TypeScriptLSPAdapter
    from synapps.lsp.interface import IndexSymbol, SymbolKind

    adapter = TypeScriptLSPAdapter(MagicMock(), "/proj")
    sym = IndexSymbol(name="fn", full_name="src/mod.fn", kind=SymbolKind.METHOD, file_path="/proj/src/mod.ts", line=1)
    assert adapter.find_overridden_method(sym) is None


# ---------------------------------------------------------------------------
# _traverse: const object promotion (export const xService = { ... })
# ---------------------------------------------------------------------------

class TestTraverseConstObjectPromotion:
    """Tests for promoting top-level Variable/Constant with children to CLASS."""

    def _make_adapter(self) -> object:
        from synapps.lsp.typescript import TypeScriptLSPAdapter
        mock_ls = MagicMock()
        return TypeScriptLSPAdapter(mock_ls, "/proj")

    def _make_raw(self, name: str, kind: int, children: list | None = None,
                  line: int = 0, end_line: int = 10) -> dict:
        raw = {
            "name": name,
            "kind": kind,
            "location": {"range": {"start": {"line": line}, "end": {"line": end_line}}},
        }
        if children is not None:
            raw["children"] = children
        return raw

    def test_top_level_const_with_method_children_promoted_to_class(self) -> None:
        """export const meetingService = { getMeetings: ... } -> :Class + :Method children."""
        adapter = self._make_adapter()
        method_child = self._make_raw("getMeetings", 6, children=[], line=2, end_line=5)
        const_obj = self._make_raw("meetingService", 14, children=[method_child], line=0, end_line=10)

        result: list = []
        adapter._traverse(const_obj, "/proj/src/service.ts", parent_full_name=None, result=result)

        assert len(result) == 2
        # Parent: promoted to CLASS with const_object signature
        assert result[0].kind == SymbolKind.CLASS
        assert result[0].name == "meetingService"
        assert result[0].signature == "const_object"
        # Child: normal METHOD
        assert result[1].kind == SymbolKind.METHOD
        assert result[1].name == "getMeetings"
        assert result[1].parent_full_name == result[0].full_name

    def test_top_level_variable_with_children_promoted(self) -> None:
        """Kind 13 (Variable) also promoted when it has children."""
        adapter = self._make_adapter()
        child = self._make_raw("doStuff", 6, children=[], line=3)
        var_obj = self._make_raw("utils", 13, children=[child])

        result: list = []
        adapter._traverse(var_obj, "/proj/src/utils.ts", parent_full_name=None, result=result)

        assert len(result) == 2
        assert result[0].kind == SymbolKind.CLASS
        assert result[0].signature == "const_object"

    def test_simple_variable_without_children_still_skipped(self) -> None:
        """const API_URL = '...' -> no children -> stays skipped."""
        adapter = self._make_adapter()
        simple_var = self._make_raw("API_URL", 14)  # no children key at all

        result: list = []
        adapter._traverse(simple_var, "/proj/src/config.ts", parent_full_name=None, result=result)
        assert result == []

    def test_variable_with_empty_children_still_skipped(self) -> None:
        """Variable with children=[] stays skipped."""
        adapter = self._make_adapter()
        empty_children_var = self._make_raw("API_URL", 14, children=[])

        result: list = []
        adapter._traverse(empty_children_var, "/proj/src/config.ts", parent_full_name=None, result=result)
        assert result == []

    def test_nested_variable_inside_method_not_promoted(self) -> None:
        """const response = await api.get() inside a method -> NOT promoted (parent_full_name guard)."""
        adapter = self._make_adapter()
        param_child = self._make_raw("params", 7, children=[], line=5)
        response_var = self._make_raw("response", 14, children=[param_child], line=3)

        result: list = []
        # parent_full_name is set -> this is inside a method, not top-level
        adapter._traverse(response_var, "/proj/src/service.ts",
                          parent_full_name="src/service.meetingService.getMeetings", result=result)
        assert result == []

    def test_unknown_kind_with_children_not_promoted(self) -> None:
        """An unknown LSP kind (e.g., 99) with children should NOT be promoted."""
        adapter = self._make_adapter()
        child = self._make_raw("inner", 6, children=[])
        unknown = self._make_raw("mystery", 99, children=[child])

        result: list = []
        adapter._traverse(unknown, "/proj/src/mod.ts", parent_full_name=None, result=result)
        assert result == []

    def test_const_with_only_property_children_promoted_to_method(self) -> None:
        """const MyComponent = () => { ... } -> Property children only -> :Method.

        React components and hooks are arrow functions assigned to const.
        The LSP reports them as Kind 14 (Constant) with Variable/Property children.
        They should be promoted to METHOD so their bodies are scanned for call sites.
        """
        adapter = self._make_adapter()
        prop_child = self._make_raw("meetings", 7, children=[], line=3)  # Property
        component = self._make_raw("MyComponent", 14, children=[prop_child], line=0, end_line=20)

        result: list = []
        adapter._traverse(component, "/proj/src/MyComponent.tsx", parent_full_name=None, result=result)

        assert len(result) == 2
        assert result[0].kind == SymbolKind.METHOD
        assert result[0].name == "MyComponent"
        assert result[0].signature == "const_function"
        assert result[1].kind == SymbolKind.PROPERTY
        assert result[1].parent_full_name == result[0].full_name

    def test_const_with_variable_children_promoted_to_method(self) -> None:
        """const useMyHook = () => { const x = ... } -> Variable children only -> :Method."""
        adapter = self._make_adapter()
        var_child = self._make_raw("data", 13, line=2)  # Variable, no children
        hook = self._make_raw("useMyHook", 14, children=[var_child], line=0, end_line=15)

        result: list = []
        adapter._traverse(hook, "/proj/src/hooks.ts", parent_full_name=None, result=result)

        # Variable child without children is skipped, but hook itself is promoted to METHOD
        assert len(result) == 1
        assert result[0].kind == SymbolKind.METHOD
        assert result[0].name == "useMyHook"
        assert result[0].signature == "const_function"

    def test_const_with_mixed_children_promoted_to_class(self) -> None:
        """Object literal with at least one Method child -> CLASS (existing behavior)."""
        adapter = self._make_adapter()
        method_child = self._make_raw("getData", 6, children=[], line=2)
        prop_child = self._make_raw("baseUrl", 7, children=[], line=5)
        obj = self._make_raw("apiClient", 14, children=[method_child, prop_child], line=0, end_line=10)

        result: list = []
        adapter._traverse(obj, "/proj/src/api.ts", parent_full_name=None, result=result)

        assert result[0].kind == SymbolKind.CLASS
        assert result[0].signature == "const_object"


class TestConvertAsClass:
    """Tests for _convert_as_class method."""

    def _make_adapter(self) -> object:
        from synapps.lsp.typescript import TypeScriptLSPAdapter
        return TypeScriptLSPAdapter(MagicMock(), "/proj")

    def test_produces_class_kind_with_const_object_signature(self) -> None:
        adapter = self._make_adapter()
        raw = {
            "name": "myService",
            "kind": 14,
            "location": {"range": {"start": {"line": 5}, "end": {"line": 20}}},
        }
        sym = adapter._convert_as_class(raw, "/proj/src/svc.ts", "/proj", parent_full_name=None)
        assert sym.kind == SymbolKind.CLASS
        assert sym.signature == "const_object"
        assert sym.name == "myService"
        assert sym.full_name == "src/svc.myService"
        assert sym.line == 6
        assert sym.end_line == 21
        assert sym.parent_full_name is None


def test_shutdown_calls_stop() -> None:
    from synapps.lsp.typescript import TypeScriptLSPAdapter

    mock_ls = MagicMock()
    adapter = TypeScriptLSPAdapter(mock_ls, "/proj")
    adapter.shutdown()
    mock_ls.stop.assert_called_once()


# ---------------------------------------------------------------------------
# Regression: 1-based line number conversion (TD9-01)
# ---------------------------------------------------------------------------

def test_line_numbers_are_1_based() -> None:
    """TD9-01: _convert, _convert_as_method, and _convert_as_class all add +1 to LSP 0-based lines.

    TypeScript LSP returns 0-based line numbers. All three conversion paths must produce
    1-based IndexSymbol.line and end_line values.
    """
    from synapps.lsp.typescript import TypeScriptLSPAdapter

    adapter = TypeScriptLSPAdapter(MagicMock(), "/proj")
    raw = {
        "name": "myFunc",
        "kind": 12,  # Function
        "location": {"range": {"start": {"line": 0, "character": 0}, "end": {"line": 9, "character": 0}}},
    }

    # _convert path
    sym = adapter._convert(raw, "/proj/src/mod.ts", "/proj", parent_full_name=None)
    assert sym is not None
    assert sym.line == 1, f"_convert: Expected line=1, got {sym.line}"
    assert sym.end_line == 10, f"_convert: Expected end_line=10, got {sym.end_line}"

    # _convert_as_method path
    sym_m = adapter._convert_as_method(raw, "/proj/src/mod.ts", "/proj", parent_full_name=None)
    assert sym_m.line == 1, f"_convert_as_method: Expected line=1, got {sym_m.line}"
    assert sym_m.end_line == 10, f"_convert_as_method: Expected end_line=10, got {sym_m.end_line}"

    # _convert_as_class path
    sym_c = adapter._convert_as_class(raw, "/proj/src/mod.ts", "/proj", parent_full_name=None)
    assert sym_c.line == 1, f"_convert_as_class: Expected line=1, got {sym_c.line}"
    assert sym_c.end_line == 10, f"_convert_as_class: Expected end_line=10, got {sym_c.end_line}"


# ---------------------------------------------------------------------------
# _is_noise_symbol — callback, <unknown>, and array-literal filtering
# ---------------------------------------------------------------------------

class TestIsNoiseSymbol:
    """Regression tests for tsserver-synthesized noise symbols (Issues 1-5, 7)."""

    def test_callback_suffix_is_noise(self) -> None:
        """Issue 1: .map() callback, forEach() callback, etc."""
        from synapps.lsp.typescript import _is_noise_symbol
        assert _is_noise_symbol({"name": ".map() callback", "kind": 6}) is True
        assert _is_noise_symbol({"name": "forEach() callback", "kind": 6}) is True
        assert _is_noise_symbol({"name": "useEffect() callback", "kind": 12}) is True
        assert _is_noise_symbol({"name": "describe('test suite') callback", "kind": 12}) is True
        assert _is_noise_symbol({"name": "it('should work') callback", "kind": 12}) is True

    def test_unknown_is_noise(self) -> None:
        """Issue 2: <unknown> JSX fragment placeholders."""
        from synapps.lsp.typescript import _is_noise_symbol
        assert _is_noise_symbol({"name": "<unknown>", "kind": 7}) is True

    def test_empty_name_is_noise(self) -> None:
        from synapps.lsp.typescript import _is_noise_symbol
        assert _is_noise_symbol({"name": "", "kind": 6}) is True
        assert _is_noise_symbol({"kind": 6}) is True

    def test_array_literal_is_noise(self) -> None:
        """Issue 5: [1, 2, 3, 4] as parent scope name."""
        from synapps.lsp.typescript import _is_noise_symbol
        assert _is_noise_symbol({"name": "[1, 2, 3, 4]", "kind": 13}) is True

    def test_css_class_callback_is_noise(self) -> None:
        """Issue 4: .map("cursor-pointer") callback with CSS class strings."""
        from synapps.lsp.typescript import _is_noise_symbol
        assert _is_noise_symbol({"name": '.map("cursor-pointer") callback', "kind": 6}) is True
        assert _is_noise_symbol({"name": '.map("font-medium mb-1") callback', "kind": 6}) is True

    def test_legitimate_names_not_noise(self) -> None:
        """Ensure real symbols are not false-positived."""
        from synapps.lsp.typescript import _is_noise_symbol
        assert _is_noise_symbol({"name": "CallbackHandler", "kind": 5}) is False
        assert _is_noise_symbol({"name": "handleCallback", "kind": 6}) is False
        assert _is_noise_symbol({"name": "MyComponent", "kind": 12}) is False
        assert _is_noise_symbol({"name": "constructor", "kind": 9}) is False
        assert _is_noise_symbol({"name": "getData", "kind": 6}) is False


class TestTraverseNoiseFiltering:
    """Regression: _traverse skips noise symbols and their entire subtrees."""

    def _make_adapter(self) -> object:
        from synapps.lsp.typescript import TypeScriptLSPAdapter
        return TypeScriptLSPAdapter(MagicMock(), "/proj")

    def _make_raw(self, name: str, kind: int, children: list | None = None,
                  line: int = 0, end_line: int = 10) -> dict:
        raw: dict = {
            "name": name,
            "kind": kind,
            "location": {"range": {"start": {"line": line}, "end": {"line": end_line}}},
        }
        if children is not None:
            raw["children"] = children
        return raw

    def test_callback_children_pruned_from_class(self) -> None:
        """Issue 1/7: Callbacks inside a class are not indexed."""
        adapter = self._make_adapter()
        callback = self._make_raw(".map() callback", 6, children=[
            self._make_raw("inner", 6, children=[], line=5),
        ], line=3)
        real_method = self._make_raw("getData", 6, children=[], line=1)
        cls = self._make_raw("MyClass", 5, children=[real_method, callback])

        result: list = []
        adapter._traverse(cls, "/proj/src/mod.ts", parent_full_name=None, result=result)

        names = [s.name for s in result]
        assert "MyClass" in names
        assert "getData" in names
        assert ".map() callback" not in names
        assert "inner" not in names  # subtree also pruned

    def test_unknown_property_pruned(self) -> None:
        """Issue 2: <unknown> properties are not indexed."""
        adapter = self._make_adapter()
        unknown = self._make_raw("<unknown>", 7, children=[], line=5)
        component = self._make_raw("NotesList", 12, children=[unknown])

        result: list = []
        adapter._traverse(component, "/proj/src/NotesList.tsx", parent_full_name=None, result=result)

        names = [s.name for s in result]
        assert "NotesList" in names
        assert "<unknown>" not in names

    def test_test_file_describe_it_pruned(self) -> None:
        """Issue 7: describe/it callbacks in test files are not indexed."""
        adapter = self._make_adapter()
        it_cb = self._make_raw("it('should delete') callback", 12, children=[], line=5)
        describe_cb = self._make_raw("describe('deleteMeeting') callback", 12,
                                     children=[it_cb], line=2)
        root_describe = self._make_raw("describe('meetingService') callback", 12,
                                       children=[describe_cb])

        result: list = []
        adapter._traverse(root_describe, "/proj/src/meeting.test.ts",
                          parent_full_name=None, result=result)
        assert result == []

    def test_array_literal_parent_pruned(self) -> None:
        """Issue 5: Array literal scoping nodes and their subtrees are pruned."""
        adapter = self._make_adapter()
        inner = self._make_raw(".map() callback", 6, children=[], line=3)
        array_lit = self._make_raw("[1, 2, 3, 4]", 13, children=[inner], line=1)

        result: list = []
        adapter._traverse(array_lit, "/proj/src/skeleton.tsx",
                          parent_full_name="src/skeleton.DashboardSkeleton", result=result)
        assert result == []


# ---------------------------------------------------------------------------
# col extraction from selectionRange (Issue 6)
# ---------------------------------------------------------------------------

class TestColExtraction:
    """Regression: all three _convert paths extract col from selectionRange."""

    def _make_adapter(self) -> object:
        from synapps.lsp.typescript import TypeScriptLSPAdapter
        return TypeScriptLSPAdapter(MagicMock(), "/proj")

    def _make_raw_with_selection_range(self, name: str, kind: int,
                                       sel_char: int = 4) -> dict:
        return {
            "name": name,
            "kind": kind,
            "location": {"range": {
                "start": {"line": 5, "character": 0},
                "end": {"line": 15, "character": 0},
            }},
            "selectionRange": {
                "start": {"line": 5, "character": sel_char},
                "end": {"line": 5, "character": sel_char + len(name)},
            },
        }

    def test_convert_extracts_col(self) -> None:
        adapter = self._make_adapter()
        raw = self._make_raw_with_selection_range("myMethod", 6, sel_char=8)
        sym = adapter._convert(raw, "/proj/src/mod.ts", "/proj", parent_full_name=None)
        assert sym is not None
        assert sym.col == 8

    def test_convert_as_method_extracts_col(self) -> None:
        adapter = self._make_adapter()
        raw = self._make_raw_with_selection_range("MyComponent", 14, sel_char=13)
        sym = adapter._convert_as_method(raw, "/proj/src/comp.tsx", "/proj", parent_full_name=None)
        assert sym.col == 13

    def test_convert_as_class_extracts_col(self) -> None:
        adapter = self._make_adapter()
        raw = self._make_raw_with_selection_range("myService", 14, sel_char=13)
        sym = adapter._convert_as_class(raw, "/proj/src/svc.ts", "/proj", parent_full_name=None)
        assert sym.col == 13

    def test_col_falls_back_to_location_range_when_no_selection_range(self) -> None:
        adapter = self._make_adapter()
        raw = {
            "name": "myFunc",
            "kind": 12,
            "location": {"range": {
                "start": {"line": 2, "character": 7},
                "end": {"line": 10, "character": 0},
            }},
        }
        sym = adapter._convert(raw, "/proj/src/mod.ts", "/proj", parent_full_name=None)
        assert sym is not None
        assert sym.col == 7

    def test_col_defaults_to_zero_when_character_missing(self) -> None:
        adapter = self._make_adapter()
        raw = {
            "name": "myFunc",
            "kind": 12,
            "location": {"range": {"start": {"line": 0}, "end": {"line": 5}}},
        }
        sym = adapter._convert(raw, "/proj/src/mod.ts", "/proj", parent_full_name=None)
        assert sym is not None
        assert sym.col == 0
