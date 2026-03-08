from unittest.mock import MagicMock, patch
from synapse.service import SynapseService


def _service() -> SynapseService:
    conn = MagicMock()
    return SynapseService(conn=conn)


def test_set_summary_delegates_to_nodes() -> None:
    svc = _service()
    with patch("synapse.service.set_summary") as mock_set:
        svc.set_summary("MyNs.MyClass", "Auth handler")
        mock_set.assert_called_once_with(svc._conn, "MyNs.MyClass", "Auth handler")


def test_get_symbol_delegates_to_queries() -> None:
    svc = _service()
    with patch("synapse.service.get_symbol", return_value={"full_name": "X"}) as mock_get:
        result = svc.get_symbol("X")
        assert result == {"full_name": "X"}


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
            {"type": {"full_name": "Ns.UserDto", "name": "UserDto"}, "kind": "return_type"},
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
