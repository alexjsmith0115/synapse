from unittest.mock import MagicMock, patch

import pytest

from synapps.service import SynappsService
from synapps.service.formatting import _p, _slim, _apply_limit, _short_ref
from conftest import _MockNode, _MockRelationship


def _node(labels: list[str], props: dict) -> _MockNode:
    return _MockNode(labels, props)


# After wiring _resolve into read methods, we need to bypass resolve_full_name
# in tests that don't care about resolution.
@pytest.fixture(autouse=True)
def bypass_resolve(monkeypatch):
    """Make resolve_full_name return the name unchanged for all service tests."""
    monkeypatch.setattr("synapps.service.resolve_full_name", lambda conn, name: name)


def _service() -> SynappsService:
    conn = MagicMock()
    return SynappsService(conn=conn)


def test_set_summary_delegates_to_nodes() -> None:
    svc = _service()
    with patch("synapps.service.set_summary") as mock_set:
        svc.set_summary("MyNs.MyClass", "Auth handler")
        mock_set.assert_called_once_with(svc._conn, "MyNs.MyClass", "Auth handler")



def test_watch_project_registers_watcher() -> None:
    svc = _service()
    mock_watcher_cls = MagicMock()
    mock_watcher = MagicMock()
    mock_watcher_cls.return_value = mock_watcher
    mock_lsp = MagicMock()
    mock_lsp.get_workspace_files.return_value = []

    with patch("synapps.service.indexing.FileWatcher", mock_watcher_cls):
        svc.watch_project("/proj", lsp_adapter=mock_lsp)
        mock_watcher.start.assert_called_once()
        assert "/proj" in svc._indexing._watchers


def test_watch_project_creates_single_watcher_for_multi_language() -> None:
    """When a repo has both .cs and .py files, watch_project creates one watcher with merged extensions."""
    conn = MagicMock()

    py_plugin = MagicMock()
    py_plugin.name = "python"
    py_plugin.file_extensions = frozenset({".py"})
    py_plugin.create_lsp_adapter.return_value = MagicMock(get_workspace_files=MagicMock(return_value=[]))

    cs_plugin = MagicMock()
    cs_plugin.name = "csharp"
    cs_plugin.file_extensions = frozenset({".cs"})
    cs_plugin.create_lsp_adapter.return_value = MagicMock(get_workspace_files=MagicMock(return_value=[]))

    registry = MagicMock()
    registry.detect.return_value = [cs_plugin, py_plugin]

    svc = SynappsService(conn=conn, registry=registry)

    mock_watcher = MagicMock()

    def make_watcher(**kwargs):
        mock_watcher.watched_extensions = kwargs.get("watched_extensions")
        return mock_watcher

    with patch("synapps.service.indexing.FileWatcher", side_effect=make_watcher), \
         patch("synapps.service.indexing.Indexer"):
        svc.watch_project("/proj")

    assert svc._indexing._watchers["/proj"] is mock_watcher
    mock_watcher.start.assert_called_once()
    assert mock_watcher.watched_extensions == frozenset({".cs", ".py"})


def test_watch_project_multi_language_creates_exactly_one_file_watcher() -> None:
    """Regression: multiple plugins must not create multiple OS-level watches on the same path."""
    conn = MagicMock()

    py_plugin = MagicMock()
    py_plugin.name = "python"
    py_plugin.file_extensions = frozenset({".py"})
    py_plugin.create_lsp_adapter.return_value = MagicMock(get_workspace_files=MagicMock(return_value=[]))

    cs_plugin = MagicMock()
    cs_plugin.name = "csharp"
    cs_plugin.file_extensions = frozenset({".cs"})
    cs_plugin.create_lsp_adapter.return_value = MagicMock(get_workspace_files=MagicMock(return_value=[]))

    ts_plugin = MagicMock()
    ts_plugin.name = "typescript"
    ts_plugin.file_extensions = frozenset({".ts", ".tsx", ".js", ".jsx"})
    ts_plugin.create_lsp_adapter.return_value = MagicMock(get_workspace_files=MagicMock(return_value=[]))

    registry = MagicMock()
    registry.detect.return_value = [cs_plugin, py_plugin, ts_plugin]

    svc = SynappsService(conn=conn, registry=registry)
    watcher_cls = MagicMock()
    watcher_cls.return_value = MagicMock()

    with patch("synapps.service.indexing.FileWatcher", watcher_cls), \
         patch("synapps.service.indexing.Indexer"):
        svc.watch_project("/proj")

    watcher_cls.assert_called_once()
    assert watcher_cls.call_args[1]["watched_extensions"] == frozenset(
        {".cs", ".py", ".ts", ".tsx", ".js", ".jsx"}
    )


def test_watch_project_invokes_on_file_event_for_change_and_delete() -> None:
    """on_file_event callback receives (event_type, file_path) when files change or are deleted."""
    svc = _service()
    mock_lsp = MagicMock()
    mock_lsp.get_workspace_files.return_value = []
    captured_callbacks: dict = {}

    def capture_watcher(**kwargs):
        captured_callbacks["on_change"] = kwargs["on_change"]
        captured_callbacks["on_delete"] = kwargs["on_delete"]
        return MagicMock()

    events: list[tuple[str, str]] = []

    with patch("synapps.service.indexing.FileWatcher", side_effect=capture_watcher):
        svc.watch_project("/proj", lsp_adapter=mock_lsp, on_file_event=lambda ev, fp: events.append((ev, fp)))

    captured_callbacks["on_change"]("/proj/Foo.cs")
    captured_callbacks["on_delete"]("/proj/Bar.cs")

    assert ("changed", "/proj/Foo.cs") in events
    assert ("deleted", "/proj/Bar.cs") in events


def test_unwatch_project_stops_watcher() -> None:
    svc = _service()
    mock_watcher = MagicMock()
    svc._indexing._watchers["/proj"] = mock_watcher

    with patch("synapps.service.indexing.is_git_repo", return_value=False):
        svc.unwatch_project("/proj")

    mock_watcher.stop.assert_called_once()
    assert "/proj" not in svc._indexing._watchers


@patch("synapps.service.indexing.set_last_indexed_commit")
@patch("synapps.service.indexing.rev_parse_head", return_value="abc123")
@patch("synapps.service.indexing.is_git_repo", return_value=True)
def test_unwatch_project_updates_stored_sha(mock_git, mock_rev, mock_set) -> None:
    """unwatch_project stores current HEAD so auto-sync doesn't re-sync watched changes."""
    svc = _service()
    mock_watcher = MagicMock()
    svc._indexing._watchers["/proj"] = mock_watcher

    svc.unwatch_project("/proj")

    mock_set.assert_called_once_with(svc._conn, "/proj", "abc123")


def test_watch_on_change_callback_catches_exceptions() -> None:
    """Exceptions in the on_change callback are logged, not propagated."""
    svc = _service()
    mock_lsp = MagicMock()
    mock_lsp.get_workspace_files.return_value = []
    captured_callbacks: dict = {}

    def capture_watcher(**kwargs):
        captured_callbacks["on_change"] = kwargs["on_change"]
        return MagicMock()

    with patch("synapps.service.indexing.FileWatcher", side_effect=capture_watcher), \
         patch("synapps.service.indexing.Indexer") as mock_indexer_cls:
        mock_indexer = mock_indexer_cls.return_value
        mock_indexer.reindex_file.side_effect = RuntimeError("LSP crashed")
        svc.watch_project("/proj", lsp_adapter=mock_lsp)

    # Should not raise even though reindex_file throws
    captured_callbacks["on_change"]("/proj/Foo.cs")


def test_get_symbol_source_reads_file_and_returns_lines(tmp_path):
    """Service reads the file from disk using 1-based line range from the graph."""
    source_file = tmp_path / "Foo.cs"
    source_file.write_text("line0\nline1\nline2\nline3\nline4\nline5\n")

    conn = MagicMock()
    svc = SynappsService(conn)

    # Graph stores 1-based lines: line=2, end_line=4 means file lines 2-4 (array[1:4])
    with patch("synapps.service.context.get_symbol_source_info") as mock_query:
        mock_query.return_value = {"file_path": str(source_file), "line": 2, "end_line": 4}
        result = svc.get_symbol_source("Ns.C.M")

    assert "line1" in result
    assert "line2" in result
    assert "line3" in result
    assert "line0" not in result
    assert "line4" not in result
    # Display header should show the 1-based line directly
    assert ":2\n" in result


def test_get_symbol_source_returns_none_when_symbol_not_found():
    conn = MagicMock()
    svc = SynappsService(conn)

    with patch("synapps.service.context.get_symbol_source_info") as mock_query:
        mock_query.return_value = None
        result = svc.get_symbol_source("Ns.Missing")

    assert result is None


def test_get_symbol_source_returns_error_when_end_line_missing(tmp_path):
    """When end_line is 0, the symbol was indexed before line ranges were added."""
    conn = MagicMock()
    svc = SynappsService(conn)

    with patch("synapps.service.context.get_symbol_source_info") as mock_query:
        mock_query.return_value = {"file_path": str(tmp_path / "F.cs"), "line": 5, "end_line": 0}
        result = svc.get_symbol_source("Ns.C.M")

    assert result is not None
    assert "re-index" in result.lower()


