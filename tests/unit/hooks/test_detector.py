"""Tests for agent detection."""
from __future__ import annotations

from pathlib import Path

import pytest


class TestDetectAgents:
    def test_detects_claude_code(self, tmp_path: Path) -> None:
        from synapps.hooks.detector import detect_agents

        (tmp_path / ".claude").mkdir()
        agents = detect_agents(home_dir=tmp_path, project_path=tmp_path)
        assert any(a.name == "claude" for a in agents)

    def test_detects_cursor(self, tmp_path: Path) -> None:
        from synapps.hooks.detector import detect_agents

        (tmp_path / ".cursor").mkdir()
        agents = detect_agents(home_dir=tmp_path, project_path=tmp_path)
        assert any(a.name == "cursor" for a in agents)

    def test_detects_copilot(self, tmp_path: Path) -> None:
        from synapps.hooks.detector import detect_agents

        (tmp_path / ".github").mkdir()
        agents = detect_agents(home_dir=tmp_path, project_path=tmp_path)
        assert any(a.name == "copilot" for a in agents)

    def test_skips_missing_agents(self, tmp_path: Path) -> None:
        from synapps.hooks.detector import detect_agents

        agents = detect_agents(home_dir=tmp_path, project_path=tmp_path)
        assert agents == []

    def test_detects_multiple_agents(self, tmp_path: Path) -> None:
        from synapps.hooks.detector import detect_agents

        (tmp_path / ".claude").mkdir()
        (tmp_path / ".cursor").mkdir()
        agents = detect_agents(home_dir=tmp_path, project_path=tmp_path)
        names = [a.name for a in agents]
        assert "claude" in names
        assert "cursor" in names

    def test_agent_has_config_path(self, tmp_path: Path) -> None:
        from synapps.hooks.detector import detect_agents

        (tmp_path / ".claude").mkdir()
        agents = detect_agents(home_dir=tmp_path, project_path=tmp_path)
        claude = next(a for a in agents if a.name == "claude")
        assert claude.config_path == tmp_path / ".claude" / "settings.json"

    def test_copilot_config_path_is_project_relative(self, tmp_path: Path) -> None:
        from synapps.hooks.detector import detect_agents

        project = tmp_path / "my-repo"
        (project / ".github").mkdir(parents=True)
        agents = detect_agents(home_dir=tmp_path, project_path=project)
        copilot = next(a for a in agents if a.name == "copilot")
        assert copilot.config_path == project / ".github" / "hooks" / "hooks.json"
