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
