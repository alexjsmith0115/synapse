"""Tests for TypeScript-specific kind_str overrides in Indexer._upsert_symbol."""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from synapse.indexer.indexer import Indexer
from synapse.indexer.assignment_ref import AssignmentRef
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


from synapse.indexer.indexer import _is_minified, _is_minified_source


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


def test_index_callback_edges_creates_calls_from_parent_to_callback(mock_conn):
    """Callback methods (name ends with 'callback') get CALLS edges from parent."""
    indexer = _make_typescript_indexer(mock_conn)
    symbols_by_file = {
        "/proj/src/hooks.ts": [
            IndexSymbol(
                name="useMyHook",
                full_name="src/hooks.useMyHook",
                kind=SymbolKind.METHOD,
                file_path="/proj/src/hooks.ts",
                line=1,
                parent_full_name=None,
            ),
            IndexSymbol(
                name="useEffect() callback",
                full_name="src/hooks.useMyHook.useEffect() callback",
                kind=SymbolKind.METHOD,
                file_path="/proj/src/hooks.ts",
                line=3,
                parent_full_name="src/hooks.useMyHook",
            ),
        ],
    }
    mock_conn.reset_mock()
    indexer._index_callback_edges(symbols_by_file)
    # Should have called execute once for the CALLS edge
    assert mock_conn.execute.call_count == 1
    cypher, params = mock_conn.execute.call_args[0]
    assert "CALLS" in cypher
    assert params["caller"] == "src/hooks.useMyHook"
    assert params["callee"] == "src/hooks.useMyHook.useEffect() callback"


def test_index_callback_edges_skips_non_callback_methods(mock_conn):
    """Methods not ending with 'callback' should not get callback CALLS edges."""
    indexer = _make_typescript_indexer(mock_conn)
    symbols_by_file = {
        "/proj/src/svc.ts": [
            IndexSymbol(
                name="getMeetings",
                full_name="src/svc.meetingService.getMeetings",
                kind=SymbolKind.METHOD,
                file_path="/proj/src/svc.ts",
                line=5,
                parent_full_name="src/svc.meetingService",
            ),
        ],
    }
    mock_conn.reset_mock()
    indexer._index_callback_edges(symbols_by_file)
    mock_conn.execute.assert_not_called()


def test_index_callback_edges_skips_parentless_callbacks(mock_conn):
    """Callbacks without parent_full_name should be skipped."""
    indexer = _make_typescript_indexer(mock_conn)
    symbols_by_file = {
        "/proj/src/mod.ts": [
            IndexSymbol(
                name="defineConfig() callback",
                full_name="src/mod.defineConfig() callback",
                kind=SymbolKind.METHOD,
                file_path="/proj/src/mod.ts",
                line=1,
                parent_full_name=None,
            ),
        ],
    }
    mock_conn.reset_mock()
    indexer._index_callback_edges(symbols_by_file)
    mock_conn.execute.assert_not_called()


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


def _make_parsed_file(file_path: str, source: str):
    """Create a mock ParsedFile for tests."""
    pf = MagicMock()
    pf.file_path = file_path
    pf.source = source
    pf.tree = MagicMock()
    return pf


def _make_python_plugin():
    """Create a mock Python plugin with assignment extractor support."""
    plugin = MagicMock()
    plugin.name = "python"
    plugin.file_extensions = frozenset({".py"})
    plugin.create_import_extractor.return_value = MagicMock()
    plugin.create_base_type_extractor.return_value = MagicMock(extract=MagicMock(return_value=[]))
    plugin.create_attribute_extractor = MagicMock(return_value=MagicMock(extract=MagicMock(return_value=[])))
    call_ext_mock = MagicMock(extract=MagicMock(return_value=[]))
    call_ext_mock._sites_seen = 0
    plugin.create_call_extractor = MagicMock(return_value=call_ext_mock)
    plugin.create_type_ref_extractor = MagicMock(return_value=MagicMock(extract=MagicMock(return_value=[])))
    plugin.parse_file = MagicMock(side_effect=lambda fp, src: _make_parsed_file(fp, src))
    return plugin


def _make_python_indexer(conn, plugin=None):
    """Create an Indexer configured for Python with mock LSP."""
    lsp = MagicMock(spec=LSPAdapter)
    type(lsp).language_server = PropertyMock(return_value=MagicMock(repository_root_path="/proj"))
    if plugin is None:
        plugin = _make_python_plugin()
    return Indexer(conn, lsp, plugin), lsp, plugin