def test_get_context_for_method_includes_all_sections(tmp_path):
    source_file = tmp_path / "Foo.cs"
    source_file.write_text(
        "namespace Ns {\n"
        "    class MyClass : IFoo {\n"
        "        public UserDto GetUser(int id) {\n"
        "            return _repo.Find(id);\n"
        "        }\n"
        "    }\n"
        "}\n"
    )

    conn = MagicMock()
    svc = SynappsService(conn)

    with patch.multiple(
        "synapps.service.context",
        get_symbol=MagicMock(return_value={"full_name": "Ns.MyClass.GetUser", "name": "GetUser", "line": 2, "end_line": 4}),
        get_symbol_source_info=MagicMock(return_value={"file_path": str(source_file), "line": 2, "end_line": 4}),
        get_containing_type=MagicMock(return_value={"full_name": "Ns.MyClass", "name": "MyClass", "kind": "class", "line": 1, "end_line": 5}),
        get_members_overview=MagicMock(return_value=[
            {"full_name": "Ns.MyClass.GetUser", "name": "GetUser", "signature": "UserDto GetUser(int)"},
        ]),
        get_implemented_interfaces=MagicMock(return_value=[
            {"full_name": "Ns.IFoo", "name": "IFoo"},
        ]),
        find_callees=MagicMock(return_value=[
            {"full_name": "Ns.Repo.Find", "name": "Find", "signature": "User Find(int)"},
        ]),
        query_find_dependencies=MagicMock(return_value=[
            {"type": {"full_name": "Ns.UserDto", "name": "UserDto"}, "depth": 1},
        ]),
    ):
        result = svc.get_context_for("Ns.MyClass.GetUser")

    assert "## Target:" in result
    assert "## Containing Type:" in result
    assert "## Implemented Interfaces" in result
    assert "## Called Methods" in result
    assert "## Parameter & Return Types" in result


def test_get_context_for_returns_none_when_symbol_not_found():
    conn = MagicMock()
    svc = SynappsService(conn)

    with patch("synapps.service.context.get_symbol", return_value=None):
        result = svc.get_context_for("Ns.Missing")

    assert result is None


def test_p_extracts_properties_and_labels_from_neo4j_node():
    node = _node(["Method"], {"full_name": "A.B", "signature": "B() : void"})
    result = _p(node)
    assert result == {"full_name": "A.B", "signature": "B() : void", "_labels": ["Method"]}


def test_p_passes_through_plain_dict():
    d = {"full_name": "A.B"}
    assert _p(d) is d


def test_p_extracts_properties_and_type_from_neo4j_relationship():
    rel = _MockRelationship("REFERENCES", {"since": "1.0"})
    result = _p(rel)
    assert result == {"since": "1.0", "_type": "REFERENCES"}


def test_p_node_still_works_after_relationship_fix():
    node = _node(["Method"], {"full_name": "A.B"})
    result = _p(node)
    assert result == {"full_name": "A.B", "_labels": ["Method"]}


def test_p_plain_dict_still_works_after_relationship_fix():
    d = {"key": "value"}
    assert _p(d) is d


def test_execute_query_handles_relationship_cells():
    conn = MagicMock()
    svc = SynappsService(conn)
    rel = _MockRelationship("REFERENCES", {"since": "1.0"})
    with patch("synapps.service.execute_readonly_query", return_value=[[rel]]):
        result = svc.execute_query("MATCH ()-[r]->() RETURN r")
    assert len(result) == 1
    row = result[0]["row"]
    assert len(row) == 1
    assert row[0] == {"since": "1.0", "_type": "REFERENCES"}


def test_find_callers_returns_plain_dicts():
    svc = _service()
    node = _node(["Method"], {"full_name": "A.Caller", "file_path": "/src/A.cs", "line": 5, "signature": "Caller() : void"})
    with patch("synapps.service.find_callers", return_value=[node]):
        result = svc.find_callers("A.B")
    assert result == [{"full_name": "A.Caller", "file_path": "/src/A.cs", "line": 5}]


def test_find_implementations_returns_plain_dicts():
    svc = _service()
    node = _node(["Class"], {"full_name": "A.Impl", "file_path": "/src/Impl.cs", "line": 1})
    with patch("synapps.service.find_implementations", return_value=[node]):
        result = svc.find_implementations("A.IService")
    assert result == [{"full_name": "A.Impl", "file_path": "/src/Impl.cs", "line": 1}]


def test_get_symbol_returns_plain_dict_with_labels():
    svc = _service()
    node = _node(["Class"], {"full_name": "A.Cls"})
    with patch("synapps.service.get_symbol", return_value=node):
        result = svc.get_symbol("A.Cls")
    assert result == {"full_name": "A.Cls", "_labels": ["Class"]}


def test_get_symbol_returns_none_when_not_found():
    svc = _service()
    with patch("synapps.service.get_symbol", return_value=None):
        result = svc.get_symbol("Missing")
    assert result is None


def test_find_type_references_unwraps_nested_nodes():
    svc = _service()
    node = _node(["Method"], {"full_name": "A.Caller", "file_path": "/src/A.cs"})
    with patch("synapps.service.query_find_type_references", return_value=[{"symbol": node, "kind": "parameter"}]):
        result = svc.find_type_references("A.IService")
    assert result == [{"symbol": {"full_name": "A.Caller", "file_path": "/src/A.cs"}, "kind": "parameter"}]


def test_find_type_references_rejects_invalid_kind() -> None:
    conn = MagicMock()
    svc = SynappsService(conn)
    with patch("synapps.service.resolve_full_name", return_value="Ns.Dto"):
        with pytest.raises(ValueError, match="Unknown reference kind"):
            svc.find_type_references("Dto", kind="invalid")


def test_find_type_references_passes_valid_kind() -> None:
    conn = MagicMock()
    svc = SynappsService(conn)
    with patch("synapps.service.resolve_full_name", return_value="Ns.Dto"), \
         patch("synapps.service.query_find_type_references", return_value=[]) as mock_query:
        svc.find_type_references("Dto", kind="parameter")
    mock_query.assert_called_once_with(conn, "Ns.Dto", kind="parameter")


def test_find_dependencies_unwraps_nested_nodes():
    svc = _service()
    node = _node(["Class"], {"full_name": "A.Dep", "file_path": "/src/Dep.cs"})
    with patch("synapps.service.query_find_dependencies", return_value=[{"type": node, "depth": 1}]):
        result = svc.find_dependencies("A.Method")
    assert result == [{"type": {"full_name": "A.Dep", "file_path": "/src/Dep.cs"}, "depth": 1}]


def test_get_context_for_includes_summaries_when_available(tmp_path):
    source_file = tmp_path / "Foo.cs"
    source_file.write_text("class Foo { void Bar() {} }\n")

    conn = MagicMock()
    svc = SynappsService(conn)

    with patch.multiple(
        "synapps.service.context",
        get_symbol=MagicMock(return_value={"full_name": "Ns.Foo.Bar", "name": "Bar"}),
        get_symbol_source_info=MagicMock(return_value={"file_path": str(source_file), "line": 1, "end_line": 0}),
        get_containing_type=MagicMock(return_value={"full_name": "Ns.Foo", "name": "Foo", "kind": "class"}),
        get_members_overview=MagicMock(return_value=[]),
        get_implemented_interfaces=MagicMock(return_value=[]),
        find_callees=MagicMock(return_value=[]),
        query_find_dependencies=MagicMock(return_value=[]),
        get_summary=MagicMock(return_value="Handles business logic"),
    ):
        result = svc.get_context_for("Ns.Foo.Bar")

    assert "## Summaries" in result
    assert "Handles business logic" in result


def test_get_context_for_no_summaries_section_when_none_exist(tmp_path):
    source_file = tmp_path / "Foo.cs"
    source_file.write_text("class Foo { void Bar() {} }\n")

    conn = MagicMock()
    svc = SynappsService(conn)

    with patch.multiple(
        "synapps.service.context",
        get_symbol=MagicMock(return_value={"full_name": "Ns.Foo.Bar", "name": "Bar"}),
        get_symbol_source_info=MagicMock(return_value={"file_path": str(source_file), "line": 1, "end_line": 0}),
        get_containing_type=MagicMock(return_value=None),
        get_summary=MagicMock(return_value=None),
    ):
        result = svc.get_context_for("Ns.Foo.Bar")

    assert "## Summaries" not in result


def test_get_hierarchy_unwraps_nodes():
    svc = _service()
    parent = _node(["Class"], {"full_name": "A.Base", "file_path": "/src/Base.cs"})
    child = _node(["Class"], {"full_name": "A.Child", "file_path": "/src/Child.cs"})
    iface = _node(["Interface"], {"full_name": "A.IFoo", "file_path": "/src/IFoo.cs"})
    with patch("synapps.service.get_hierarchy", return_value={"parents": [parent], "children": [child], "implements": [iface]}):
        result = svc.get_hierarchy("A.Middle")
    assert result["parents"] == [{"full_name": "A.Base", "file_path": "/src/Base.cs"}]
    assert result["children"] == [{"full_name": "A.Child", "file_path": "/src/Child.cs"}]
    assert result["implements"] == [{"full_name": "A.IFoo", "file_path": "/src/IFoo.cs"}]


def test_get_context_for_scope_structure_returns_signatures_only(tmp_path):
    source_file = tmp_path / "Foo.cs"
    source_file.write_text(
        "namespace Ns {\n"
        "    class MyClass : IFoo {\n"
        "        public MyClass(IRepo repo) { _repo = repo; }\n"
        "        public UserDto GetUser(int id) { return _repo.Find(id); }\n"
        "    }\n"
        "}\n"
    )

    svc = _service()
    symbol = _node(["Class"], {"full_name": "Ns.MyClass", "name": "MyClass", "kind": "class"})
    ctor_node = _node(["Method"], {"full_name": "Ns.MyClass.MyClass", "name": "MyClass",
                                    "line": 3, "end_line": 3})

    with patch.multiple(
        "synapps.service.context",
        get_symbol=MagicMock(return_value=symbol),
        get_constructor=MagicMock(return_value=ctor_node),
        get_symbol_source_info=MagicMock(return_value={
            "file_path": str(source_file), "line": 3, "end_line": 3,
        }),
        get_members_overview=MagicMock(return_value=[
            {"full_name": "Ns.MyClass.MyClass", "name": "MyClass", "signature": "MyClass(IRepo)"},
            {"full_name": "Ns.MyClass.GetUser", "name": "GetUser", "signature": "UserDto GetUser(int)"},
        ]),
        get_implemented_interfaces=MagicMock(return_value=[
            _node(["Interface"], {"full_name": "Ns.IFoo", "name": "IFoo"}),
        ]),
        get_summary=MagicMock(return_value="Main service class"),
    ):
        result = svc.get_context_for("Ns.MyClass", scope="structure")

    assert result is not None
    assert "## Constructor" in result
    assert "public MyClass(IRepo repo)" in result
    assert "## Members" in result
    assert "GetUser: UserDto GetUser(int)" in result
    assert "## Implemented Interfaces" in result
    assert "## Summaries" in result
    # Must NOT contain full source or callees
    assert "## Target:" not in result
    assert "## Called Methods" not in result
    assert "## Parameter & Return Types" not in result


