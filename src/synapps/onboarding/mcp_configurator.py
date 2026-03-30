from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from mcp_config_path.main import get_config_path

log = logging.getLogger(__name__)

_SYNAPPS_ENTRY = {"command": "synapps-mcp", "args": []}

# (display_name, mcp-config-path key, servers JSON key, needs_project_path)
_CLIENT_DEFS: list[tuple[str, str, str, bool]] = [
    ("Claude Desktop", "claude_desktop", "mcpServers", False),
    ("Claude Code", "claude_code", "mcpServers", True),
    ("Cursor", "cursor", "mcpServers", True),
    ("VS Code / Copilot", "vscode", "servers", True),
]


@dataclass(frozen=True)
class MCPClient:
    name: str
    config_path: Path
    servers_key: str


def detect_mcp_clients(project_path: str) -> list[MCPClient]:
    """Return MCP clients whose application directory exists on this machine."""
    clients: list[MCPClient] = []
    for display_name, lib_key, servers_key, needs_path in _CLIENT_DEFS:
        kwargs: dict[str, str] = {"path": project_path} if needs_path else {}
        config_path = Path(get_config_path(lib_key, **kwargs))
        if config_path.parent.exists():
            clients.append(MCPClient(
                name=display_name,
                config_path=config_path,
                servers_key=servers_key,
            ))
    return clients


def write_mcp_config(config_path: Path, servers_key: str = "mcpServers") -> None:
    """Merge synapps entry into an MCP client config file. Atomic write."""
    existing: dict = {}
    if config_path.exists():
        raw = config_path.read_text(encoding="utf-8")
        try:
            existing = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            backup = config_path.with_suffix(".json.bak")
            log.warning("Corrupt config at %s — backing up to %s", config_path, backup)
            config_path.rename(backup)

    existing.setdefault(servers_key, {})["synapps"] = _SYNAPPS_ENTRY

    config_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", dir=str(config_path.parent), delete=False, suffix=".tmp",
    ) as tmp:
        json.dump(existing, tmp, indent=2)
        tmp.flush()
        tmp_name = tmp.name
    os.replace(tmp_name, str(config_path))
