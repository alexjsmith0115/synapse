from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from synapps.lsp.interface import IndexSymbol, SymbolKind
from synapps.lsp.java import JavaLSPAdapter, _LSP_KIND_MAP, _detect_java_source_root, _build_java_full_name, _clean_java_full_name


# ---------------------------------------------------------------------------
# _LSP_KIND_MAP coverage
# ---------------------------------------------------------------------------

class TestLSPKindMap:
    def test_class_mapping(self) -> None:
        assert _LSP_KIND_MAP[5] == SymbolKind.CLASS

    def test_method_mapping(self) -> None:
        assert _LSP_KIND_MAP[6] == SymbolKind.METHOD

    def test_constructor_mapping(self) -> None:
        assert _LSP_KIND_MAP[9] == SymbolKind.METHOD

    def test_interface_mapping(self) -> None:
        assert _LSP_KIND_MAP[11] == SymbolKind.INTERFACE

    def test_enum_mapping(self) -> None:
        assert _LSP_KIND_MAP[10] == SymbolKind.ENUM

    def test_field_mapping(self) -> None:
        assert _LSP_KIND_MAP[8] == SymbolKind.FIELD

    def test_constant_mapping(self) -> None:
        """D-23: static final fields (kind 14) map to FIELD."""
        assert _LSP_KIND_MAP[14] == SymbolKind.FIELD

    def test_namespace_mapping(self) -> None:
        assert _LSP_KIND_MAP[3] == SymbolKind.NAMESPACE

    def test_property_mapping(self) -> None:
        assert _LSP_KIND_MAP[7] == SymbolKind.PROPERTY

    def test_function_mapping(self) -> None:
        assert _LSP_KIND_MAP[12] == SymbolKind.METHOD


# ---------------------------------------------------------------------------
# _clean_java_full_name tests
# ---------------------------------------------------------------------------

class TestCleanJavaFullName:
    def test_strips_directory_prefix_com(self) -> None:
        assert _clean_java_full_name("....core.src.main.java.com.graphhopper.routing.Path") == "com.graphhopper.routing.Path"

    def test_strips_directory_prefix_org(self) -> None:
        assert _clean_java_full_name("....lib.src.main.java.org.example.Foo") == "org.example.Foo"

    def test_strips_dotdot_segments(self) -> None:
        assert _clean_java_full_name("............core.src.main.java.com.graphhopper.routing.Path") == "com.graphhopper.routing.Path"

    def test_preserves_clean_name(self) -> None:
        assert _clean_java_full_name("com.graphhopper.routing.Path") == "com.graphhopper.routing.Path"

    def test_preserves_name_without_known_prefix(self) -> None:
        assert _clean_java_full_name("mycompany.internal.Foo") == "mycompany.internal.Foo"

    def test_handles_nested_class(self) -> None:
        assert _clean_java_full_name("....core.src.main.java.com.example.Outer.Inner") == "com.example.Outer.Inner"

    def test_handles_method(self) -> None:
        assert _clean_java_full_name("....core.src.main.java.com.example.Foo.bar") == "com.example.Foo.bar"

    def test_preserves_io_prefix(self) -> None:
        assert _clean_java_full_name("....src.main.java.io.grpc.Server") == "io.grpc.Server"

    def test_preserves_net_prefix(self) -> None:
        assert _clean_java_full_name("....src.main.java.net.example.Foo") == "net.example.Foo"

    def test_preserves_dev_prefix(self) -> None:
        assert _clean_java_full_name("src.main.java.dev.example.Foo") == "dev.example.Foo"


# ---------------------------------------------------------------------------
# _detect_java_source_root tests
# ---------------------------------------------------------------------------