def test_get_context_for_scope_structure_on_interface():
    svc = _service()
    symbol = _node(["Interface"], {"full_name": "Ns.IFoo", "name": "IFoo", "kind": "interface"})

    with patch.multiple(
        "synapps.service.context",
        get_symbol=MagicMock(return_value=symbol),
        get_constructor=MagicMock(return_value=None),
        get_members_overview=MagicMock(return_value=[
            {"full_name": "Ns.IFoo.DoWork", "name": "DoWork", "signature": "void DoWork()"},
        ]),
        get_implemented_interfaces=MagicMock(return_value=[]),
        get_summary=MagicMock(return_value=None),
    ):
        result = svc.get_context_for("Ns.IFoo", scope="structure")

    assert result is not None
    assert "## Members" in result
    assert "DoWork: void DoWork()" in result
    # No constructor section for an interface with no constructor
    assert "## Constructor" not in result


def test_get_context_for_scope_structure_empty_type_returns_message():
    svc = _service()
    symbol = _node(["Class"], {"full_name": "Ns.Empty", "name": "Empty", "kind": "class"})

    with patch.multiple(
        "synapps.service.context",
        get_symbol=MagicMock(return_value=symbol),
        get_constructor=MagicMock(return_value=None),
        get_members_overview=MagicMock(return_value=[]),
        get_implemented_interfaces=MagicMock(return_value=[]),
        get_summary=MagicMock(return_value=None),
    ):
        result = svc.get_context_for("Ns.Empty", scope="structure")

    assert result is not None
    assert "No structure information available" in result
    assert "Ns.Empty" in result


def test_get_constructor_returns_constructor_node():
    from synapps.graph.lookups import get_constructor
    conn = MagicMock()
    ctor_node = _node(["Method"], {"full_name": "Ns.Foo.Foo", "name": "Foo"})
    conn.query.return_value = [[ctor_node]]
    result = get_constructor(conn, "Ns.Foo")
    assert result is not None
    assert result["name"] == "Foo"
    conn.query.assert_called_once()


def test_get_constructor_returns_none_when_no_constructor():
    from synapps.graph.lookups import get_constructor
    conn = MagicMock()
    conn.query.return_value = []
    result = get_constructor(conn, "Ns.Foo")
    assert result is None


def test_index_method_implements_calls_indexer() -> None:
    """SynappsService.index_method_implements must delegate to MethodImplementsIndexer."""
    svc = _service()
    with patch("synapps.service.indexing.MethodImplementsIndexer") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        svc.index_method_implements()

    mock_cls.assert_called_once_with(svc._conn)
    mock_instance.index.assert_called_once()


def test_get_context_for_scope_structure_on_method_returns_error():
    svc = _service()
    symbol = _node(["Method"], {"full_name": "Ns.Foo.Bar", "name": "Bar", "kind": "method"})
    with patch("synapps.service.context.get_symbol", return_value=symbol):
        result = svc.get_context_for("Ns.Foo.Bar", scope="structure")
    assert result is not None
    assert "scope='structure' requires a type" in result
    assert "method" in result


def test_get_context_for_scope_method_on_class_returns_error():
    svc = _service()
    symbol = _node(["Class"], {"full_name": "Ns.Foo", "name": "Foo", "kind": "class"})
    with patch("synapps.service.context.get_symbol", return_value=symbol):
        result = svc.get_context_for("Ns.Foo", scope="method")
    assert result is not None
    assert "scope='method' requires a method or property" in result
    assert "class" in result


def test_get_context_for_unknown_scope_returns_error():
    svc = _service()
    symbol = _node(["Class"], {"full_name": "Ns.Foo", "name": "Foo", "kind": "class"})
    with patch("synapps.service.context.get_symbol", return_value=symbol):
        result = svc.get_context_for("Ns.Foo", scope="bogus")
    assert result is not None
    assert "Unknown scope" in result
    assert "'bogus'" in result


def test_get_context_for_scope_method_returns_focused_context(tmp_path):
    source_file = tmp_path / "Foo.cs"
    source_file.write_text(
        "namespace Ns {\n"
        "    class MyClass : IFoo {\n"
        "        public UserDto GetUser(int id) {\n"
        "            return _repo.Find(id);\n"
        "        }\n"
        "    }\n"
        "}\n"
    )

    svc = _service()
    symbol = _node(["Method"], {"full_name": "Ns.MyClass.GetUser", "name": "GetUser", "kind": "method"})

    with patch.multiple(
        "synapps.service.context",
        get_symbol=MagicMock(return_value=symbol),
        get_symbol_source_info=MagicMock(return_value={
            "file_path": str(source_file), "line": 2, "end_line": 4,
        }),
        find_interface_contract=MagicMock(return_value={
            "method": "Ns.MyClass.GetUser",
            "interface": "Ns.IFoo",
            "contract_method": "Ns.IFoo.GetUser",
            "sibling_implementations": [],
        }),
        find_callees=MagicMock(return_value=[
            {"full_name": "Ns.Repo.Find", "name": "Find", "signature": "User Find(int)"},
        ]),
        query_find_dependencies=MagicMock(return_value=[
            {"type": _node(["Class"], {"full_name": "Ns.UserDto", "name": "UserDto"}), "depth": 1},
        ]),
        get_containing_type=MagicMock(return_value=_node(
            ["Class"], {"full_name": "Ns.MyClass", "name": "MyClass"}
        )),
        get_summary=MagicMock(return_value="Fetches user by ID"),
        get_members_overview=MagicMock(return_value=[
            {"full_name": "Ns.UserDto.Id", "name": "Id", "signature": "int"},
        ]),
    ):
        result = svc.get_context_for("Ns.MyClass.GetUser", scope="method")

    assert result is not None
    assert "## Target:" in result
    assert "GetUser" in result
    assert "## Interface Contract" in result
    assert "Ns.IFoo.GetUser" in result
    assert "## Called Methods" in result
    assert "`Ns.Repo.Find`" in result
    assert "## Parameter & Return Types" in result
    assert "Ns.UserDto" in result
    assert "## Summaries" in result
    # Must NOT contain full containing type member list
    assert "## Containing Type:" not in result
    assert "## Members:" not in result


def test_get_context_for_scope_method_empty_callees_and_no_interface(tmp_path):
    source_file = tmp_path / "Foo.cs"
    source_file.write_text("class Foo { void Simple() {} }\n")

    svc = _service()
    symbol = _node(["Method"], {"full_name": "Ns.Foo.Simple", "name": "Simple", "kind": "method"})

    with patch.multiple(
        "synapps.service.context",
        get_symbol=MagicMock(return_value=symbol),
        get_symbol_source_info=MagicMock(return_value={
            "file_path": str(source_file), "line": 1, "end_line": 0,
        }),
        find_interface_contract=MagicMock(return_value={
            "method": "Ns.Foo.Simple",
            "interface": None,
            "contract_method": None,
            "sibling_implementations": [],
        }),
        find_callees=MagicMock(return_value=[]),
        query_find_dependencies=MagicMock(return_value=[]),
        get_containing_type=MagicMock(return_value=None),
        get_summary=MagicMock(return_value=None),
    ):
        result = svc.get_context_for("Ns.Foo.Simple", scope="method")

    assert result is not None
    assert "## Target:" in result
    # Sections with no data should be omitted
    assert "## Interface Contract" not in result
    assert "## Called Methods" not in result
    assert "## Parameter & Return Types" not in result
    assert "## Summaries" not in result


def test_get_context_for_scope_method_interface_contract_only_matching(tmp_path):
    source_file = tmp_path / "Foo.cs"
    source_file.write_text("class Foo : IBar { void DoWork() {} }\n")

    svc = _service()
    symbol = _node(["Method"], {"full_name": "Ns.Foo.DoWork", "name": "DoWork", "kind": "method"})

    with patch.multiple(
        "synapps.service.context",
        get_symbol=MagicMock(return_value=symbol),
        get_symbol_source_info=MagicMock(return_value={
            "file_path": str(source_file), "line": 1, "end_line": 0,
        }),
        find_interface_contract=MagicMock(return_value={
            "method": "Ns.Foo.DoWork",
            "interface": "Ns.IBar",
            "contract_method": "Ns.IBar.DoWork",
            "sibling_implementations": [{"class_name": "Baz", "file_path": "Baz.cs"}],
        }),
        find_callees=MagicMock(return_value=[]),
        query_find_dependencies=MagicMock(return_value=[]),
        get_containing_type=MagicMock(return_value=None),
        get_summary=MagicMock(return_value=None),
    ):
        result = svc.get_context_for("Ns.Foo.DoWork", scope="method")

    assert "## Interface Contract" in result
    assert "Ns.IBar" in result
    assert "Ns.IBar.DoWork" in result
    assert "Baz" in result


def test_callers_section_formats_callers_with_sites():
    svc = _service()
    caller = _node(["Method"], {"full_name": "A.Ctrl.Create", "file_path": "/src/Ctrl.cs"})
    with patch("synapps.service.context.find_callers_with_sites", return_value=[
        {"caller": caller, "call_sites": [[32, 5], [58, 8]]},
    ]):
        result = svc._context._callers_section("Ns.Svc.DoWork")
    assert "## Direct Callers" in result
    assert "`A.Ctrl.Create`" in result
    assert "lines 32, 58" in result


