"""Tests for auto-sync logic in MCP tools."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from synapps.mcp.tools import _check_auto_sync


@pytest.fixture
def mock_service():
    svc = MagicMock()
    svc._conn = MagicMock()
    return svc


@pytest.fixture
def git_project(tmp_path):
    """Create a tmp dir that looks like a git project with .synapps/config.json."""
    return str(tmp_path)


class TestCheckAutoSync:
    """Unit tests for _check_auto_sync core logic."""

    def test_no_project_path_skips(self, mock_service):
        _check_auto_sync("", mock_service)
        mock_service.smart_index.assert_not_called()

    def test_auto_sync_disabled_in_config_skips(self, mock_service, git_project):
        config_dir = Path(git_project) / ".synapps"
        config_dir.mkdir()
        (config_dir / "config.json").write_text(json.dumps({"auto_sync": False}))

        _check_auto_sync(git_project, mock_service)
        mock_service.smart_index.assert_not_called()

    @patch("synapps.mcp.tools.is_git_repo", return_value=False)
    def test_not_git_repo_skips(self, mock_is_git, mock_service, git_project):
        _check_auto_sync(git_project, mock_service)
        mock_service.smart_index.assert_not_called()

    @patch("synapps.mcp.tools.get_last_indexed_commit", return_value=None)
    @patch("synapps.mcp.tools.is_git_repo", return_value=True)
    def test_no_stored_sha_skips(self, mock_is_git, mock_get_commit, mock_service, git_project):
        _check_auto_sync(git_project, mock_service)
        mock_service.smart_index.assert_not_called()

    @patch("synapps.mcp.tools.dirty_tracked_paths", return_value=set())
    @patch("synapps.mcp.tools.rev_parse_head", return_value="abc123")
    @patch("synapps.mcp.tools.get_last_indexed_commit", return_value="abc123")
    @patch("synapps.mcp.tools.is_git_repo", return_value=True)
    def test_shas_match_no_dirty_files_skips(self, mock_is_git, mock_get_commit, mock_rev, mock_dirty, mock_service, git_project):
        _check_auto_sync(git_project, mock_service)
        mock_service.smart_index.assert_not_called()

    @patch("synapps.mcp.tools.check_staleness", return_value={"is_stale": True})
    @patch("synapps.mcp.tools.dirty_tracked_paths", return_value={"/proj/a.py"})
    @patch("synapps.mcp.tools.rev_parse_head", return_value="abc123")
    @patch("synapps.mcp.tools.get_last_indexed_commit", return_value="abc123")
    @patch("synapps.mcp.tools.is_git_repo", return_value=True)
    def test_shas_match_stale_dirty_file_triggers_sync(self, mock_is_git, mock_get_commit, mock_rev, mock_dirty, mock_stale, mock_service, git_project):
        """When SHAs match but a dirty tracked file is stale, auto-sync fires."""
        _check_auto_sync(git_project, mock_service)
        mock_service.smart_index.assert_called_once_with(git_project)

    @patch("synapps.mcp.tools.check_staleness", return_value={"is_stale": False})
    @patch("synapps.mcp.tools.dirty_tracked_paths", return_value={"/proj/a.py"})
    @patch("synapps.mcp.tools.rev_parse_head", return_value="abc123")
    @patch("synapps.mcp.tools.get_last_indexed_commit", return_value="abc123")
    @patch("synapps.mcp.tools.is_git_repo", return_value=True)
    def test_shas_match_fresh_dirty_file_skips(self, mock_is_git, mock_get_commit, mock_rev, mock_dirty, mock_stale, mock_service, git_project):
        """When SHAs match and dirty files are fresh in the graph, skip sync."""
        _check_auto_sync(git_project, mock_service)
        mock_service.smart_index.assert_not_called()

    @patch("synapps.mcp.tools.rev_parse_head", return_value="def456")
    @patch("synapps.mcp.tools.get_last_indexed_commit", return_value="abc123")
    @patch("synapps.mcp.tools.is_git_repo", return_value=True)
    def test_shas_differ_triggers_smart_index(self, mock_is_git, mock_get_commit, mock_rev, mock_service, git_project):
        _check_auto_sync(git_project, mock_service)
        mock_service.smart_index.assert_called_once_with(git_project)

    def test_missing_config_file_defaults_to_enabled(self, mock_service, git_project):
        """D-07: config file missing defaults to auto_sync=True."""
        with patch("synapps.mcp.tools.is_git_repo", return_value=True), \
             patch("synapps.mcp.tools.get_last_indexed_commit", return_value="abc123"), \
             patch("synapps.mcp.tools.rev_parse_head", return_value="def456"):
            _check_auto_sync(git_project, mock_service)
            mock_service.smart_index.assert_called_once_with(git_project)

    def test_malformed_config_json_defaults_to_enabled(self, mock_service, git_project):
        """Corrupt config.json should not disable auto-sync."""
        config_dir = Path(git_project) / ".synapps"
        config_dir.mkdir()
        (config_dir / "config.json").write_text("not valid json{{{")

        with patch("synapps.mcp.tools.is_git_repo", return_value=True), \
             patch("synapps.mcp.tools.get_last_indexed_commit", return_value="abc123"), \
             patch("synapps.mcp.tools.rev_parse_head", return_value="def456"):
            _check_auto_sync(git_project, mock_service)
            mock_service.smart_index.assert_called_once_with(git_project)

    def test_config_without_auto_sync_key_defaults_to_enabled(self, mock_service, git_project):
        """Config exists but without auto_sync key -> default True."""
        config_dir = Path(git_project) / ".synapps"
        config_dir.mkdir()
        (config_dir / "config.json").write_text(json.dumps({"other_key": "value"}))

        with patch("synapps.mcp.tools.is_git_repo", return_value=True), \
             patch("synapps.mcp.tools.get_last_indexed_commit", return_value="abc123"), \
             patch("synapps.mcp.tools.rev_parse_head", return_value="def456"):
            _check_auto_sync(git_project, mock_service)
            mock_service.smart_index.assert_called_once_with(git_project)
