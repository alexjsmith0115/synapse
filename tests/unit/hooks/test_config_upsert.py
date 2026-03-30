"""Tests for per-agent config upsert and removal."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


_SYNAPPS_MARKER = ".synapps/hooks/"


class TestClaudeCodeUpsert:
    def test_creates_new_settings_file(self, tmp_path: Path) -> None:
        from synapps.hooks.config_upsert import upsert_claude_hook

        config = tmp_path / "settings.json"
        upsert_claude_hook(config, "~/.synapps/hooks/claude-gate.sh")

        data = json.loads(config.read_text())
        hooks = data["hooks"]["PreToolUse"]
        assert len(hooks) == 1
        assert hooks[0]["matcher"] == "Grep|Glob"
        assert hooks[0]["hooks"][0]["command"] == "~/.synapps/hooks/claude-gate.sh"

    def test_preserves_existing_hooks(self, tmp_path: Path) -> None:
        from synapps.hooks.config_upsert import upsert_claude_hook

        config = tmp_path / "settings.json"
        existing = {
            "hooks": {
                "PreToolUse": [
                    {"matcher": "Write", "hooks": [{"type": "command", "command": "other.sh"}]}
                ]
            }
        }
        config.write_text(json.dumps(existing))

        upsert_claude_hook(config, "~/.synapps/hooks/claude-gate.sh")

        data = json.loads(config.read_text())
        hooks = data["hooks"]["PreToolUse"]
        assert len(hooks) == 2
        assert hooks[0]["matcher"] == "Write"

    def test_replaces_existing_synapps_hook(self, tmp_path: Path) -> None:
        from synapps.hooks.config_upsert import upsert_claude_hook

        config = tmp_path / "settings.json"
        upsert_claude_hook(config, "~/.synapps/hooks/old-gate.sh")
        upsert_claude_hook(config, "~/.synapps/hooks/claude-gate.sh")

        data = json.loads(config.read_text())
        hooks = data["hooks"]["PreToolUse"]
        synapps_hooks = [h for h in hooks if _SYNAPPS_MARKER in str(h)]
        assert len(synapps_hooks) == 1

    def test_preserves_non_hook_settings(self, tmp_path: Path) -> None:
        from synapps.hooks.config_upsert import upsert_claude_hook

        config = tmp_path / "settings.json"
        config.write_text(json.dumps({"permissions": {"allow": ["Read"]}}))

        upsert_claude_hook(config, "~/.synapps/hooks/claude-gate.sh")

        data = json.loads(config.read_text())
        assert data["permissions"]["allow"] == ["Read"]


class TestCursorUpsert:
    def test_creates_new_hooks_file(self, tmp_path: Path) -> None:
        from synapps.hooks.config_upsert import upsert_cursor_hook

        config = tmp_path / "hooks.json"
        upsert_cursor_hook(config, "~/.synapps/hooks/cursor-gate.sh")

        data = json.loads(config.read_text())
        assert data["version"] == 1
        hooks = data["hooks"]["preToolUse"]
        assert len(hooks) == 1
        assert hooks[0]["command"] == "~/.synapps/hooks/cursor-gate.sh"
        assert hooks[0]["matcher"] == "Read"

    def test_preserves_existing_hooks(self, tmp_path: Path) -> None:
        from synapps.hooks.config_upsert import upsert_cursor_hook

        config = tmp_path / "hooks.json"
        existing = {"version": 1, "hooks": {"preToolUse": [
            {"command": "other.sh", "matcher": "Write"}
        ]}}
        config.write_text(json.dumps(existing))

        upsert_cursor_hook(config, "~/.synapps/hooks/cursor-gate.sh")

        data = json.loads(config.read_text())
        assert len(data["hooks"]["preToolUse"]) == 2


class TestCopilotUpsert:
    def test_creates_new_hooks_file_and_parent_dir(self, tmp_path: Path) -> None:
        from synapps.hooks.config_upsert import upsert_copilot_hook

        config = tmp_path / ".github" / "hooks" / "hooks.json"
        upsert_copilot_hook(config, "~/.synapps/hooks/copilot-gate.sh")

        assert config.exists()
        data = json.loads(config.read_text())
        assert data["version"] == 1
        hooks = data["hooks"]["preToolUse"]
        assert len(hooks) == 1
        assert hooks[0]["bash"] == "~/.synapps/hooks/copilot-gate.sh"

    def test_preserves_existing_hooks(self, tmp_path: Path) -> None:
        from synapps.hooks.config_upsert import upsert_copilot_hook

        config = tmp_path / ".github" / "hooks" / "hooks.json"
        config.parent.mkdir(parents=True)
        existing = {"version": 1, "hooks": {"preToolUse": [
            {"type": "command", "bash": "other.sh"}
        ]}}
        config.write_text(json.dumps(existing))

        upsert_copilot_hook(config, "~/.synapps/hooks/copilot-gate.sh")

        data = json.loads(config.read_text())
        assert len(data["hooks"]["preToolUse"]) == 2


class TestRemoveHooks:
    def test_remove_claude_hook(self, tmp_path: Path) -> None:
        from synapps.hooks.config_upsert import upsert_claude_hook, remove_claude_hook

        config = tmp_path / "settings.json"
        config.write_text(json.dumps({
            "hooks": {"PreToolUse": [
                {"matcher": "Write", "hooks": [{"type": "command", "command": "other.sh"}]},
            ]}
        }))
        upsert_claude_hook(config, "~/.synapps/hooks/claude-gate.sh")
        remove_claude_hook(config)

        data = json.loads(config.read_text())
        hooks = data["hooks"]["PreToolUse"]
        assert len(hooks) == 1
        assert hooks[0]["matcher"] == "Write"

    def test_remove_cursor_hook(self, tmp_path: Path) -> None:
        from synapps.hooks.config_upsert import upsert_cursor_hook, remove_cursor_hook

        config = tmp_path / "hooks.json"
        upsert_cursor_hook(config, "~/.synapps/hooks/cursor-gate.sh")
        remove_cursor_hook(config)

        data = json.loads(config.read_text())
        assert data["hooks"]["preToolUse"] == []

    def test_remove_copilot_hook(self, tmp_path: Path) -> None:
        from synapps.hooks.config_upsert import upsert_copilot_hook, remove_copilot_hook

        config = tmp_path / ".github" / "hooks" / "hooks.json"
        config.parent.mkdir(parents=True)
        upsert_copilot_hook(config, "~/.synapps/hooks/copilot-gate.sh")
        remove_copilot_hook(config)

        data = json.loads(config.read_text())
        assert data["hooks"]["preToolUse"] == []

    def test_remove_noop_if_file_missing(self, tmp_path: Path) -> None:
        from synapps.hooks.config_upsert import remove_claude_hook

        config = tmp_path / "nonexistent.json"
        remove_claude_hook(config)  # should not raise