def test_callers_section_single_line_uses_singular():
    svc = _service()
    caller = _node(["Method"], {"full_name": "A.Ctrl.Create", "file_path": "/src/Ctrl.cs"})
    with patch("synapps.service.context.find_callers_with_sites", return_value=[
        {"caller": caller, "call_sites": [[32, 5]]},
    ]):
        result = svc._context._callers_section("Ns.Svc.DoWork")
    assert "line 32" in result
    assert "lines" not in result


def test_callers_section_no_sites_omits_parenthetical():
    svc = _service()
    caller = _node(["Method"], {"full_name": "A.Ctrl.Create", "file_path": "/src/Ctrl.cs"})
    with patch("synapps.service.context.find_callers_with_sites", return_value=[
        {"caller": caller, "call_sites": []},
    ]):
        result = svc._context._callers_section("Ns.Svc.DoWork")
    assert "`A.Ctrl.Create`" in result
    assert "(" not in result


def test_callers_section_returns_none_when_no_callers():
    svc = _service()
    with patch("synapps.service.context.find_callers_with_sites", return_value=[]):
        result = svc._context._callers_section("Ns.Svc.DoWork")
    assert result is None


def test_callers_section_limits_to_15_callers():
    svc = _service()
    callers = [
        {"caller": _node(["Method"], {"full_name": f"A.C{i}", "file_path": f"/src/{i}.cs"}), "call_sites": []}
        for i in range(20)
    ]
    with patch("synapps.service.context.find_callers_with_sites", return_value=callers):
        result = svc._context._callers_section("Ns.Svc.DoWork")
    assert "... and 5 more callers" in result


def test_test_coverage_section_formats_test_methods():
    svc = _service()
    with patch("synapps.service.context.find_test_coverage", return_value=[
        {"full_name": "Ns.Tests.FooTests.TestBar", "file_path": "/tests/FooTests.cs"},
    ]):
        result = svc._context._test_coverage_section("Ns.Foo.Bar")
    assert "## Test Coverage" in result
    assert "Ns.Tests.FooTests.TestBar" in result


def test_test_coverage_section_returns_none_when_empty():
    svc = _service()
    with patch("synapps.service.context.find_test_coverage", return_value=[]):
        result = svc._context._test_coverage_section("Ns.Foo.Bar")
    assert result is None


def test_find_callers_returns_slim_dicts() -> None:
    """find_callers should return only full_name, file_path, line — not all node properties."""
    svc = _service()
    caller = _node(["Method"], {
        "full_name": "Ns.Ctrl.Action", "file_path": "/src/Ctrl.cs",
        "line": 10, "end_line": 20, "language": "csharp", "signature": "void Action()",
    })
    with patch("synapps.service.find_callers", return_value=[caller]):
        result = svc.find_callers("Ns.Svc.Do")
    assert result == [{"full_name": "Ns.Ctrl.Action", "file_path": "/src/Ctrl.cs", "line": 10}]
    assert "end_line" not in result[0]
    assert "language" not in result[0]


def test_search_symbols_returns_slim_dicts() -> None:
    """search_symbols should return only full_name, name, kind, file_path, line."""
    svc = _service()
    node = _node(["Class"], {
        "full_name": "Ns.MyClass", "name": "MyClass", "kind": "class",
        "file_path": "/src/My.cs", "line": 5, "end_line": 100, "language": "csharp",
    })
    with patch("synapps.service.search_symbols", return_value=[node]):
        result = svc.search_symbols("MyClass")
    assert result == [{"full_name": "Ns.MyClass", "name": "MyClass", "kind": "class", "file_path": "/src/My.cs", "line": 5, "language": "csharp"}]
    assert "end_line" not in result[0]


def test_get_hierarchy_returns_slim_dicts() -> None:
    """get_hierarchy should return only full_name, file_path per node."""
    svc = _service()
    parent = _node(["Class"], {"full_name": "Ns.Base", "file_path": "/src/Base.cs", "line": 1, "end_line": 50})
    child = _node(["Class"], {"full_name": "Ns.Derived", "file_path": "/src/Derived.cs", "line": 1, "end_line": 30})
    iface = _node(["Interface"], {"full_name": "Ns.IFoo", "file_path": "/src/IFoo.cs", "line": 1, "end_line": 10})
    with patch("synapps.service.get_hierarchy", return_value={"parents": [parent], "children": [child], "implements": [iface]}):
        result = svc.get_hierarchy("Ns.Derived")
    assert result["parents"] == [{"full_name": "Ns.Base", "file_path": "/src/Base.cs"}]
    assert "end_line" not in result["parents"][0]


def test_relevant_deps_section_shows_member_signatures():
    svc = _service()
    dep = _node(["Interface"], {"full_name": "Ns.IRepo"})
    with patch("synapps.service.context.find_relevant_deps", return_value=[dep]), \
         patch("synapps.service.context.get_called_members", return_value=[
             {"full_name": "Ns.IRepo.Save", "name": "Save", "signature": "Task Save(Entity)"},
         ]):
        result = svc._context._relevant_deps_section("Ns.MyClass", "Ns.MyClass.DoWork")
    assert "## Constructor Dependencies (used by this method)" in result
    assert "Ns.IRepo" in result
    assert "Save" in result


def test_relevant_deps_section_returns_none_when_empty():
    svc = _service()
    with patch("synapps.service.context.find_relevant_deps", return_value=[]):
        result = svc._context._relevant_deps_section("Ns.MyClass", "Ns.MyClass.DoWork")
    assert result is None


def test_relevant_deps_section_shows_only_called_members() -> None:
    conn = MagicMock()
    svc = SynappsService(conn)
    dep_node = {"full_name": "Ns.DbContext", "name": "DbContext"}
    with patch("synapps.service.context.find_relevant_deps", return_value=[dep_node]), \
         patch("synapps.service.context.get_called_members") as mock_called:
        mock_called.return_value = [
            {"full_name": "Ns.DbContext.MeetingNotes", "name": "MeetingNotes", "type_name": "DbSet<MeetingNote>"},
        ]
        result = svc._context._relevant_deps_section("Ns.Svc", "Ns.Svc.Create")
    assert result is not None
    assert "MeetingNotes" in result


def test_relevant_deps_section_fallback_to_all_members() -> None:
    conn = MagicMock()
    svc = SynappsService(conn)
    dep_node = {"full_name": "Ns.DbContext", "name": "DbContext"}
    with patch("synapps.service.context.find_relevant_deps", return_value=[dep_node]), \
         patch("synapps.service.context.get_called_members", return_value=[]), \
         patch("synapps.service.context.get_members_overview") as mock_members:
        mock_members.return_value = [
            {"full_name": "Ns.DbContext.All", "name": "All", "type_name": "DbSet<All>"},
        ]
        result = svc._context._relevant_deps_section("Ns.Svc", "Ns.Svc.Create")
    assert result is not None
    assert "all members shown" in result.lower()


def test_get_context_for_default_scope_unchanged(tmp_path):
    """Verify that scope=None produces identical output to the original get_context_for."""
    source_file = tmp_path / "Foo.cs"
    source_file.write_text(
        "namespace Ns {\n"
        "    class MyClass : IFoo {\n"
        "        public UserDto GetUser(int id) {\n"
        "            return _repo.Find(id);\n"
        "        }\n"
        "    }\n"
        "}\n"
    )

    conn = MagicMock()
    svc = SynappsService(conn)

    patches = dict(
        get_symbol=MagicMock(return_value=_node(
            ["Method"], {"full_name": "Ns.MyClass.GetUser", "name": "GetUser", "line": 2, "end_line": 4}
        )),
        get_symbol_source_info=MagicMock(return_value={
            "file_path": str(source_file), "line": 2, "end_line": 4,
        }),
        get_containing_type=MagicMock(return_value=_node(
            ["Class"], {"full_name": "Ns.MyClass", "name": "MyClass", "kind": "class"}
        )),
        get_members_overview=MagicMock(return_value=[
            {"full_name": "Ns.MyClass.GetUser", "name": "GetUser", "signature": "UserDto GetUser(int)"},
        ]),
        get_implemented_interfaces=MagicMock(return_value=[]),
        find_callees=MagicMock(return_value=[]),
        query_find_dependencies=MagicMock(return_value=[]),
        get_summary=MagicMock(return_value=None),
    )

    with patch.multiple("synapps.service.context", **patches):
        result_default = svc.get_context_for("Ns.MyClass.GetUser")
    with patch.multiple("synapps.service.context", **patches):
        result_explicit = svc.get_context_for("Ns.MyClass.GetUser", scope=None)

    assert result_default == result_explicit
    assert "## Target:" in result_default
    assert "## Containing Type:" in result_default


def test_get_context_for_scope_edit_method_includes_all_sections(tmp_path):
    source_file = tmp_path / "Foo.cs"
    source_file.write_text(
        "namespace Ns {\n"
        "    class Svc : ISvc {\n"
        "        public Result DoWork(int id) {\n"
        "            return _repo.Find(id);\n"
        "        }\n"
        "    }\n"
        "}\n"
    )

    svc = _service()
    symbol = _node(["Method"], {"full_name": "Ns.Svc.DoWork", "name": "DoWork", "kind": "method"})
    caller = _node(["Method"], {"full_name": "Ns.Ctrl.Action", "file_path": "/src/Ctrl.cs"})
    dep = _node(["Interface"], {"full_name": "Ns.IRepo"})

    with patch.multiple(
        "synapps.service.context",
        get_symbol=MagicMock(return_value=symbol),
        get_symbol_source_info=MagicMock(return_value={
            "file_path": str(source_file), "line": 2, "end_line": 4,
        }),
        find_interface_contract=MagicMock(return_value={
            "method": "Ns.Svc.DoWork",
            "interface": "Ns.ISvc",
            "contract_method": "Ns.ISvc.DoWork",
            "sibling_implementations": [],
        }),
        get_served_endpoint=MagicMock(return_value=None),
        find_http_callers=MagicMock(return_value=[]),
        find_callers_with_sites=MagicMock(return_value=[
            {"caller": caller, "call_sites": [[32, 5]]},
        ]),
        get_containing_type=MagicMock(return_value=_node(
            ["Class"], {"full_name": "Ns.Svc", "name": "Svc"}
        )),
        find_relevant_deps=MagicMock(return_value=[dep]),
        get_members_overview=MagicMock(return_value=[
            {"full_name": "Ns.IRepo.Find", "name": "Find", "signature": "Result Find(int)"},
        ]),
        find_test_coverage=MagicMock(return_value=[
            {"full_name": "Ns.Tests.SvcTests.TestDoWork", "file_path": "/tests/SvcTests.cs"},
        ]),
        get_summary=MagicMock(return_value=None),
        get_implemented_interfaces=MagicMock(return_value=[]),
    ):
        result = svc.get_context_for("Ns.Svc.DoWork", scope="edit")

    assert result is not None
    assert "## Target:" in result
    assert "## Interface Contract" in result
    assert "## Direct Callers" in result
    assert "line 32" in result
    assert "## Constructor Dependencies (used by this method)" in result
    assert "Ns.IRepo" in result
    assert "## Test Coverage" in result
    assert "Ns.Tests.SvcTests.TestDoWork" in result