class TestDetectJavaSourceRoot:
    def test_maven_src_main_java(self) -> None:
        root = _detect_java_source_root(
            "/proj/src/main/java/com/synappstest/Animal.java", "/proj"
        )
        assert root == "/proj/src/main/java"

    def test_maven_src_test_java(self) -> None:
        root = _detect_java_source_root(
            "/proj/src/test/java/com/synappstest/AnimalTest.java", "/proj"
        )
        assert root == "/proj/src/test/java"

    def test_simple_src_java(self) -> None:
        """src/java layout (no main/test)."""
        root = _detect_java_source_root(
            "/proj/src/java/com/test/Foo.java", "/proj"
        )
        assert root == "/proj/src/java"

    def test_flat_layout_fallback(self) -> None:
        """No conventional java source dir -> fallback to root_path."""
        root = _detect_java_source_root(
            "/proj/Foo.java", "/proj"
        )
        assert root == "/proj"

    def test_src_only_no_java_dir(self) -> None:
        """src/com/test/Foo.java - 'src' contains package dirs directly."""
        # No 'java' dir in path, so fallback to root_path
        root = _detect_java_source_root(
            "/proj/src/com/test/Foo.java", "/proj"
        )
        assert root == "/proj"

    def test_src_main_fallback_when_no_java_dir(self) -> None:
        """When there's no 'java' directory, fall back to src/main."""
        result = _detect_java_source_root(
            "/proj/core/src/main/com/example/Foo.java", "/proj"
        )
        assert result == "/proj/core/src/main"

    def test_src_test_fallback_when_no_java_dir(self) -> None:
        result = _detect_java_source_root(
            "/proj/module/src/test/com/example/FooTest.java", "/proj"
        )
        assert result == "/proj/module/src/test"


# ---------------------------------------------------------------------------
# _build_java_full_name tests
# ---------------------------------------------------------------------------

class TestBuildJavaFullName:
    def test_class_with_package(self) -> None:
        """Top-level class derives package from file path."""
        ns_parent = {"name": "com.synappstest", "kind": 3}
        raw = {"name": "Animal", "kind": 5, "parent": ns_parent}
        result = _build_java_full_name(raw, "com/synappstest/Animal.java", "/src")
        # source_root is /src, file is at /src/com/synappstest/Animal.java
        result = _build_java_full_name(
            raw,
            "/src/com/synappstest/Animal.java",
            "/src",
        )
        assert result == "com.synappstest.Animal"

    def test_method_with_package(self) -> None:
        """Nested method: package from path + class.method from symbol chain."""
        ns = {"name": "com.synappstest", "kind": 3}
        cls_parent = {"name": "Animal", "kind": 5, "parent": ns}
        raw = {"name": "speak", "kind": 6, "parent": cls_parent}
        result = _build_java_full_name(
            raw,
            "/src/com/synappstest/Animal.java",
            "/src",
        )
        assert result == "com.synappstest.Animal.speak"

    def test_namespace_parent_is_skipped(self) -> None:
        """NAMESPACE (kind=3) parents are excluded from symbol_suffix since package comes from path."""
        ns = {"name": "com.synappstest", "kind": 3}
        raw = {"name": "Animal", "kind": 5, "parent": ns}
        result = _build_java_full_name(
            raw,
            "/src/com/synappstest/Animal.java",
            "/src",
        )
        # Should NOT be com.synappstest.com.synappstest.Animal (no double package)
        assert result == "com.synappstest.Animal"

    def test_nested_class_method(self) -> None:
        """Inner method: com.synappstest.Router.route."""
        ns = {"name": "com.synappstest", "kind": 3}
        cls_parent = {"name": "Router", "kind": 5, "parent": ns}
        raw = {"name": "route", "kind": 6, "parent": cls_parent}
        result = _build_java_full_name(
            raw,
            "/src/com/synappstest/Router.java",
            "/src",
        )
        assert result == "com.synappstest.Router.route"

    def test_no_package_prefix(self) -> None:
        """File at source root directly (no package subdirs)."""
        raw = {"name": "Main", "kind": 5}
        result = _build_java_full_name(raw, "/proj/Main.java", "/proj")
        assert result == "Main"

    def test_overload_idx_appended(self) -> None:
        """Overloaded method includes parameter signature."""
        ns = {"name": "com.test", "kind": 3}
        cls_parent = {"name": "Foo", "kind": 5, "parent": ns}
        raw = {
            "name": "bar",
            "kind": 6,
            "parent": cls_parent,
            "overload_idx": 1,
            "detail": "void bar(int x)",
        }
        result = _build_java_full_name(
            raw,
            "/src/com/test/Foo.java",
            "/src",
        )
        assert result == "com.test.Foo.bar(int x)"


# ---------------------------------------------------------------------------
# _convert tests
# ---------------------------------------------------------------------------

