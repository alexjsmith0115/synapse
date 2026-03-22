from __future__ import annotations

from unittest.mock import MagicMock, patch, call

import pytest

from synapse.indexer.git import GitDiff
from synapse.indexer.sync import git_sync_project, SyncResult


@pytest.fixture
def conn():
    return MagicMock()


@pytest.fixture
def indexer():
    m = MagicMock()
    m.reindex_file = MagicMock()
    m.delete_file = MagicMock()
    return m


@patch("synapse.indexer.sync.rev_parse_head", return_value="abc123")
@patch("synapse.indexer.sync.compute_git_diff")
def test_no_changes_returns_zero_sync_result(mock_diff, mock_rev, conn, indexer):
    mock_diff.return_value = GitDiff()
    result = git_sync_project(conn, indexer, "/project", "old_sha")
    assert result == SyncResult(updated=0, deleted=0, unchanged=0)
    indexer.reindex_file.assert_not_called()
    indexer.delete_file.assert_not_called()


@patch("synapse.indexer.sync.set_last_indexed_commit")
@patch("synapse.indexer.sync.rev_parse_head", return_value="new_sha")
@patch("synapse.indexer.sync.compute_git_diff")
def test_modified_file_reindexed(mock_diff, mock_rev, mock_set, conn, indexer):
    mock_diff.return_value = GitDiff(to_reindex={"/project/a.cs"})
    result = git_sync_project(conn, indexer, "/project", "old_sha")
    indexer.reindex_file.assert_called_once_with("/project/a.cs", "/project")
    assert result.updated == 1
    assert result.deleted == 0


@patch("synapse.indexer.sync.set_last_indexed_commit")
@patch("synapse.indexer.sync.rev_parse_head", return_value="new_sha")
@patch("synapse.indexer.sync.compute_git_diff")
def test_deleted_file_removed(mock_diff, mock_rev, mock_set, conn, indexer):
    mock_diff.return_value = GitDiff(to_delete={"/project/old.cs"})
    result = git_sync_project(conn, indexer, "/project", "old_sha")
    indexer.delete_file.assert_called_once_with("/project/old.cs")
    assert result.deleted == 1
    assert result.updated == 0


@patch("synapse.indexer.sync.set_last_indexed_commit")
@patch("synapse.indexer.sync.rename_file_node")
@patch("synapse.indexer.sync.rev_parse_head", return_value="new_sha")
@patch("synapse.indexer.sync.compute_git_diff")
def test_renamed_file_calls_rename_and_reindex(mock_diff, mock_rev, mock_rename, mock_set, conn, indexer):
    mock_diff.return_value = GitDiff(
        renames=[("/project/old.cs", "/project/new.cs")],
        to_reindex={"/project/new.cs"},
    )
    result = git_sync_project(conn, indexer, "/project", "old_sha")
    mock_rename.assert_called_once_with(conn, "/project/old.cs", "/project/new.cs")
    indexer.reindex_file.assert_called_once_with("/project/new.cs", "/project")
    assert result.updated == 2  # 1 rename + 1 reindex


@patch("synapse.indexer.sync.set_last_indexed_commit")
@patch("synapse.indexer.sync.rev_parse_head", return_value="head_sha")
@patch("synapse.indexer.sync.compute_git_diff")
def test_stores_commit_sha_after_sync(mock_diff, mock_rev, mock_set, conn, indexer):
    mock_diff.return_value = GitDiff(to_reindex={"/project/a.cs"})
    git_sync_project(conn, indexer, "/project", "old_sha")
    mock_set.assert_called_once_with(conn, "/project", "head_sha")


@patch("synapse.indexer.sync.set_last_indexed_commit")
@patch("synapse.indexer.sync.rev_parse_head", return_value="new_sha")
@patch("synapse.indexer.sync.compute_git_diff")
def test_reindex_failure_skipped_others_processed(mock_diff, mock_rev, mock_set, conn, indexer):
    mock_diff.return_value = GitDiff(to_reindex={"/project/a.cs", "/project/b.cs"})
    indexer.reindex_file.side_effect = [Exception("boom"), None]
    result = git_sync_project(conn, indexer, "/project", "old_sha")
    assert indexer.reindex_file.call_count == 2
    assert result.updated == 1  # one succeeded


@patch("synapse.indexer.sync.set_last_indexed_commit")
@patch("synapse.indexer.sync.rev_parse_head", return_value=None)
@patch("synapse.indexer.sync.compute_git_diff")
def test_no_head_sha_skips_commit_store(mock_diff, mock_rev, mock_set, conn, indexer):
    mock_diff.return_value = GitDiff(to_reindex={"/project/a.cs"})
    git_sync_project(conn, indexer, "/project", "old_sha")
    mock_set.assert_not_called()