def test_get_context_for_scope_edit_method_shows_empty_state(tmp_path):
    """scope='edit' always shows callers/test sections with empty-state messages."""
    source_file = tmp_path / "Foo.cs"
    source_file.write_text("class Foo { void Simple() {} }\n")

    svc = _service()
    symbol = _node(["Method"], {"full_name": "Ns.Foo.Simple", "name": "Simple", "kind": "method"})

    with patch.multiple(
        "synapps.service.context",
        get_symbol=MagicMock(return_value=symbol),
        get_symbol_source_info=MagicMock(return_value={
            "file_path": str(source_file), "line": 1, "end_line": 0,
        }),
        find_interface_contract=MagicMock(return_value={
            "method": "Ns.Foo.Simple", "interface": None,
            "contract_method": None, "sibling_implementations": [],
        }),
        get_served_endpoint=MagicMock(return_value=None),
        find_http_callers=MagicMock(return_value=[]),
        find_callers_with_sites=MagicMock(return_value=[]),
        get_containing_type=MagicMock(return_value=None),
        find_test_coverage=MagicMock(return_value=[]),
        get_summary=MagicMock(return_value=None),
    ):
        result = svc.get_context_for("Ns.Foo.Simple", scope="edit")

    assert "## Target:" in result
    assert "## Interface Contract" not in result
    assert "## Direct Callers" in result
    assert "No callers found" in result
    assert "## Constructor Dependencies" not in result
    assert "## Test Coverage" in result
    assert "No tests found" in result


def test_get_context_for_scope_edit_method_includes_http_endpoint(tmp_path):
    """scope='edit' shows HTTP endpoint info when the method serves one."""
    source_file = tmp_path / "Api.cs"
    source_file.write_text("class Api { void GetItem() {} }\n")

    svc = _service()
    symbol = _node(["Method"], {"full_name": "Ns.Api.GetItem", "name": "GetItem", "kind": "method"})

    with patch.multiple(
        "synapps.service.context",
        get_symbol=MagicMock(return_value=symbol),
        get_symbol_source_info=MagicMock(return_value={
            "file_path": str(source_file), "line": 1, "end_line": 0,
        }),
        find_interface_contract=MagicMock(return_value={
            "method": "Ns.Api.GetItem", "interface": None,
            "contract_method": None, "sibling_implementations": [],
        }),
        get_served_endpoint=MagicMock(return_value={"http_method": "GET", "route": "/items/{id}"}),
        find_http_callers=MagicMock(return_value=[
            {"full_name": "Ns.Client.FetchItem", "file_path": "/src/Client.cs", "route": "/items/{id}"},
        ]),
        find_callers_with_sites=MagicMock(return_value=[]),
        get_containing_type=MagicMock(return_value=None),
        find_test_coverage=MagicMock(return_value=[]),
        get_summary=MagicMock(return_value=None),
    ):
        result = svc.get_context_for("Ns.Api.GetItem", scope="edit")

    assert "## HTTP Endpoint" in result
    assert "GET /items/{id}" in result
    assert "Client call sites" in result
    assert "Ns.Client.FetchItem" in result


def test_get_context_for_scope_edit_rejects_property():
    svc = _service()
    symbol = _node(["Property"], {"full_name": "Ns.Foo.Name", "name": "Name", "kind": "property"})
    with patch("synapps.service.context.get_symbol", return_value=symbol):
        result = svc.get_context_for("Ns.Foo.Name", scope="edit")
    assert "scope='edit' requires" in result
    assert "property" in result


def test_get_context_for_scope_edit_class_includes_all_sections(tmp_path):
    source_file = tmp_path / "Svc.cs"
    source_file.write_text(
        "namespace Ns {\n"
        "    class Svc : ISvc {\n"
        "        public void DoWork() {}\n"
        "    }\n"
        "}\n"
    )

    svc = _service()
    symbol = _node(["Class"], {"full_name": "Ns.Svc", "name": "Svc", "kind": "class"})
    method = _node(["Method"], {"full_name": "Ns.Svc.DoWork", "name": "DoWork", "signature": "void DoWork()"})
    caller = _node(["Method"], {"full_name": "Ns.Ctrl.Action", "file_path": "/src/Ctrl.cs"})
    dep = _node(["Interface"], {"full_name": "Ns.IRepo"})

    with patch.multiple(
        "synapps.service.context",
        get_symbol=MagicMock(return_value=symbol),
        get_symbol_source_info=MagicMock(return_value={
            "file_path": str(source_file), "line": 2, "end_line": 4,
        }),
        get_implemented_interfaces=MagicMock(return_value=[
            _node(["Interface"], {"full_name": "Ns.ISvc", "name": "ISvc"}),
        ]),
        get_members_overview=MagicMock(return_value=[method]),
        find_callers_with_sites=MagicMock(return_value=[
            {"caller": caller, "call_sites": [[10, 0]]},
        ]),
        find_all_deps=MagicMock(return_value=[dep]),
        find_test_coverage=MagicMock(return_value=[
            {"full_name": "Ns.Tests.SvcTests.TestDoWork", "file_path": "/tests/SvcTests.cs"},
        ]),
        get_summary=MagicMock(return_value=None),
    ):
        result = svc.get_context_for("Ns.Svc", scope="edit")

    assert "## Target:" in result
    assert "## Implemented Interfaces" in result
    assert "## Callers" in result
    assert "DoWork" in result
    assert "`Ns.Ctrl.Action`" in result
    assert "## Constructor Dependencies" in result
    assert "Ns.IRepo" in result
    assert "## Test Coverage" in result


def test_get_context_for_scope_edit_interface_skips_constructor_deps():
    svc = _service()
    symbol = _node(["Interface"], {"full_name": "Ns.ISvc", "name": "ISvc", "kind": "interface"})

    with patch.multiple(
        "synapps.service.context",
        get_symbol=MagicMock(return_value=symbol),
        get_symbol_source_info=MagicMock(return_value={
            "file_path": "/src/ISvc.cs", "line": 1, "end_line": 6,
        }),
        get_implemented_interfaces=MagicMock(return_value=[]),
        get_members_overview=MagicMock(return_value=[]),
        find_callers_with_sites=MagicMock(return_value=[]),
        find_all_deps=MagicMock(return_value=[]),
        find_test_coverage=MagicMock(return_value=[]),
        get_summary=MagicMock(return_value=None),
    ):
        result = svc.get_context_for("Ns.ISvc", scope="edit")

    assert "## Target:" in result
    assert "## Constructor Dependencies" not in result
    assert "## Implemented Interfaces" not in result


def test_get_context_for_scope_edit_class_no_methods_shows_note():
    svc = _service()
    symbol = _node(["Class"], {"full_name": "Ns.Empty", "name": "Empty", "kind": "class"})

    with patch.multiple(
        "synapps.service.context",
        get_symbol=MagicMock(return_value=symbol),
        get_symbol_source_info=MagicMock(return_value={
            "file_path": "/src/Empty.cs", "line": 1, "end_line": 2,
        }),
        get_implemented_interfaces=MagicMock(return_value=[]),
        get_members_overview=MagicMock(return_value=[]),
        find_all_deps=MagicMock(return_value=[]),
        find_test_coverage=MagicMock(return_value=[]),
        get_summary=MagicMock(return_value=None),
    ):
        result = svc.get_context_for("Ns.Empty", scope="edit")

    assert "No public methods found" in result


# --- find_usages tests ---


def test_find_usages_method_returns_text_with_callers() -> None:
    """For a Method symbol, find_usages returns compact text listing callers."""
    svc = _service()
    method_node = _node(["Method"], {"full_name": "Ns.Svc.DoWork", "name": "DoWork"})

    with patch("synapps.service.get_symbol", return_value=method_node):
        svc.find_callers = MagicMock(return_value=[
            {"full_name": "Ns.Controller.Action", "file_path": "/src/Controller.cs", "line": 10},
        ])
        result = svc.find_usages("Ns.Svc.DoWork")

    assert isinstance(result, str)
    assert "Ns.Svc.DoWork" in result
    assert "(Method)" in result
    assert "1 callers" in result
    assert "Ns.Controller.Action" in result


def test_find_usages_class_returns_text_summary() -> None:
    """For a Class, find_usages returns compact text with type refs and method callers."""
    svc = _service()
    class_node = _node(["Class"], {"full_name": "Ns.MyService", "name": "MyService", "kind": "class"})
    method_member = _node(["Method"], {"full_name": "Ns.MyService.DoWork", "name": "DoWork"})
    ref_symbol = _node(["Field"], {"full_name": "Ns.Controller._svc", "file_path": "/src/Controller.cs"})

    with patch.multiple(
        "synapps.service",
        get_symbol=MagicMock(return_value=class_node),
        get_members_overview=MagicMock(return_value=[method_member]),
        query_find_type_references=MagicMock(return_value=[{"symbol": ref_symbol, "kind": "field_type"}]),
    ):
        svc.find_callers = MagicMock(return_value=[{"full_name": "Ns.Controller.Action", "file_path": "/src/Controller.cs", "line": 10}])
        result = svc.find_usages("Ns.MyService")

    assert isinstance(result, str)
    assert "(Class)" in result
    assert "1 type references" in result
    assert "1 method callers" in result
    assert "DoWork" in result
    assert "Controller._svc" in result