def _make_adapter(root_path: str = "/proj", source_root: str | None = None) -> JavaLSPAdapter:
    """Create adapter with a mock language server (no real LSP needed for _convert)."""
    adapter = JavaLSPAdapter(MagicMock(), root_path)
    if source_root is not None:
        adapter._source_root = source_root
    return adapter


def _make_raw(
    name: str,
    kind: int,
    parent: dict | None = None,
    detail: str = "",
    start_line: int = 0,
    end_line: int = 0,
) -> dict:
    raw: dict = {
        "name": name,
        "kind": kind,
        "detail": detail,
        "location": {
            "range": {
                "start": {"line": start_line, "character": 0},
                "end": {"line": end_line, "character": 0},
            }
        },
    }
    if parent is not None:
        raw["parent"] = parent
    return raw


class TestConvert:
    def test_convert_class_symbol(self) -> None:
        parent = {"name": "com.graphhopper.routing", "kind": 3}
        raw = _make_raw("Router", 5, parent=parent, start_line=10, end_line=100)
        adapter = _make_adapter(
            root_path="/proj",
            source_root="/proj/src/main/java",
        )
        sym = adapter._convert(
            raw,
            "/proj/src/main/java/com/graphhopper/routing/Router.java",
            parent_full_name=None,
        )

        assert sym.full_name == "com.graphhopper.routing.Router"
        assert sym.kind == SymbolKind.CLASS
        assert sym.name == "Router"
        assert sym.line == 10
        assert sym.end_line == 100

    def test_convert_method_symbol(self) -> None:
        grandparent = {"name": "com.graphhopper.routing", "kind": 3}
        parent = {"name": "Router", "kind": 5, "parent": grandparent}
        raw = _make_raw("route", 6, parent=parent, detail="public GHResponse route(GHRequest req)")
        adapter = _make_adapter(
            root_path="/proj",
            source_root="/proj/src/main/java",
        )
        sym = adapter._convert(
            raw,
            "/proj/src/main/java/com/graphhopper/routing/Router.java",
            parent_full_name="com.graphhopper.routing.Router",
        )

        assert sym.full_name == "com.graphhopper.routing.Router.route"
        assert sym.kind == SymbolKind.METHOD
        assert sym.signature == "public GHResponse route(GHRequest req)"

    def test_convert_constructor(self) -> None:
        ns = {"name": "com.test", "kind": 3}
        parent = {"name": "Router", "kind": 5, "parent": ns}
        raw = _make_raw("Router", 9, parent=parent)
        adapter = _make_adapter(root_path="/proj", source_root="/proj/src/main/java")
        sym = adapter._convert(
            raw,
            "/proj/src/main/java/com/test/Router.java",
            parent_full_name="com.test.Router",
        )

        assert sym.kind == SymbolKind.METHOD
        assert sym.parent_full_name == "com.test.Router"

    def test_convert_interface(self) -> None:
        parent = {"name": "com.graphhopper.routing", "kind": 3}
        raw = _make_raw("RoutingAlgorithm", 11, parent=parent)
        adapter = _make_adapter(root_path="/proj", source_root="/proj/src/main/java")
        sym = adapter._convert(
            raw,
            "/proj/src/main/java/com/graphhopper/routing/RoutingAlgorithm.java",
            parent_full_name=None,
        )

        assert sym.kind == SymbolKind.INTERFACE
        assert sym.full_name == "com.graphhopper.routing.RoutingAlgorithm"

    def test_convert_constant(self) -> None:
        """D-23: kind 14 (constant) maps to FIELD."""
        ns = {"name": "com.test", "kind": 3}
        parent = {"name": "Router", "kind": 5, "parent": ns}
        raw = _make_raw("MAX_RETRIES", 14, parent=parent, detail="public static final int")
        adapter = _make_adapter(root_path="/proj", source_root="/proj/src/main/java")
        sym = adapter._convert(
            raw,
            "/proj/src/main/java/com/test/Router.java",
            parent_full_name="com.test.Router",
        )

        assert sym.kind == SymbolKind.FIELD
        assert sym.is_static is True

    def test_convert_abstract_method(self) -> None:
        ns = {"name": "com.test", "kind": 3}
        parent = {"name": "Animal", "kind": 5, "parent": ns}
        raw = _make_raw("speak", 6, parent=parent, detail="public abstract void speak()")
        adapter = _make_adapter(root_path="/proj", source_root="/proj/src/main/java")
        sym = adapter._convert(
            raw,
            "/proj/src/main/java/com/test/Animal.java",
            parent_full_name="com.test.Animal",
        )

        assert sym.is_abstract is True

    def test_convert_static_method(self) -> None:
        ns = {"name": "com.test", "kind": 3}
        parent = {"name": "Util", "kind": 5, "parent": ns}
        raw = _make_raw("helper", 6, parent=parent, detail="public static void helper()")
        adapter = _make_adapter(root_path="/proj", source_root="/proj/src/main/java")
        sym = adapter._convert(
            raw,
            "/proj/src/main/java/com/test/Util.java",
            parent_full_name="com.test.Util",
        )

        assert sym.is_static is True

    def test_convert_unmapped_kind_defaults_to_class(self) -> None:
        raw = _make_raw("Unknown", 999)
        adapter = _make_adapter(root_path="/proj", source_root="/proj")
        sym = adapter._convert(raw, "/proj/Foo.java", parent_full_name=None)

        assert sym.kind == SymbolKind.CLASS


