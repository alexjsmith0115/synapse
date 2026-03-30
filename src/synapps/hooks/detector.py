"""Detect which AI coding agents are installed on this machine."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DetectedAgent:
    """An agent found on the local machine."""

    name: str
    display_name: str
    config_path: Path


def detect_agents(
    *,
    home_dir: Path | None = None,
    project_path: Path | None = None,
) -> list[DetectedAgent]:
    """Return agents whose marker directories exist on disk."""
    home = home_dir or Path.home()
    project = project_path or Path.cwd()

    agents: list[DetectedAgent] = []

    if (home / ".claude").is_dir():
        agents.append(DetectedAgent(
            name="claude",
            display_name="Claude Code",
            config_path=home / ".claude" / "settings.json",
        ))

    if (home / ".cursor").is_dir():
        agents.append(DetectedAgent(
            name="cursor",
            display_name="Cursor",
            config_path=home / ".cursor" / "hooks.json",
        ))

    if (project / ".github").is_dir():
        agents.append(DetectedAgent(
            name="copilot",
            display_name="GitHub Copilot",
            config_path=project / ".github" / "hooks" / "hooks.json",
        ))

    return agents
