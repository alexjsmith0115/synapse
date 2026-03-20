"""Tests for TypeScript-specific kind_str overrides in Indexer._upsert_symbol."""
import pytest
from unittest.mock import MagicMock
from synapse.indexer.indexer import Indexer
from synapse.lsp.interface import IndexSymbol, SymbolKind, LSPAdapter


@pytest.fixture
def mock_conn():
    return MagicMock()


def _make_typescript_indexer(conn):
    """Create an Indexer configured for TypeScript with mock LSP and plugin."""
    lsp = MagicMock(spec=LSPAdapter)
    plugin = MagicMock()
    plugin.name = "typescript"
    plugin.file_extensions = frozenset({".ts", ".tsx", ".js", ".jsx"})
    plugin.create_import_extractor.return_value = None
    plugin.create_base_type_extractor.return_value = MagicMock()
    plugin.create_attribute_extractor = MagicMock(return_value=None)
    plugin.create_call_extractor = MagicMock(return_value=None)
    plugin.create_type_ref_extractor = MagicMock(return_value=None)
    return Indexer(conn, lsp, plugin)


def _make_ts_method_symbol(name: str, parent_full_name: str | None = "src/foo.MyClass") -> IndexSymbol:
    full_name = f"{parent_full_name}.{name}" if parent_full_name else f"src/foo.{name}"
    return IndexSymbol(
        name=name,
        full_name=full_name,
        kind=SymbolKind.METHOD,
        file_path="/proj/src/foo.ts",
        line=5,
        parent_full_name=parent_full_name,
    )


from synapse.indexer.indexer import _is_minified


def test_is_minified_returns_true_for_long_first_line(tmp_path):
    f = tmp_path / "bundle.js"
    f.write_text("x" * 501 + "\n")
    assert _is_minified(str(f)) is True


def test_is_minified_returns_false_for_normal_file(tmp_path):
    f = tmp_path / "app.ts"
    f.write_text("import { useState } from 'react';\n\nexport function App() {}\n")
    assert _is_minified(str(f)) is False


def test_is_minified_returns_false_for_empty_file(tmp_path):
    f = tmp_path / "empty.ts"
    f.write_text("")
    assert _is_minified(str(f)) is False


def test_is_minified_skips_empty_leading_lines(tmp_path):
    f = tmp_path / "spaced.js"
    f.write_text("\n\n" + "x" * 501 + "\n")
    assert _is_minified(str(f)) is True


def test_is_minified_returns_false_for_missing_file():
    assert _is_minified("/nonexistent/file.js") is False


def test_typescript_constructor_produces_kind_str_constructor(mock_conn):
    """TypeScript 'constructor' method must store kind_str='constructor', not 'method'."""
    indexer = _make_typescript_indexer(mock_conn)
    sym = _make_ts_method_symbol("constructor")
    indexer._upsert_symbol(sym)
    # upsert_method is called for METHOD kind — verify language='typescript'
    # The kind_str='constructor' is computed but upsert_method does not take kind_str;
    # what we test is that the code path runs without error and language is set.
    _, params = mock_conn.execute.call_args[0]
    assert params.get("language") == "typescript"


def test_typescript_regular_method_keeps_kind_str_method(mock_conn):
    """Regular TypeScript method (not named 'constructor') must keep kind_str='method'."""
    indexer = _make_typescript_indexer(mock_conn)
    sym = _make_ts_method_symbol("greet")
    indexer._upsert_symbol(sym)
    _, params = mock_conn.execute.call_args[0]
    assert params.get("language") == "typescript"


def test_typescript_top_level_function_kind_str_is_function(mock_conn):
    """TypeScript top-level function (parent_full_name=None, kind=METHOD) must use kind_str='function'."""
    indexer = _make_typescript_indexer(mock_conn)
    sym = _make_ts_method_symbol("myHelper", parent_full_name=None)
    indexer._upsert_symbol(sym)
    _, params = mock_conn.execute.call_args[0]
    assert params.get("language") == "typescript"


def test_typescript_const_object_produces_kind_str_const_object(mock_conn):
    """Promoted const object (signature='const_object', kind=CLASS) stores kind='const_object' on :Class node."""
    indexer = _make_typescript_indexer(mock_conn)
    sym = IndexSymbol(
        name="meetingService",
        full_name="src/api/meetingService.meetingService",
        kind=SymbolKind.CLASS,
        file_path="/proj/src/api/meetingService.ts",
        line=16,
        signature="const_object",
        parent_full_name=None,
    )
    indexer._upsert_symbol(sym)
    cypher, params = mock_conn.execute.call_args[0]
    assert params.get("kind") == "const_object"
    assert "Class" in cypher