# ---------------------------------------------------------------------------
# get_workspace_files tests
# ---------------------------------------------------------------------------

class TestGetWorkspaceFiles:
    def test_excludes_build_dirs(self, tmp_path: Path) -> None:
        """D-03: target, build, .gradle and other build dirs are excluded."""
        # Create included files
        src_dir = tmp_path / "src" / "main" / "java"
        src_dir.mkdir(parents=True)
        (src_dir / "Main.java").touch()

        # Create excluded files
        for excluded in ["target", "build", ".gradle", ".idea", "bin", ".settings", ".mvn"]:
            d = tmp_path / excluded / "sub"
            d.mkdir(parents=True)
            (d / "Excluded.java").touch()

        adapter = _make_adapter(root_path=str(tmp_path))
        files = adapter.get_workspace_files(str(tmp_path))

        assert len(files) == 1
        assert files[0].endswith("Main.java")

    def test_returns_only_java_files(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "Main.java").touch()
        (src / "readme.md").touch()
        (src / "pom.xml").touch()

        adapter = _make_adapter(root_path=str(tmp_path))
        files = adapter.get_workspace_files(str(tmp_path))

        assert len(files) == 1
        assert files[0].endswith("Main.java")

    def test_returns_absolute_paths(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "App.java").touch()

        adapter = _make_adapter(root_path=str(tmp_path))
        files = adapter.get_workspace_files(str(tmp_path))

        assert len(files) == 1
        assert os.path.isabs(files[0])


# ---------------------------------------------------------------------------
# get_document_symbols integration
# ---------------------------------------------------------------------------

class TestGetDocumentSymbols:
    def test_returns_symbols_from_root(self) -> None:
        class_raw = _make_raw("Router", 5, start_line=5, end_line=50)
        class_raw["children"] = []

        mock_result = MagicMock()
        mock_result.root_symbols = [class_raw]
        mock_ls = MagicMock()
        mock_ls.request_document_symbols.return_value = mock_result

        adapter = JavaLSPAdapter(mock_ls, "/proj")
        adapter._source_root = "/proj"
        symbols = adapter.get_document_symbols("/proj/Router.java")

        assert len(symbols) == 1
        assert symbols[0].name == "Router"

    def test_returns_empty_on_none(self) -> None:
        mock_ls = MagicMock()
        mock_ls.request_document_symbols.return_value = None

        adapter = JavaLSPAdapter(mock_ls, "/proj")
        symbols = adapter.get_document_symbols("/proj/Missing.java")

        assert symbols == []

    def test_traverse_sets_parent_full_name(self) -> None:
        method_raw = _make_raw("route", 6, detail="void route()")
        method_raw["children"] = []
        parent = {"name": "com.test", "kind": 3}
        class_raw = _make_raw("Router", 5, parent=parent)
        class_raw["children"] = [method_raw]

        mock_result = MagicMock()
        mock_result.root_symbols = [class_raw]
        mock_ls = MagicMock()
        mock_ls.request_document_symbols.return_value = mock_result

        adapter = JavaLSPAdapter(mock_ls, "/proj")
        adapter._source_root = "/proj/src/main/java"
        symbols = adapter.get_document_symbols("/proj/src/main/java/com/test/Router.java")

        method = next(s for s in symbols if s.name == "route")
        assert method.parent_full_name == "com.test.Router"

    def test_returns_empty_on_exception(self) -> None:
        mock_ls = MagicMock()
        mock_ls.request_document_symbols.side_effect = RuntimeError("LSP failed")

        adapter = JavaLSPAdapter(mock_ls, "/proj")
        symbols = adapter.get_document_symbols("/proj/Broken.java")

        assert symbols == []