def test_find_usages_class_affected_files_deduplicates() -> None:
    """affected_files count in text should be deduplicated."""
    svc = _service()
    class_node = _node(["Class"], {"full_name": "Ns.Svc", "name": "Svc", "kind": "class"})
    ref1 = _node(["Field"], {"full_name": "Ns.C1._s", "file_path": "/src/C1.cs"})
    ref2 = _node(["Field"], {"full_name": "Ns.C1._s2", "file_path": "/src/C1.cs"})  # same file

    with patch.multiple(
        "synapps.service",
        get_symbol=MagicMock(return_value=class_node),
        get_members_overview=MagicMock(return_value=[]),
        query_find_type_references=MagicMock(return_value=[
            {"symbol": ref1, "kind": "field_type"},
            {"symbol": ref2, "kind": "field_type"},
        ]),
    ):
        svc.find_callers = MagicMock(return_value=[])
        result = svc.find_usages("Ns.Svc")

    assert isinstance(result, str)
    assert "across 1 files" in result


def test_find_usages_symbol_not_found() -> None:
    svc = _service()
    with patch("synapps.service.get_symbol", return_value=None):
        result = svc.find_usages("Ns.Missing")
    assert isinstance(result, str)
    assert "not found" in result.lower()


def test_find_usages_unsupported_label() -> None:
    svc = _service()
    file_node = _node(["File"], {"full_name": "/src/Foo.cs", "name": "Foo.cs"})
    with patch("synapps.service.get_symbol", return_value=file_node):
        result = svc.find_usages("/src/Foo.cs")
    assert isinstance(result, str)
    assert "does not support" in result.lower()


def test_find_usages_class_filters_test_type_references() -> None:
    """Type references from test files should be excluded by default."""
    svc = _service()
    class_node = _node(["Class"], {"full_name": "Ns.MyService", "name": "MyService", "kind": "class"})
    prod_ref = _node(["Field"], {"full_name": "Ns.Controller._svc", "file_path": "/src/Controller.cs"})
    test_ref = _node(["Field"], {"full_name": "Ns.Tests.Setup._svc", "file_path": "/proj/MyApp.Tests/Setup.cs"})

    with patch.multiple(
        "synapps.service",
        get_symbol=MagicMock(return_value=class_node),
        get_members_overview=MagicMock(return_value=[]),
        query_find_type_references=MagicMock(return_value=[
            {"symbol": prod_ref, "kind": "field_type"},
            {"symbol": test_ref, "kind": "field_type"},
        ]),
    ):
        svc.find_callers = MagicMock(return_value=[])
        result = svc.find_usages("Ns.MyService")

    assert isinstance(result, str)
    assert "1 type references" in result
    assert "Controller._svc" in result
    assert "Ns.Tests.Setup._svc" not in result


def test_find_usages_class_includes_test_refs_when_requested() -> None:
    """exclude_test_callers=False should include test type references."""
    svc = _service()
    class_node = _node(["Class"], {"full_name": "Ns.MyService", "name": "MyService", "kind": "class"})
    prod_ref = _node(["Field"], {"full_name": "Ns.Controller._svc", "file_path": "/src/Controller.cs"})
    test_ref = _node(["Field"], {"full_name": "Ns.Tests.Setup._svc", "file_path": "/proj/MyApp.Tests/Setup.cs"})

    with patch.multiple(
        "synapps.service",
        get_symbol=MagicMock(return_value=class_node),
        get_members_overview=MagicMock(return_value=[]),
        query_find_type_references=MagicMock(return_value=[
            {"symbol": prod_ref, "kind": "field_type"},
            {"symbol": test_ref, "kind": "field_type"},
        ]),
    ):
        svc.find_callers = MagicMock(return_value=[])
        result = svc.find_usages("Ns.MyService", exclude_test_callers=False)

    assert isinstance(result, str)
    assert "2 type references" in result


def test_find_usages_property_returns_text() -> None:
    """For a Property symbol, find_usages returns text with kind=Property."""
    svc = _service()
    prop_node = _node(["Property"], {"full_name": "Ns.Svc.Name", "name": "Name"})

    with patch("synapps.service.get_symbol", return_value=prop_node):
        svc.find_callers = MagicMock(return_value=[
            {"full_name": "Ns.Controller.Action", "file_path": "/src/Controller.cs", "line": 5},
        ])
        result = svc.find_usages("Ns.Svc.Name")

    assert isinstance(result, str)
    assert "(Property)" in result
    assert "Ns.Controller.Action" in result


# --- max_lines fallback tests ---


def test_get_context_for_falls_back_to_structure_when_source_exceeds_max_lines(tmp_path) -> None:
    """When source > max_lines, show structure overview instead of full source."""
    source_file = tmp_path / "BigClass.cs"
    source_lines = "\n".join([f"// line {i}" for i in range(300)])
    source_file.write_text(source_lines)

    conn = MagicMock()
    svc = SynappsService(conn)

    class_node = _node(["Class"], {
        "full_name": "Ns.BigClass", "name": "BigClass", "kind": "class",
        "line": 1, "end_line": 300,
    })
    member = _node(["Method"], {
        "full_name": "Ns.BigClass.DoWork", "name": "DoWork",
        "signature": "void DoWork()",
    })

    with patch.multiple(
        "synapps.service.context",
        get_symbol=MagicMock(return_value=class_node),
        get_symbol_source_info=MagicMock(return_value={"file_path": str(source_file), "line": 1, "end_line": 300}),
        get_containing_type=MagicMock(return_value=None),
        get_members_overview=MagicMock(return_value=[member]),
        get_implemented_interfaces=MagicMock(return_value=[]),
        find_callees=MagicMock(return_value=[]),
        query_find_dependencies=MagicMock(return_value=[]),
        get_summary=MagicMock(return_value=None),
    ):
        result = svc.get_context_for("Ns.BigClass", max_lines=50)

    assert "Source exceeds 50 lines" in result
    assert "scope='method'" in result
    assert "DoWork" in result  # member signature visible


def test_get_context_for_shows_full_source_when_under_max_lines(tmp_path) -> None:
    """When source <= max_lines, show full source as usual."""
    source_file = tmp_path / "Small.cs"
    source_file.write_text("public class Small {}\nint x;\n")

    conn = MagicMock()
    svc = SynappsService(conn)

    class_node = _node(["Class"], {
        "full_name": "Ns.Small", "name": "Small", "kind": "class",
        "line": 1, "end_line": 2,
    })

    with patch.multiple(
        "synapps.service.context",
        get_symbol=MagicMock(return_value=class_node),
        get_symbol_source_info=MagicMock(return_value={"file_path": str(source_file), "line": 1, "end_line": 2}),
        get_containing_type=MagicMock(return_value=None),
        get_members_overview=MagicMock(return_value=[]),
        get_implemented_interfaces=MagicMock(return_value=[]),
        find_callees=MagicMock(return_value=[]),
        query_find_dependencies=MagicMock(return_value=[]),
        get_summary=MagicMock(return_value=None),
    ):
        result = svc.get_context_for("Ns.Small", max_lines=200)

    assert "Source exceeds" not in result
    assert "public class Small" in result


def test_get_context_for_max_lines_zero_always_uses_structure(tmp_path) -> None:
    """max_lines=0 means always use structure view."""
    source_file = tmp_path / "X.cs"
    source_file.write_text("class X {}\n")

    conn = MagicMock()
    svc = SynappsService(conn)

    class_node = _node(["Class"], {
        "full_name": "Ns.X", "name": "X", "kind": "class",
        "line": 1, "end_line": 0,
    })

    with patch.multiple(
        "synapps.service.context",
        get_symbol=MagicMock(return_value=class_node),
        get_symbol_source_info=MagicMock(return_value={"file_path": str(source_file), "line": 1, "end_line": 0}),
        get_containing_type=MagicMock(return_value=None),
        get_members_overview=MagicMock(return_value=[]),
        get_implemented_interfaces=MagicMock(return_value=[]),
        find_callees=MagicMock(return_value=[]),
        query_find_dependencies=MagicMock(return_value=[]),
        get_summary=MagicMock(return_value=None),
    ):
        result = svc.get_context_for("Ns.X", max_lines=0)

    assert "Source exceeds 0 lines" in result


def test_get_context_for_negative_max_lines_disables_fallback(tmp_path) -> None:
    """Negative max_lines means unlimited — no fallback."""
    source_file = tmp_path / "Huge.cs"
    source_lines = "\n".join([f"// line {i}" for i in range(500)])
    source_file.write_text(source_lines)

    conn = MagicMock()
    svc = SynappsService(conn)

    class_node = _node(["Class"], {
        "full_name": "Ns.Huge", "name": "Huge", "kind": "class",
        "line": 1, "end_line": 500,
    })

    with patch.multiple(
        "synapps.service.context",
        get_symbol=MagicMock(return_value=class_node),
        get_symbol_source_info=MagicMock(return_value={"file_path": str(source_file), "line": 1, "end_line": 500}),
        get_containing_type=MagicMock(return_value=None),
        get_members_overview=MagicMock(return_value=[]),
        get_implemented_interfaces=MagicMock(return_value=[]),
        find_callees=MagicMock(return_value=[]),
        query_find_dependencies=MagicMock(return_value=[]),
        get_summary=MagicMock(return_value=None),
    ):
        result = svc.get_context_for("Ns.Huge", max_lines=-1)

    assert "Source exceeds" not in result
    assert "// line 0" in result