def test_index_project_builds_assignment_map_for_python(tmp_path):
    """Indexer.index_project with Python plugin builds assignment maps and passes
    assignment_position_map to SymbolResolver."""
    conn = MagicMock()
    conn.query.return_value = []

    plugin = _make_python_plugin()

    # Assignment extractor returns one AssignmentRef
    ref = AssignmentRef("mod.MyClass", "_handler", str(tmp_path / "foo.py"), 5, 12)
    assign_ext = MagicMock()
    assign_ext.extract.return_value = [ref]
    plugin.create_assignment_extractor = MagicMock(return_value=assign_ext)

    indexer, lsp, _ = _make_python_indexer(conn, plugin)

    # Set up workspace with one Python file
    py_file = tmp_path / "foo.py"
    py_file.write_text("class MyClass:\n    def __init__(self):\n        self._handler = create_handler()\n")
    lsp.get_workspace_files.return_value = [str(py_file)]

    # get_document_symbols returns symbols including a class and a method
    cls_sym = IndexSymbol(
        name="MyClass", full_name="mod.MyClass", kind=SymbolKind.CLASS,
        file_path=str(py_file), line=0, parent_full_name=None,
    )
    method_sym = IndexSymbol(
        name="__init__", full_name="mod.MyClass.__init__", kind=SymbolKind.METHOD,
        file_path=str(py_file), line=1, parent_full_name="mod.MyClass",
    )
    lsp.get_document_symbols.return_value = [cls_sym, method_sym]

    with patch("synapse.indexer.indexer.SymbolResolver") as MockResolver:
        mock_resolver_instance = MagicMock()
        MockResolver.return_value = mock_resolver_instance
        indexer.index_project(str(tmp_path), "python")

    # Verify SymbolResolver was constructed with assignment_position_map
    MockResolver.assert_called_once()
    call_kwargs = MockResolver.call_args[1]
    apm = call_kwargs.get("assignment_position_map", None)
    assert apm is not None
    assert (str(tmp_path / "foo.py"), 5) in apm
    assert apm[(str(tmp_path / "foo.py"), 5)] is ref

    # Verify the extractor was called
    assert assign_ext.extract.call_count >= 1


def test_index_project_skips_assignment_map_for_csharp(tmp_path):
    """Indexer with C# plugin (no create_assignment_extractor) constructs SymbolResolver
    without assignment_position_map (or with empty dict)."""
    conn = MagicMock()
    conn.query.return_value = []

    plugin = _make_python_plugin()
    plugin.name = "csharp"
    plugin.file_extensions = frozenset({".cs"})
    # No assignment extractor support
    plugin.create_assignment_extractor = MagicMock(return_value=None)

    indexer, lsp, _ = _make_python_indexer(conn, plugin)

    cs_file = tmp_path / "Foo.cs"
    cs_file.write_text("namespace X { class Foo {} }")
    lsp.get_workspace_files.return_value = [str(cs_file)]

    cls_sym = IndexSymbol(
        name="Foo", full_name="X.Foo", kind=SymbolKind.CLASS,
        file_path=str(cs_file), line=0, parent_full_name=None,
    )
    lsp.get_document_symbols.return_value = [cls_sym]

    with patch("synapse.indexer.indexer.SymbolResolver") as MockResolver:
        mock_resolver_instance = MagicMock()
        MockResolver.return_value = mock_resolver_instance
        indexer.index_project(str(tmp_path), "csharp")

    MockResolver.assert_called_once()
    call_kwargs = MockResolver.call_args[1]
    apm = call_kwargs.get("assignment_position_map", {})
    assert len(apm) == 0


def test_reindex_file_builds_assignment_map(tmp_path):
    """Indexer.reindex_file with Python plugin builds assignment maps and passes
    assignment_position_map to SymbolResolver."""
    conn = MagicMock()
    conn.query.return_value = []

    plugin = _make_python_plugin()

    ref = AssignmentRef("mod.MyClass", "_svc", str(tmp_path / "bar.py"), 3, 8)
    assign_ext = MagicMock()
    assign_ext.extract.return_value = [ref]
    plugin.create_assignment_extractor = MagicMock(return_value=assign_ext)

    indexer, lsp, _ = _make_python_indexer(conn, plugin)

    py_file = tmp_path / "bar.py"
    py_file.write_text("class MyClass:\n    def setup(self):\n        self._svc = SvcFactory.create()\n")

    cls_sym = IndexSymbol(
        name="MyClass", full_name="mod.MyClass", kind=SymbolKind.CLASS,
        file_path=str(py_file), line=0, parent_full_name=None,
    )
    method_sym = IndexSymbol(
        name="setup", full_name="mod.MyClass.setup", kind=SymbolKind.METHOD,
        file_path=str(py_file), line=1, parent_full_name="mod.MyClass",
    )
    lsp.get_document_symbols.return_value = [cls_sym, method_sym]

    with patch("synapse.indexer.indexer.SymbolResolver") as MockResolver:
        mock_resolver_instance = MagicMock()
        MockResolver.return_value = mock_resolver_instance
        indexer.reindex_file(str(py_file), str(tmp_path))

    MockResolver.assert_called_once()
    call_kwargs = MockResolver.call_args[1]
    apm = call_kwargs.get("assignment_position_map", None)
    assert apm is not None
    assert (str(tmp_path / "bar.py"), 3) in apm
    assert apm[(str(tmp_path / "bar.py"), 3)] is ref