# ---------------------------------------------------------------------------
# TestConvertSelectionRange — regression test for Javadoc line fix (JF-01)
# ---------------------------------------------------------------------------

class TestConvertSelectionRange:
    def test_uses_selection_range_start_line_when_present(self) -> None:
        """JF-01: selectionRange.start.line is used for IndexSymbol.line, not location.range.start.line.

        Javadoc causes location.range.start.line to point at the /** line, while
        selectionRange.start.line points at the 'class'/'interface' keyword — the
        value that LSP definition lookups return. Both symbol_map and base_type_symbol_map
        are keyed by (file_path, line) and must match.
        """
        raw = {
            "name": "Animal",
            "kind": 5,
            "detail": "",
            "location": {
                "uri": "file:///proj/src/main/java/com/test/Animal.java",
                "range": {
                    "start": {"line": 3, "character": 0},
                    "end": {"line": 20, "character": 1},
                },
            },
            "selectionRange": {
                "start": {"line": 7, "character": 13},
                "end": {"line": 7, "character": 19},
            },
        }
        adapter = _make_adapter(root_path="/proj", source_root="/proj/src/main/java")
        sym = adapter._convert(raw, "/proj/src/main/java/com/test/Animal.java", parent_full_name=None)

        assert sym.line == 7, "line must use selectionRange.start.line, not location.range.start.line"
        assert sym.end_line == 20, "end_line must still use location.range.end.line"

    def test_falls_back_to_location_range_when_selection_range_absent(self) -> None:
        """Backward compat: when selectionRange is not present, use location.range.start.line."""
        raw = {
            "name": "Animal",
            "kind": 5,
            "detail": "",
            "location": {
                "uri": "file:///proj/src/main/java/com/test/Animal.java",
                "range": {
                    "start": {"line": 5, "character": 0},
                    "end": {"line": 15, "character": 1},
                },
            },
        }
        adapter = _make_adapter(root_path="/proj", source_root="/proj/src/main/java")
        sym = adapter._convert(raw, "/proj/src/main/java/com/test/Animal.java", parent_full_name=None)

        assert sym.line == 5
        assert sym.end_line == 15

    def test_end_line_not_taken_from_selection_range(self) -> None:
        """selectionRange covers only the declaration name; end_line must use location.range.end."""
        raw = {
            "name": "Animal",
            "kind": 5,
            "detail": "",
            "location": {
                "uri": "file:///proj/src/main/java/com/test/Animal.java",
                "range": {
                    "start": {"line": 3, "character": 0},
                    "end": {"line": 50, "character": 1},
                },
            },
            "selectionRange": {
                "start": {"line": 7, "character": 13},
                "end": {"line": 7, "character": 19},
            },
        }
        adapter = _make_adapter(root_path="/proj", source_root="/proj/src/main/java")
        sym = adapter._convert(raw, "/proj/src/main/java/com/test/Animal.java", parent_full_name=None)

        assert sym.end_line == 50, "end_line is the class body extent, not the selectionRange end"
        assert sym.line == 7


# ---------------------------------------------------------------------------
# Stub methods
# ---------------------------------------------------------------------------

class TestStubs:
    def test_find_method_calls_returns_empty(self) -> None:
        adapter = _make_adapter()
        sym = IndexSymbol(
            name="route", full_name="com.test.Router.route",
            kind=SymbolKind.METHOD, file_path="/proj/Router.java", line=10,
        )
        assert adapter.find_method_calls(sym) == []

    def test_find_overridden_method_returns_none(self) -> None:
        adapter = _make_adapter()
        sym = IndexSymbol(
            name="speak", full_name="com.test.Dog.speak",
            kind=SymbolKind.METHOD, file_path="/proj/Dog.java", line=5,
        )
        assert adapter.find_overridden_method(sym) is None
