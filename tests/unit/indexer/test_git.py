from __future__ import annotations

from unittest.mock import MagicMock, patch, call
from synapse.indexer.git import (
    GitDiff,
    is_git_repo,
    rev_parse_head,
    compute_git_diff,
    _diff_name_status,
)


class TestIsGitRepo:
    @patch("synapse.indexer.git.Path")
    def test_returns_true_when_git_dir_exists(self, mock_path_cls: MagicMock) -> None:
        mock_path_cls.return_value.__truediv__ = MagicMock(
            return_value=MagicMock(is_dir=MagicMock(return_value=True))
        )
        assert is_git_repo("/my/project") is True

    @patch("synapse.indexer.git.Path")
    def test_returns_false_when_no_git_dir(self, mock_path_cls: MagicMock) -> None:
        mock_path_cls.return_value.__truediv__ = MagicMock(
            return_value=MagicMock(is_dir=MagicMock(return_value=False))
        )
        assert is_git_repo("/not/a/repo") is False


class TestRevParseHead:
    @patch("synapse.indexer.git.subprocess")
    def test_returns_sha_on_success(self, mock_sub: MagicMock) -> None:
        mock_sub.run.return_value = MagicMock(returncode=0, stdout="abc123def\n")
        result = rev_parse_head("/my/project")
        assert result == "abc123def"
        mock_sub.run.assert_called_once_with(
            ["git", "rev-parse", "HEAD"],
            cwd="/my/project",
            capture_output=True,
            text=True,
        )

    @patch("synapse.indexer.git.subprocess")
    def test_returns_none_on_failure(self, mock_sub: MagicMock) -> None:
        mock_sub.run.return_value = MagicMock(returncode=128, stdout="")
        assert rev_parse_head("/not/a/repo") is None


class TestDiffNameStatus:
    @patch("synapse.indexer.git.subprocess")
    def test_parses_modified_and_deleted(self, mock_sub: MagicMock) -> None:
        mock_sub.run.return_value = MagicMock(
            returncode=0, stdout="M\tsrc/foo.py\nD\tsrc/bar.py\n"
        )
        result = _diff_name_status("/proj", "abc..HEAD")
        assert ("M", "src/foo.py", None) in result
        assert ("D", "src/bar.py", None) in result

    @patch("synapse.indexer.git.subprocess")
    def test_parses_rename(self, mock_sub: MagicMock) -> None:
        mock_sub.run.return_value = MagicMock(
            returncode=0, stdout="R100\told/file.py\tnew/file.py\n"
        )
        result = _diff_name_status("/proj", "abc..HEAD")
        assert result == [("R100", "old/file.py", "new/file.py")]

    @patch("synapse.indexer.git.subprocess")
    def test_parses_added(self, mock_sub: MagicMock) -> None:
        mock_sub.run.return_value = MagicMock(
            returncode=0, stdout="A\tnew_file.py\n"
        )
        result = _diff_name_status("/proj", "abc..HEAD")
        assert result == [("A", "new_file.py", None)]

    @patch("synapse.indexer.git.subprocess")
    def test_returns_empty_on_failure(self, mock_sub: MagicMock) -> None:
        mock_sub.run.return_value = MagicMock(returncode=1, stdout="")
        assert _diff_name_status("/proj", "abc..HEAD") == []

    @patch("synapse.indexer.git.subprocess")
    def test_cached_ref_spec(self, mock_sub: MagicMock) -> None:
        mock_sub.run.return_value = MagicMock(returncode=0, stdout="")
        _diff_name_status("/proj", "--cached")
        cmd = mock_sub.run.call_args[0][0]
        assert "--cached" in cmd

    @patch("synapse.indexer.git.subprocess")
    def test_none_ref_spec_no_extra_args(self, mock_sub: MagicMock) -> None:
        mock_sub.run.return_value = MagicMock(returncode=0, stdout="")
        _diff_name_status("/proj", None)
        cmd = mock_sub.run.call_args[0][0]
        assert cmd == ["git", "diff", "--name-status"]


class TestComputeGitDiff:
    @patch("synapse.indexer.git._diff_name_status")
    def test_modified_file_in_to_reindex(self, mock_diff: MagicMock) -> None:
        mock_diff.side_effect = [
            [("M", "src/foo.py", None)],  # committed
            [],  # unstaged
            [],  # staged
        ]
        result = compute_git_diff("/proj", "abc123")
        assert "/proj/src/foo.py" in result.to_reindex
        assert "/proj/src/foo.py" not in result.to_delete

    @patch("synapse.indexer.git._diff_name_status")
    def test_deleted_file_in_to_delete(self, mock_diff: MagicMock) -> None:
        mock_diff.side_effect = [
            [("D", "src/bar.py", None)],  # committed
            [],  # unstaged
            [],  # staged
        ]
        result = compute_git_diff("/proj", "abc123")
        assert "/proj/src/bar.py" in result.to_delete

    @patch("synapse.indexer.git._diff_name_status")
    def test_added_file_in_to_reindex(self, mock_diff: MagicMock) -> None:
        mock_diff.side_effect = [
            [("A", "src/new.py", None)],
            [],
            [],
        ]
        result = compute_git_diff("/proj", "abc123")
        assert "/proj/src/new.py" in result.to_reindex

    @patch("synapse.indexer.git._diff_name_status")
    def test_renamed_file_in_renames_and_reindex(self, mock_diff: MagicMock) -> None:
        mock_diff.side_effect = [
            [("R100", "old/file.py", "new/file.py")],
            [],
            [],
        ]
        result = compute_git_diff("/proj", "abc123")
        assert ("/proj/old/file.py", "/proj/new/file.py") in result.renames
        assert "/proj/new/file.py" in result.to_reindex
        # Renamed file's old path must NOT be in to_delete
        assert "/proj/old/file.py" not in result.to_delete

    @patch("synapse.indexer.git._diff_name_status")
    def test_uncommitted_changes_included(self, mock_diff: MagicMock) -> None:
        mock_diff.side_effect = [
            [],  # committed
            [("M", "src/unstaged.py", None)],  # unstaged
            [("A", "src/staged.py", None)],  # staged
        ]
        result = compute_git_diff("/proj", "abc123")
        assert "/proj/src/unstaged.py" in result.to_reindex
        assert "/proj/src/staged.py" in result.to_reindex

    @patch("synapse.indexer.git._diff_name_status")
    def test_diff_calls_three_subprocess_diffs(self, mock_diff: MagicMock) -> None:
        mock_diff.side_effect = [[], [], []]
        compute_git_diff("/proj", "abc123")
        assert mock_diff.call_count == 3
        mock_diff.assert_any_call("/proj", "abc123..HEAD")
        mock_diff.assert_any_call("/proj", None)
        mock_diff.assert_any_call("/proj", "--cached")
