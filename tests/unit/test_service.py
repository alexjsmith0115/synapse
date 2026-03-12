from unittest.mock import MagicMock, patch

import pytest

from synapse.service import SynapseService, _p
from falkordb.node import Node as FalkorNode


# After wiring _resolve into read methods, we need to bypass resolve_full_name
# in tests that don't care about resolution.
@pytest.fixture(autouse=True)
def bypass_resolve(monkeypatch):
    """Make resolve_full_name return the name unchanged for all service tests."""
    monkeypatch.setattr("synapse.service.resolve_full_name", lambda conn, name: name)


def _node(labels: list[str], props: dict) -> FalkorNode:
    return FalkorNode(node_id=1, labels=labels, properties=props)


def _service() -> SynapseService:
    conn = MagicMock()
    return SynapseService(conn=conn)


def test_set_summary_delegates_to_nodes() -> None:
    svc = _service()
    with patch("synapse.service.set_summary") as mock_set:
        svc.set_summary("MyNs.MyClass", "Auth handler")
        mock_set.assert_called_once_with(svc._conn, "MyNs.MyClass", "Auth handler")



def test_watch_project_registers_watcher() -> None:
    svc = _service()
    mock_watcher_cls = MagicMock()
    mock_watcher = MagicMock()
    mock_watcher_cls.return_value = mock_watcher
    mock_lsp = MagicMock()
    mock_lsp.get_workspace_files.return_value = []

    with patch("synapse.service.FileWatcher", mock_watcher_cls):
        svc.watch_project("/proj", lsp_adapter=mock_lsp)
        mock_watcher.start.assert_called_once()
        assert "/proj" in svc._watchers


def test_unwatch_project_stops_watcher() -> None:
    svc = _service()
    mock_watcher = MagicMock()
    svc._watchers["/proj"] = mock_watcher

    svc.unwatch_project("/proj")

    mock_watcher.stop.assert_called_once()
    assert "/proj" not in svc._watchers


def test_get_symbol_source_reads_file_and_returns_lines(tmp_path):
    """Service reads the file from disk using line range from the graph."""
    source_file = tmp_path / "Foo.cs"
    source_file.write_text("line0\nline1\nline2\nline3\nline4\nline5\n")

    conn = MagicMock()
    svc = SynapseService(conn)

    with patch("synapse.service.get_symbol_source_info") as mock_query:
        mock_query.return_value = {"file_path": str(source_file), "line": 1, "end_line": 3}
        result = svc.get_symbol_source("Ns.C.M")

    assert "line1" in result
    assert "line2" in result
    assert "line3" in result
    assert "line0" not in result


def test_get_symbol_source_returns_none_when_symbol_not_found():
    conn = MagicMock()
    svc = SynapseService(conn)

    with patch("synapse.service.get_symbol_source_info") as mock_query:
        mock_query.return_value = None
        result = svc.get_symbol_source("Ns.Missing")

    assert result is None


def test_get_symbol_source_returns_error_when_end_line_missing(tmp_path):
    """When end_line is 0, the symbol was indexed before line ranges were added."""
    conn = MagicMock()
    svc = SynapseService(conn)

    with patch("synapse.service.get_symbol_source_info") as mock_query:
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
    svc = SynapseService(conn)

    with patch.multiple(
        "synapse.service",
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
    svc = SynapseService(conn)

    with patch("synapse.service.get_symbol", return_value=None):
        result = svc.get_context_for("Ns.Missing")

    assert result is None


def test_p_extracts_properties_and_labels_from_falkordb_node():
    node = _node(["Method"], {"full_name": "A.B", "signature": "B() : void"})
    result = _p(node)
    assert result == {"full_name": "A.B", "signature": "B() : void", "_labels": ["Method"]}


def test_p_passes_through_plain_dict():
    d = {"full_name": "A.B"}
    assert _p(d) is d


def test_find_callers_returns_plain_dicts():
    svc = _service()
    node = _node(["Method"], {"full_name": "A.Caller", "signature": "Caller() : void"})
    with patch("synapse.service.find_callers", return_value=[node]):
        result = svc.find_callers("A.B")
    assert result == [{"full_name": "A.Caller", "signature": "Caller() : void", "_labels": ["Method"]}]


def test_find_implementations_returns_plain_dicts():
    svc = _service()
    node = _node(["Class"], {"full_name": "A.Impl"})
    with patch("synapse.service.find_implementations", return_value=[node]):
        result = svc.find_implementations("A.IService")
    assert result == [{"full_name": "A.Impl", "_labels": ["Class"]}]


def test_get_symbol_returns_plain_dict_with_labels():
    svc = _service()
    node = _node(["Class"], {"full_name": "A.Cls"})
    with patch("synapse.service.get_symbol", return_value=node):
        result = svc.get_symbol("A.Cls")
    assert result == {"full_name": "A.Cls", "_labels": ["Class"]}


def test_get_symbol_returns_none_when_not_found():
    svc = _service()
    with patch("synapse.service.get_symbol", return_value=None):
        result = svc.get_symbol("Missing")
    assert result is None


def test_find_type_references_unwraps_nested_nodes():
    svc = _service()
    node = _node(["Method"], {"full_name": "A.Caller"})
    with patch("synapse.service.query_find_type_references", return_value=[{"symbol": node, "kind": "parameter"}]):
        result = svc.find_type_references("A.IService")
    assert result == [{"symbol": {"full_name": "A.Caller", "_labels": ["Method"]}, "kind": "parameter"}]


def test_find_dependencies_unwraps_nested_nodes():
    svc = _service()
    node = _node(["Class"], {"full_name": "A.Dep"})
    with patch("synapse.service.query_find_dependencies", return_value=[{"type": node, "depth": 1}]):
        result = svc.find_dependencies("A.Method")
    assert result == [{"type": {"full_name": "A.Dep", "_labels": ["Class"]}, "depth": 1}]


def test_get_hierarchy_unwraps_nodes():
    svc = _service()
    parent = _node(["Class"], {"full_name": "A.Base"})
    child = _node(["Class"], {"full_name": "A.Child"})
    iface = _node(["Interface"], {"full_name": "A.IFoo"})
    with patch("synapse.service.get_hierarchy", return_value={"parents": [parent], "children": [child], "implements": [iface]}):
        result = svc.get_hierarchy("A.Middle")
    assert result["parents"] == [{"full_name": "A.Base", "_labels": ["Class"]}]
    assert result["children"] == [{"full_name": "A.Child", "_labels": ["Class"]}]
    assert result["implements"] == [{"full_name": "A.IFoo", "_labels": ["Interface"]}]