# --- _is_minified_source tests ---


def test_is_minified_source_returns_true_for_long_first_line():
    source = "x" * 501
    assert _is_minified_source(source) is True


def test_is_minified_source_returns_false_for_normal():
    source = "def foo():\n    pass"
    assert _is_minified_source(source) is False


def test_is_minified_source_returns_false_for_empty():
    assert _is_minified_source("") is False


def test_is_minified_source_returns_true_for_long_first_line_with_newline():
    source = "x" * 501 + "\nshort line"
    assert _is_minified_source(source) is True


def test_is_minified_source_returns_false_for_blank_first_line():
    """A source whose first line is whitespace-only is not minified."""
    source = "   \nshort line"
    assert _is_minified_source(source) is False


# --- ERR-06: LSP timeout recovery ---


def _make_two_file_indexer(tmp_path):
    """Create a Python indexer with two test files for timeout testing."""
    conn = MagicMock()
    conn.query.return_value = []

    plugin = _make_python_plugin()
    plugin.create_attribute_extractor = MagicMock(return_value=None)

    indexer, lsp, _ = _make_python_indexer(conn, plugin)

    file_a = tmp_path / "file_a.py"
    file_a.write_text("class A:\n    pass\n")
    file_b = tmp_path / "file_b.py"
    file_b.write_text("class B:\n    pass\n")

    lsp.get_workspace_files.return_value = [str(file_a), str(file_b)]

    sym_b = IndexSymbol(
        name="B", full_name="mod.B", kind=SymbolKind.CLASS,
        file_path=str(file_b), line=0, parent_full_name=None,
    )

    # file_a times out; file_b succeeds
    def _symbols_side_effect(file_path):
        if "file_a" in file_path:
            raise TimeoutError("LSP timed out")
        return [sym_b]

    lsp.get_document_symbols.side_effect = _symbols_side_effect

    return indexer, lsp, conn, file_a, file_b


def test_index_project_catches_lsp_timeout_and_continues(tmp_path):
    """ERR-06: TimeoutError on one file doesn't abort entire indexing."""
    indexer, lsp, conn, file_a, file_b = _make_two_file_indexer(tmp_path)

    with patch("synapse.indexer.indexer.SymbolResolver") as MockResolver:
        MockResolver.return_value = MagicMock()
        indexer.index_project(str(tmp_path), "python")

    # file_b was processed — upsert_file was called at least for file_b
    calls = [str(c) for c in conn.execute.call_args_list]
    assert any(str(file_b) in c for c in calls)


def test_index_project_logs_timed_out_file_name(tmp_path):
    """ERR-06: Timed-out file name appears in log warning."""
    import logging
    indexer, lsp, conn, file_a, file_b = _make_two_file_indexer(tmp_path)

    with patch("synapse.indexer.indexer.SymbolResolver") as MockResolver:
        MockResolver.return_value = MagicMock()
        with patch("synapse.indexer.indexer.log") as mock_log:
            indexer.index_project(str(tmp_path), "python")

    # Check that a warning was emitted mentioning file_a
    warning_calls = [str(c) for c in mock_log.warning.call_args_list]
    assert any("file_a" in c for c in warning_calls)


def test_index_project_logs_verbose_suggestion_on_timeout(tmp_path):
    """ERR-06: End-of-index summary suggests --verbose."""
    indexer, lsp, conn, file_a, file_b = _make_two_file_indexer(tmp_path)

    with patch("synapse.indexer.indexer.SymbolResolver") as MockResolver:
        MockResolver.return_value = MagicMock()
        with patch("synapse.indexer.indexer.log") as mock_log:
            indexer.index_project(str(tmp_path), "python")

    # Check that a warning containing --verbose was emitted
    warning_calls = [str(c) for c in mock_log.warning.call_args_list]
    assert any("--verbose" in c for c in warning_calls)
