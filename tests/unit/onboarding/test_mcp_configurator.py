from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest


class TestDetectMCPClients:
    def test_detect_clients_includes_claude_code(self, tmp_path: Path) -> None:
        from synapps.onboarding.mcp_configurator import detect_mcp_clients

        clients = detect_mcp_clients(str(tmp_path))
        names = [c.name for c in clients]
        assert "Claude Code" in names

    def test_detect_clients_skips_uninstalled(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "nonexistent_app_dir" / "config.json"

        def fake_get_config_path(key: str, **kwargs: object) -> str:
            if key == "cursor":
                return str(nonexistent)
            # For all others, return a path whose parent exists
            return str(tmp_path / f"{key}_config.json")

        with patch(
            "synapps.onboarding.mcp_configurator.get_config_path",
            side_effect=fake_get_config_path,
        ):
            from synapps.onboarding.mcp_configurator import detect_mcp_clients

            clients = detect_mcp_clients(str(tmp_path))
            names = [c.name for c in clients]

        assert "Cursor" not in names

    def test_detect_clients_includes_installed(self, tmp_path: Path) -> None:
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir()
        cursor_config = cursor_dir / "mcp.json"

        def fake_get_config_path(key: str, **kwargs: object) -> str:
            if key == "cursor":
                return str(cursor_config)
            return str(tmp_path / f"{key}_config.json")

        with patch(
            "synapps.onboarding.mcp_configurator.get_config_path",
            side_effect=fake_get_config_path,
        ):
            from synapps.onboarding.mcp_configurator import detect_mcp_clients

            clients = detect_mcp_clients(str(tmp_path))
            names = [c.name for c in clients]

        assert "Cursor" in names


    def test_cursor_entry_has_needs_project_path_true(self) -> None:
        from synapps.onboarding.mcp_configurator import _CLIENT_DEFS

        cursor_entry = next((e for e in _CLIENT_DEFS if e[1] == "cursor"), None)
        assert cursor_entry is not None, "Cursor entry not found in _CLIENT_DEFS"
        assert cursor_entry[3] is True, "Cursor needs_project_path must be True"

    def test_cursor_get_config_path_receives_project_path(self, tmp_path: Path) -> None:
        calls: list[tuple[tuple, dict]] = []

        def tracking_get_config_path(key: str, **kwargs: object) -> str:
            calls.append((key, kwargs))
            return str(tmp_path / f"{key}_config.json")

        with patch(
            "synapps.onboarding.mcp_configurator.get_config_path",
            side_effect=tracking_get_config_path,
        ):
            from synapps.onboarding.mcp_configurator import detect_mcp_clients

            detect_mcp_clients(str(tmp_path))

        cursor_calls = [(k, kw) for k, kw in calls if k == "cursor"]
        assert cursor_calls, "get_config_path was never called with 'cursor'"
        assert cursor_calls[0][1].get("path") == str(tmp_path), (
            f"Cursor's get_config_path call missing path kwarg; got kwargs={cursor_calls[0][1]}"
        )


class TestWriteMCPConfig:
    def test_write_creates_new_file(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.json"

        from synapps.onboarding.mcp_configurator import write_mcp_config

        write_mcp_config(config_path, servers_key="mcpServers")

        data = json.loads(config_path.read_text())
        assert "mcpServers" in data
        assert "synapps" in data["mcpServers"]
        assert data["mcpServers"]["synapps"]["command"] == "synapps-mcp"
        assert data["mcpServers"]["synapps"]["args"] == []

    def test_write_preserves_existing_servers(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps({"mcpServers": {"other-tool": {"command": "other"}}}),
            encoding="utf-8",
        )

        from synapps.onboarding.mcp_configurator import write_mcp_config

        write_mcp_config(config_path, servers_key="mcpServers")

        data = json.loads(config_path.read_text())
        assert "other-tool" in data["mcpServers"]
        assert "synapps" in data["mcpServers"]

    def test_write_uses_servers_key_for_vscode(self, tmp_path: Path) -> None:
        config_path = tmp_path / "mcp.json"

        from synapps.onboarding.mcp_configurator import write_mcp_config

        write_mcp_config(config_path, servers_key="servers")

        data = json.loads(config_path.read_text())
        assert "servers" in data
        assert "synapps" in data["servers"]

    def test_write_atomic_uses_os_replace(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.json"
        replace_calls: list[tuple[str, str]] = []

        original_replace = os.replace

        def tracking_replace(src: str, dst: str) -> None:
            replace_calls.append((src, dst))
            original_replace(src, dst)

        from synapps.onboarding.mcp_configurator import write_mcp_config

        with patch("synapps.onboarding.mcp_configurator.os.replace", side_effect=tracking_replace):
            write_mcp_config(config_path, servers_key="mcpServers")

        assert len(replace_calls) == 1
        assert replace_calls[0][1] == str(config_path)

    def test_write_backs_up_corrupt_json(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.json"
        config_path.write_text("this is not valid json!!!", encoding="utf-8")

        from synapps.onboarding.mcp_configurator import write_mcp_config

        write_mcp_config(config_path, servers_key="mcpServers")

        backup_path = config_path.with_suffix(".json.bak")
        assert backup_path.exists()
        assert backup_path.read_text(encoding="utf-8") == "this is not valid json!!!"

        data = json.loads(config_path.read_text())
        assert "synapps" in data["mcpServers"]

    def test_write_creates_parent_dirs(self, tmp_path: Path) -> None:
        config_path = tmp_path / "subdir" / "config.json"
        assert not config_path.parent.exists()

        from synapps.onboarding.mcp_configurator import write_mcp_config

        write_mcp_config(config_path, servers_key="mcpServers")

        assert config_path.exists()
        data = json.loads(config_path.read_text())
        assert "synapps" in data["mcpServers"]
