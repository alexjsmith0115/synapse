from datetime import datetime, timezone
from unittest.mock import MagicMock
import os

import pytest

from synapps.indexer.sync import SyncResult, compute_sync_diff, sync_project


def _ts(year=2026, month=3, day=20, hour=12) -> str:
    """Return an ISO timestamp string."""
    return datetime(year, month, day, hour, tzinfo=timezone.utc).isoformat()


def _mtime(year=2026, month=3, day=20, hour=14) -> float:
    """Return a POSIX timestamp (float)."""
    return datetime(year, month, day, hour, tzinfo=timezone.utc).timestamp()


def test_stale_file_detected():
    graph = {"/proj/a.cs": _ts(hour=10)}
    disk = {"/proj/a.cs": _mtime(hour=14)}
    to_delete, to_reindex, unchanged = compute_sync_diff(graph, disk)
    assert to_delete == set()
    assert to_reindex == {"/proj/a.cs"}
    assert unchanged == set()


def test_fresh_file_unchanged():
    graph = {"/proj/a.cs": _ts(hour=14)}
    disk = {"/proj/a.cs": _mtime(hour=10)}
    to_delete, to_reindex, unchanged = compute_sync_diff(graph, disk)
    assert to_delete == set()
    assert to_reindex == set()
    assert unchanged == {"/proj/a.cs"}


def test_deleted_file_detected():
    graph = {"/proj/a.cs": _ts(), "/proj/gone.cs": _ts()}
    disk = {"/proj/a.cs": _mtime(hour=10)}
    to_delete, to_reindex, unchanged = compute_sync_diff(graph, disk)
    assert to_delete == {"/proj/gone.cs"}
    assert to_reindex == set()
    assert unchanged == {"/proj/a.cs"}


def test_new_file_detected():
    graph = {"/proj/a.cs": _ts(hour=14)}
    disk = {"/proj/a.cs": _mtime(hour=10), "/proj/new.cs": _mtime(hour=15)}
    to_delete, to_reindex, unchanged = compute_sync_diff(graph, disk)
    assert to_delete == set()
    assert to_reindex == {"/proj/new.cs"}
    assert unchanged == {"/proj/a.cs"}


def test_empty_graph_all_new():
    graph = {}
    disk = {"/proj/a.cs": _mtime(), "/proj/b.cs": _mtime()}
    to_delete, to_reindex, unchanged = compute_sync_diff(graph, disk)
    assert to_delete == set()
    assert to_reindex == {"/proj/a.cs", "/proj/b.cs"}
    assert unchanged == set()


def test_empty_disk_all_deleted():
    graph = {"/proj/a.cs": _ts(), "/proj/b.cs": _ts()}
    disk = {}
    to_delete, to_reindex, unchanged = compute_sync_diff(graph, disk)
    assert to_delete == {"/proj/a.cs", "/proj/b.cs"}
    assert to_reindex == set()
    assert unchanged == set()


def test_equal_timestamp_treated_as_unchanged():
    """When mtime == last_indexed exactly, file is unchanged (not stale)."""
    ts = _ts(hour=12)
    mtime = datetime(2026, 3, 20, 12, tzinfo=timezone.utc).timestamp()
    graph = {"/proj/a.cs": ts}
    disk = {"/proj/a.cs": mtime}
    to_delete, to_reindex, unchanged = compute_sync_diff(graph, disk)
    assert to_delete == set()
    assert to_reindex == set()
    assert unchanged == {"/proj/a.cs"}


def test_sync_result_total():
    r = SyncResult(updated=3, deleted=1, unchanged=10)
    assert r.updated == 3
    assert r.deleted == 1
    assert r.unchanged == 10


def test_sync_project_orchestration(tmp_path):
    """sync_project deletes removed files, re-indexes stale/new, skips fresh."""
    (tmp_path / "a.cs").write_text("class A {}")
    (tmp_path / "new.cs").write_text("class New {}")

    old_ts = _ts(hour=1)

    future_mtime = _mtime(hour=23)
    os.utime(str(tmp_path / "a.cs"), (future_mtime, future_mtime))
    os.utime(str(tmp_path / "new.cs"), (future_mtime, future_mtime))

    conn = MagicMock()
    conn.query.side_effect = [
        [[str(tmp_path)]],  # repo check
        [[str(tmp_path / "a.cs"), old_ts], [str(tmp_path / "gone.cs"), old_ts]],  # file list
    ]

    mock_indexer = MagicMock()
    disk_files = {
        str(tmp_path / "a.cs"): os.path.getmtime(str(tmp_path / "a.cs")),
        str(tmp_path / "new.cs"): os.path.getmtime(str(tmp_path / "new.cs")),
    }

    result = sync_project(
        conn=conn,
        indexer=mock_indexer,
        root_path=str(tmp_path),
        disk_files=disk_files,
    )

    mock_indexer.delete_file.assert_called_once_with(str(tmp_path / "gone.cs"))
    reindex_calls = {call.args[0] for call in mock_indexer.reindex_file.call_args_list}
    assert str(tmp_path / "a.cs") in reindex_calls
    assert str(tmp_path / "new.cs") in reindex_calls
    for c in mock_indexer.reindex_file.call_args_list:
        assert c.args[1] == str(tmp_path)
    assert result.deleted == 1
    assert result.updated == 2
    assert result.unchanged == 0


