"""Tests for bash gate script behavior via subprocess."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from synapps.hooks.installer import install_scripts


@pytest.fixture()
def hooks_dir(tmp_path: Path) -> Path:
    d = tmp_path / ".synapps" / "hooks"
    install_scripts(d)
    return d


@pytest.fixture()
def indexed_project(tmp_path: Path) -> Path:
    """A directory with .synapps/config.json present."""
    config_dir = tmp_path / "project" / ".synapps"
    config_dir.mkdir(parents=True)
    (config_dir / "config.json").write_text("{}")
    return tmp_path / "project"


@pytest.fixture()
def unindexed_project(tmp_path: Path) -> Path:
    """A directory with no .synapps/config.json."""
    project = tmp_path / "bare-project"
    project.mkdir()
    return project


class TestClaudeGate:
    def test_exits_zero(self, hooks_dir: Path, indexed_project: Path) -> None:
        result = subprocess.run(
            [str(hooks_dir / "claude-gate.sh")],
            cwd=str(indexed_project),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_emits_reminder_in_indexed_project(
        self, hooks_dir: Path, indexed_project: Path,
    ) -> None:
        result = subprocess.run(
            [str(hooks_dir / "claude-gate.sh")],
            cwd=str(indexed_project),
            capture_output=True,
            text=True,
        )
        assert "Synapps" in result.stderr

    def test_silent_in_unindexed_project(
        self, hooks_dir: Path, unindexed_project: Path,
    ) -> None:
        result = subprocess.run(
            [str(hooks_dir / "claude-gate.sh")],
            cwd=str(unindexed_project),
            capture_output=True,
            text=True,
        )
        assert result.stderr == ""


class TestCopilotGate:
    def test_emits_allow_json(self, hooks_dir: Path, indexed_project: Path) -> None:
        stdin_data = json.dumps({"toolName": "grep", "toolArgs": "{}"})
        result = subprocess.run(
            [str(hooks_dir / "copilot-gate.sh")],
            cwd=str(indexed_project),
            input=stdin_data,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout.strip())
        assert output["permissionDecision"] == "allow"

    def test_emits_reminder_for_grep(
        self, hooks_dir: Path, indexed_project: Path,
    ) -> None:
        stdin_data = json.dumps({"toolName": "grep", "toolArgs": "{}"})
        result = subprocess.run(
            [str(hooks_dir / "copilot-gate.sh")],
            cwd=str(indexed_project),
            input=stdin_data,
            capture_output=True,
            text=True,
        )
        assert "Synapps" in result.stderr

    def test_silent_for_non_search_tool(
        self, hooks_dir: Path, indexed_project: Path,
    ) -> None:
        stdin_data = json.dumps({"toolName": "edit", "toolArgs": "{}"})
        result = subprocess.run(
            [str(hooks_dir / "copilot-gate.sh")],
            cwd=str(indexed_project),
            input=stdin_data,
            capture_output=True,
            text=True,
        )
        assert result.stderr == ""

    def test_silent_in_unindexed_project(
        self, hooks_dir: Path, unindexed_project: Path,
    ) -> None:
        stdin_data = json.dumps({"toolName": "grep", "toolArgs": "{}"})
        result = subprocess.run(
            [str(hooks_dir / "copilot-gate.sh")],
            cwd=str(unindexed_project),
            input=stdin_data,
            capture_output=True,
            text=True,
        )
        assert result.stderr == ""
        output = json.loads(result.stdout.strip())
        assert output["permissionDecision"] == "allow"