# --- limit parameter tests ---


def test_find_callers_respects_limit() -> None:
    svc = _service()
    callers = [_node(["Method"], {"full_name": f"Ns.C{i}", "file_path": f"/f{i}.cs", "line": i}) for i in range(10)]
    with patch("synapps.service.find_callers", return_value=callers):
        result = svc.find_callers("Ns.Svc.Do", limit=3)
    assert result["_truncated"] is True
    assert result["_total"] == 10
    assert len(result["results"]) == 3


def test_find_callers_no_truncation_when_under_limit() -> None:
    svc = _service()
    callers = [_node(["Method"], {"full_name": "Ns.C1", "file_path": "/f.cs", "line": 1})]
    with patch("synapps.service.find_callers", return_value=callers):
        result = svc.find_callers("Ns.Svc.Do", limit=50)
    assert isinstance(result, list)
    assert len(result) == 1


def test_search_symbols_respects_limit() -> None:
    svc = _service()
    nodes = [_node(["Class"], {"full_name": f"Ns.C{i}", "name": f"C{i}", "kind": "class", "file_path": f"/f{i}.cs", "line": i}) for i in range(10)]
    with patch("synapps.service.search_symbols", return_value=nodes):
        result = svc.search_symbols("C", limit=2)
    assert result["_truncated"] is True
    assert result["_total"] == 10
    assert len(result["results"]) == 2


def test_resolve_preference_concrete_selects_class() -> None:
    conn = MagicMock()
    svc = SynappsService(conn)
    with patch("synapps.service.resolve_full_name") as mock_resolve, \
         patch("synapps.service.resolve_full_name_with_labels") as mock_labels:
        mock_resolve.return_value = ["Ns.ITaskService", "Ns.TaskService"]
        mock_labels.return_value = [("Ns.ITaskService", ["Interface"]), ("Ns.TaskService", ["Class"])]
        result = svc._resolve("TaskService", preference="concrete")
    assert result == "Ns.TaskService"


def test_resolve_preference_interface_selects_interface() -> None:
    conn = MagicMock()
    svc = SynappsService(conn)
    with patch("synapps.service.resolve_full_name") as mock_resolve, \
         patch("synapps.service.resolve_full_name_with_labels") as mock_labels:
        mock_resolve.return_value = ["Ns.ITaskService", "Ns.TaskService"]
        mock_labels.return_value = [("Ns.ITaskService", ["Interface"]), ("Ns.TaskService", ["Class"])]
        result = svc._resolve("TaskService", preference="interface")
    assert result == "Ns.ITaskService"


def test_resolve_preference_none_raises_on_ambiguity() -> None:
    conn = MagicMock()
    svc = SynappsService(conn)
    with patch("synapps.service.resolve_full_name") as mock_resolve:
        mock_resolve.return_value = ["Ns.ITaskService", "Ns.TaskService"]
        with pytest.raises(ValueError, match="Ambiguous"):
            svc._resolve("TaskService")


def test_resolve_preference_still_raises_if_multiple_match() -> None:
    conn = MagicMock()
    svc = SynappsService(conn)
    with patch("synapps.service.resolve_full_name") as mock_resolve, \
         patch("synapps.service.resolve_full_name_with_labels") as mock_labels:
        mock_resolve.return_value = ["Ns.A.TaskService", "Ns.B.TaskService"]
        mock_labels.return_value = [("Ns.A.TaskService", ["Class"]), ("Ns.B.TaskService", ["Class"])]
        with pytest.raises(ValueError, match="Ambiguous"):
            svc._resolve("TaskService", preference="concrete")


def test_resolve_preference_method_checks_parent_type() -> None:
    """When both candidates are :Method, prefer the one whose parent is :Class (concrete)."""
    conn = MagicMock()
    # Parent label query returns both methods with their parent labels
    conn.query.return_value = [
        ["Ns.MeetingService.CreateAsync", ["Class"]],
        ["Ns.IMeetingService.CreateAsync", ["Interface"]],
    ]
    svc = SynappsService(conn)
    with patch("synapps.service.resolve_full_name") as mock_resolve, \
         patch("synapps.service.resolve_full_name_with_labels") as mock_labels:
        mock_resolve.return_value = ["Ns.IMeetingService.CreateAsync", "Ns.MeetingService.CreateAsync"]
        mock_labels.return_value = [
            ("Ns.IMeetingService.CreateAsync", ["Method"]),
            ("Ns.MeetingService.CreateAsync", ["Method"]),
        ]
        result = svc._resolve("CreateAsync", preference="concrete")
    assert result == "Ns.MeetingService.CreateAsync"


def test_resolve_preference_method_interface_checks_parent() -> None:
    """When both candidates are :Method, prefer the one whose parent is :Interface."""
    conn = MagicMock()
    conn.query.return_value = [
        ["Ns.MeetingService.CreateAsync", ["Class"]],
        ["Ns.IMeetingService.CreateAsync", ["Interface"]],
    ]
    svc = SynappsService(conn)
    with patch("synapps.service.resolve_full_name") as mock_resolve, \
         patch("synapps.service.resolve_full_name_with_labels") as mock_labels:
        mock_resolve.return_value = ["Ns.IMeetingService.CreateAsync", "Ns.MeetingService.CreateAsync"]
        mock_labels.return_value = [
            ("Ns.IMeetingService.CreateAsync", ["Method"]),
            ("Ns.MeetingService.CreateAsync", ["Method"]),
        ]
        result = svc._resolve("CreateAsync", preference="interface")
    assert result == "Ns.IMeetingService.CreateAsync"


def test_resolve_preference_method_still_ambiguous_if_multiple_concrete() -> None:
    """If multiple methods have :Class parents, still raise."""
    conn = MagicMock()
    conn.query.return_value = [
        ["Ns.A.CreateAsync", ["Class"]],
        ["Ns.B.CreateAsync", ["Class"]],
    ]
    svc = SynappsService(conn)
    with patch("synapps.service.resolve_full_name") as mock_resolve, \
         patch("synapps.service.resolve_full_name_with_labels") as mock_labels:
        mock_resolve.return_value = ["Ns.A.CreateAsync", "Ns.B.CreateAsync"]
        mock_labels.return_value = [
            ("Ns.A.CreateAsync", ["Method"]),
            ("Ns.B.CreateAsync", ["Method"]),
        ]
        with pytest.raises(ValueError, match="Ambiguous"):
            svc._resolve("CreateAsync", preference="concrete")


# ---------------------------------------------------------------------------
# index_calls() Python wiring tests
# ---------------------------------------------------------------------------
# SymbolResolver and OverridesIndexer are imported at module level in service.py,
# so they can be patched via "synapps.service.indexing.SymbolResolver" etc.

def _make_python_plugin():
    """Return a mock plugin with name='python'."""
    plugin = MagicMock()
    plugin.name = "python"
    plugin.file_extensions = frozenset({".py"})
    lsp = MagicMock()
    lsp.language_server = MagicMock()
    plugin.create_lsp_adapter.return_value = lsp
    call_ext = MagicMock()
    call_ext._sites_seen = 0
    plugin.create_call_extractor.return_value = call_ext
    plugin.create_type_ref_extractor.return_value = MagicMock()
    return plugin, lsp


def _make_csharp_plugin():
    """Return a mock plugin with name='csharp'."""
    plugin = MagicMock()
    plugin.name = "csharp"
    plugin.file_extensions = frozenset({".cs"})
    lsp = MagicMock()
    lsp.language_server = MagicMock()
    plugin.create_lsp_adapter.return_value = lsp
    plugin.create_call_extractor.return_value = MagicMock()
    plugin.create_type_ref_extractor.return_value = MagicMock()
    return plugin, lsp


def test_index_calls_python_builds_module_full_names_and_passes_to_resolver() -> None:
    """index_calls() for a Python plugin passes module_full_names to SymbolResolver."""
    conn = MagicMock()
    plugin, _lsp = _make_python_plugin()
    registry = MagicMock()
    registry.detect.return_value = [plugin]

    svc = SynappsService(conn=conn, registry=registry)

    with patch("synapps.service.indexing.get_method_symbol_map", return_value={}), \
         patch("synapps.service.indexing.SymbolResolver") as MockResolver, \
         patch("synapps.service.indexing.OverridesIndexer"):

        mock_resolver_inst = MagicMock()
        mock_resolver_inst._unresolved_sites = []
        MockResolver.return_value = mock_resolver_inst

        # Module query returns (full_name, file_path) rows
        conn.query.side_effect = [
            [("mypkg.mymod", "/proj/mymod.py"), ("mypkg.other", "/proj/other.py")],
            [[0]],  # calls count
        ]

        svc.index_calls("/proj")

        # SymbolResolver must have been called with module_full_names containing both modules
        call_kwargs = MockResolver.call_args
        module_full_names = call_kwargs.kwargs.get("module_full_names")
        assert module_full_names is not None, "module_full_names not passed to SymbolResolver"
        assert "mypkg.mymod" in module_full_names
        assert "mypkg.other" in module_full_names


def test_index_calls_python_wires_module_name_resolver() -> None:
    """index_calls() wires _module_name_resolver on the call extractor for Python."""
    conn = MagicMock()
    plugin, _lsp = _make_python_plugin()

    call_ext = MagicMock(spec=["_module_name_resolver", "_sites_seen"])
    call_ext._module_name_resolver = None
    call_ext._sites_seen = 0
    plugin.create_call_extractor.return_value = call_ext

    registry = MagicMock()
    registry.detect.return_value = [plugin]

    svc = SynappsService(conn=conn, registry=registry)

    with patch("synapps.service.indexing.get_method_symbol_map", return_value={}), \
         patch("synapps.service.indexing.SymbolResolver") as MockResolver, \
         patch("synapps.service.indexing.OverridesIndexer"):

        mock_resolver_inst = MagicMock()
        mock_resolver_inst._unresolved_sites = []
        MockResolver.return_value = mock_resolver_inst

        conn.query.side_effect = [
            [("mypkg.mymod", "/proj/mymod.py")],
            [[0]],  # calls count
        ]

        svc.index_calls("/proj")

        # After the call, _module_name_resolver should be set (not None)
        assert call_ext._module_name_resolver is not None, "_module_name_resolver not wired"
        # Verify it maps file path to module name
        assert call_ext._module_name_resolver("/proj/mymod.py") == "mypkg.mymod"
        assert call_ext._module_name_resolver("/proj/missing.py") is None