def test_sync_project_no_changes(tmp_path):
    """When nothing changed, sync returns all zeros."""
    (tmp_path / "a.cs").write_text("class A {}")
    fresh_ts = datetime(2099, 1, 1, tzinfo=timezone.utc).isoformat()

    conn = MagicMock()
    conn.query.side_effect = [
        [[str(tmp_path)]],  # repo check
        [[str(tmp_path / "a.cs"), fresh_ts]],  # file list
    ]

    mock_indexer = MagicMock()
    disk_files = {str(tmp_path / "a.cs"): os.path.getmtime(str(tmp_path / "a.cs"))}

    result = sync_project(conn=conn, indexer=mock_indexer, root_path=str(tmp_path), disk_files=disk_files)

    mock_indexer.delete_file.assert_not_called()
    mock_indexer.reindex_file.assert_not_called()
    assert result.updated == 0
    assert result.deleted == 0
    assert result.unchanged == 1


def test_sync_project_no_repo_raises(tmp_path):
    """sync_project raises ValueError when Repository node doesn't exist."""
    conn = MagicMock()
    conn.query.return_value = []
    mock_indexer = MagicMock()

    with pytest.raises(ValueError, match="not indexed"):
        sync_project(conn=conn, indexer=mock_indexer, root_path=str(tmp_path), disk_files={})


def test_sync_project_language_filter(tmp_path):
    """sync_project with language param only queries files of that language."""
    (tmp_path / "a.cs").write_text("class A {}")

    old_ts = _ts(hour=1)
    future_mtime = _mtime(hour=23)
    os.utime(str(tmp_path / "a.cs"), (future_mtime, future_mtime))

    conn = MagicMock()
    conn.query.side_effect = [
        [[str(tmp_path)]],  # repo check
        [[str(tmp_path / "a.cs"), old_ts]],  # language-filtered file list
    ]

    mock_indexer = MagicMock()
    disk_files = {
        str(tmp_path / "a.cs"): os.path.getmtime(str(tmp_path / "a.cs")),
    }

    result = sync_project(
        conn=conn,
        indexer=mock_indexer,
        root_path=str(tmp_path),
        disk_files=disk_files,
        language="csharp",
    )

    # Verify the query used the language filter
    file_query_call = conn.query.call_args_list[1]
    assert "language" in file_query_call.args[0] or "lang" in str(file_query_call.kwargs) or "lang" in str(file_query_call.args[1])
    assert result.updated == 1
    assert result.deleted == 0


def test_sync_project_language_filter_ignores_other_languages(tmp_path):
    """With language filter, files from other languages in the graph are not deleted."""
    (tmp_path / "a.cs").write_text("class A {}")

    old_ts = _ts(hour=1)
    future_mtime = _mtime(hour=23)
    os.utime(str(tmp_path / "a.cs"), (future_mtime, future_mtime))

    conn = MagicMock()
    # When filtered by language, graph only returns csharp files — NOT typescript files
    conn.query.side_effect = [
        [[str(tmp_path)]],  # repo check
        [[str(tmp_path / "a.cs"), old_ts]],  # only csharp files returned
    ]

    mock_indexer = MagicMock()
    disk_files = {
        str(tmp_path / "a.cs"): os.path.getmtime(str(tmp_path / "a.cs")),
    }

    result = sync_project(
        conn=conn,
        indexer=mock_indexer,
        root_path=str(tmp_path),
        disk_files=disk_files,
        language="csharp",
    )

    # No deletions — typescript files in graph are invisible to this sync pass
    mock_indexer.delete_file.assert_not_called()
    assert result.deleted == 0
    assert result.updated == 1


def test_sync_project_continues_on_reindex_failure(tmp_path):
    """If reindex_file raises for one file, sync continues with remaining files."""
    (tmp_path / "a.cs").write_text("class A {}")
    (tmp_path / "b.cs").write_text("class B {}")

    old_ts = _ts(hour=1)
    future_mtime = _mtime(hour=23)
    os.utime(str(tmp_path / "a.cs"), (future_mtime, future_mtime))
    os.utime(str(tmp_path / "b.cs"), (future_mtime, future_mtime))

    conn = MagicMock()
    conn.query.side_effect = [
        [[str(tmp_path)]],  # repo check
        [[str(tmp_path / "a.cs"), old_ts], [str(tmp_path / "b.cs"), old_ts]],  # file list
    ]

    mock_indexer = MagicMock()
    mock_indexer.reindex_file.side_effect = [Exception("LSP timeout"), None]

    disk_files = {
        str(tmp_path / "a.cs"): os.path.getmtime(str(tmp_path / "a.cs")),
        str(tmp_path / "b.cs"): os.path.getmtime(str(tmp_path / "b.cs")),
    }

    result = sync_project(conn=conn, indexer=mock_indexer, root_path=str(tmp_path), disk_files=disk_files)

    assert mock_indexer.reindex_file.call_count == 2
    assert result.updated == 1
    assert result.deleted == 0