def test_index_calls_python_calls_overrides_indexer() -> None:
    """index_calls() for a Python plugin calls OverridesIndexer(conn).index()."""
    conn = MagicMock()
    plugin, _lsp = _make_python_plugin()
    registry = MagicMock()
    registry.detect.return_value = [plugin]

    svc = SynappsService(conn=conn, registry=registry)

    with patch("synapps.service.indexing.get_method_symbol_map", return_value={}), \
         patch("synapps.service.indexing.SymbolResolver") as MockResolver, \
         patch("synapps.service.indexing.OverridesIndexer") as MockOverrides:

        mock_resolver_inst = MagicMock()
        mock_resolver_inst._unresolved_sites = []
        MockResolver.return_value = mock_resolver_inst

        conn.query.side_effect = [
            [],     # module query (no modules)
            [[0]],  # calls count
        ]

        svc.index_calls("/proj")

        MockOverrides.assert_called_once_with(conn)
        MockOverrides.return_value.index.assert_called_once()


def test_index_calls_python_iterates_unresolved_sites() -> None:
    """index_calls() iterates resolver._unresolved_sites for DEBUG logging."""
    conn = MagicMock()
    plugin, _lsp = _make_python_plugin()
    registry = MagicMock()
    registry.detect.return_value = [plugin]

    svc = SynappsService(conn=conn, registry=registry)

    with patch("synapps.service.indexing.get_method_symbol_map", return_value={}), \
         patch("synapps.service.indexing.SymbolResolver") as MockResolver, \
         patch("synapps.service.indexing.OverridesIndexer"), \
         patch("synapps.service.indexing.log") as mock_log:

        mock_resolver_inst = MagicMock()
        mock_resolver_inst._unresolved_sites = ["site1: unresolved", "site2: unresolved"]
        MockResolver.return_value = mock_resolver_inst

        conn.query.side_effect = [
            [],     # module query
            [[0]],  # calls count
        ]

        svc.index_calls("/proj")

        # log.debug should be called for each unresolved site
        debug_messages = [str(call.args) for call in mock_log.debug.call_args_list]
        assert any("site1" in m for m in debug_messages), f"Expected site1 in debug log, got: {debug_messages}"
        assert any("site2" in m for m in debug_messages), f"Expected site2 in debug log, got: {debug_messages}"


def test_index_calls_csharp_no_module_full_names_no_overrides_indexer() -> None:
    """index_calls() for a C# plugin does NOT build module_full_names or call OverridesIndexer."""
    conn = MagicMock()
    plugin, _lsp = _make_csharp_plugin()
    registry = MagicMock()
    registry.detect.return_value = [plugin]

    svc = SynappsService(conn=conn, registry=registry)

    with patch("synapps.service.indexing.get_method_symbol_map", return_value={}), \
         patch("synapps.service.indexing.SymbolResolver") as MockResolver, \
         patch("synapps.service.indexing.OverridesIndexer") as MockOverrides:

        mock_resolver_inst = MagicMock()
        MockResolver.return_value = mock_resolver_inst

        svc.index_calls("/proj")

        # OverridesIndexer must NOT be called for C#
        MockOverrides.assert_not_called()

        # SymbolResolver must NOT receive module_full_names (or it should be empty set)
        call_kwargs = MockResolver.call_args
        module_full_names = call_kwargs.kwargs.get("module_full_names")
        # C# path: module_full_names should be empty set or not passed
        assert not module_full_names, f"C# should not pass module_full_names, got: {module_full_names}"


def test_slim_extracts_specified_fields_from_mock_node() -> None:
    node = _node(["Method"], {"full_name": "Ns.Foo.Bar", "file_path": "/f.cs", "line": 10, "end_line": 20, "language": "csharp"})
    result = _slim(node, "full_name", "file_path", "line")
    assert result == {"full_name": "Ns.Foo.Bar", "file_path": "/f.cs", "line": 10}

def test_slim_skips_missing_fields() -> None:
    node = _node(["Method"], {"full_name": "Ns.Foo.Bar"})
    result = _slim(node, "full_name", "file_path", "line")
    assert result == {"full_name": "Ns.Foo.Bar"}

def test_slim_works_with_plain_dict() -> None:
    d = {"full_name": "Ns.Foo", "file_path": "/f.cs", "extra": "noise"}
    result = _slim(d, "full_name", "file_path")
    assert result == {"full_name": "Ns.Foo", "file_path": "/f.cs"}

def test_apply_limit_returns_list_when_under() -> None:
    items = [{"a": 1}, {"a": 2}]
    result = _apply_limit(items, 5)
    assert result == items
    assert isinstance(result, list)

def test_apply_limit_returns_dict_when_over() -> None:
    items = [{"a": i} for i in range(10)]
    result = _apply_limit(items, 3)
    assert result["_total"] == 10
    assert result["_truncated"] is True
    assert len(result["results"]) == 3

def test_apply_limit_at_boundary_returns_list() -> None:
    items = [{"a": i} for i in range(5)]
    result = _apply_limit(items, 5)
    assert isinstance(result, list)
    assert len(result) == 5


def test_find_type_impact_applies_limit() -> None:
    svc = _service()
    refs = [{"full_name": f"Ns.R{i}", "file_path": f"/f{i}.cs", "context": "prod"} for i in range(10)]
    impact = {"type": "Ns.Foo", "references": refs, "prod_count": 10, "test_count": 0}
    with patch("synapps.service.find_type_impact", return_value=impact):
        result = svc.find_type_impact("Ns.Foo", limit=3)
    assert result["_total_references"] == 10
    assert len(result["references"]) == 3


# --- _short_ref tests ---


def test_short_ref_strips_package_and_params() -> None:
    assert _short_ref("com.example.Foo.bar(int, String)") == "Foo.bar"


def test_short_ref_class_only() -> None:
    assert _short_ref("com.example.Foo") == "example.Foo"


def test_short_ref_simple_name() -> None:
    assert _short_ref("Foo") == "Foo"


def test_short_ref_two_parts() -> None:
    assert _short_ref("Foo.bar") == "Foo.bar"


# --- _rel_path / search_symbols path stripping ---


def test_rel_path_strips_project_root() -> None:
    svc = _service()
    svc._project_roots = ["/proj/root"]
    assert svc._rel_path("/proj/root/src/Foo.cs") == "src/Foo.cs"


def test_rel_path_preserves_unknown_path() -> None:
    svc = _service()
    svc._project_roots = ["/proj/root"]
    assert svc._rel_path("/other/path/Foo.cs") == "/other/path/Foo.cs"


def test_analyze_change_impact_returns_text() -> None:
    svc = _service()
    svc._project_roots = ["/proj"]
    impact = {
        "target": "Ns.Svc.Do",
        "direct_callers": [{"full_name": "Ns.Ctrl.Action", "file_path": "/proj/src/Ctrl.cs"}],
        "transitive_callers": [{"full_name": "Ns.App.Run", "file_path": "/proj/src/App.cs"}],
        "test_coverage": [{"full_name": "Ns.Tests.DoTest", "file_path": "/proj/tests/DoTest.cs"}],
        "direct_callees": [{"full_name": "Ns.Repo.Save", "file_path": "/proj/src/Repo.cs"}],
        "total_affected": 3,
    }
    with patch("synapps.service.analyze_change_impact", return_value=impact):
        result = svc.analyze_change_impact("Ns.Svc.Do")

    assert isinstance(result, str)
    assert "Ns.Svc.Do" in result
    assert "3 affected" in result
    assert "Ctrl.Action" in result
    assert "src/Ctrl.cs" in result
    assert "App.Run" in result
    assert "DoTest" in result
    assert "Repo.Save" in result


def test_search_symbols_returns_relative_paths() -> None:
    svc = _service()
    svc._project_roots = ["/proj"]
    node = _node(["Class"], {
        "full_name": "Ns.Foo", "name": "Foo", "kind": "class",
        "file_path": "/proj/src/Foo.cs", "line": 1,
    })
    with patch("synapps.service.search_symbols", return_value=[node]):
        result = svc.search_symbols("Foo")
    assert result[0]["file_path"] == "src/Foo.cs"


# ---------------------------------------------------------------------------
# find_tests_for: fallback to transitive CALLS when TESTS edges return empty
# ---------------------------------------------------------------------------

def test_find_tests_for_falls_back_to_transitive_calls() -> None:
    svc = _service()
    with patch("synapps.service.query_find_tests_for", return_value=[]) as mock_tests, \
         patch("synapps.service.query_find_test_coverage", return_value=[
             {"full_name": "tests.test_order.test_create", "file_path": "/tests/test_order.py"}
         ]) as mock_coverage:
        result = svc.find_tests_for("Ns.OrderService.create")
    mock_tests.assert_called_once()
    mock_coverage.assert_called_once()
    assert len(result) == 1
    assert result[0]["full_name"] == "tests.test_order.test_create"


def test_find_tests_for_skips_fallback_when_tests_edge_found() -> None:
    svc = _service()
    direct_result = [{"full_name": "tests.test_direct.test_it", "file_path": "/tests/test_direct.py", "line": 5}]
    with patch("synapps.service.query_find_tests_for", return_value=direct_result) as mock_tests, \
         patch("synapps.service.query_find_test_coverage") as mock_coverage:
        result = svc.find_tests_for("Ns.Foo.bar")
    mock_tests.assert_called_once()
    mock_coverage.assert_not_called()
    assert len(result) == 1
