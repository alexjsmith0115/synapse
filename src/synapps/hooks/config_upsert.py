"""Per-agent config file read-modify-write logic for hook entries."""
from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

_SYNAPPS_MARKER = ".synapps/hooks/"


def _read_json(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            log.warning("Could not parse %s — treating as empty", path)
    return {}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", dir=str(path.parent), delete=False, suffix=".tmp",
    ) as tmp:
        json.dump(data, tmp, indent=2)
        tmp.flush()
        tmp_name = tmp.name
    os.replace(tmp_name, str(path))


def _is_synapps_entry(entry: dict) -> bool:
    """Check if a hook entry belongs to Synapps by inspecting command paths."""
    for value in _iter_string_values(entry):
        if _SYNAPPS_MARKER in value:
            return True
    return False


def _iter_string_values(obj: object) -> list[str]:
    """Recursively collect all string values from a JSON-like structure."""
    values: list[str] = []
    if isinstance(obj, str):
        values.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            values.extend(_iter_string_values(v))
    elif isinstance(obj, list):
        for item in obj:
            values.extend(_iter_string_values(item))
    return values


# ── Claude Code ──────────────────────────────────────────────────────


def upsert_claude_hook(config_path: Path, gate_script: str) -> None:
    """Add or replace the Synapps PreToolUse hook in Claude Code settings."""
    data = _read_json(config_path)
    hooks = data.setdefault("hooks", {})
    entries = hooks.setdefault("PreToolUse", [])

    hooks["PreToolUse"] = [e for e in entries if not _is_synapps_entry(e)]

    hooks["PreToolUse"].append({
        "matcher": "Grep|Glob",
        "hooks": [{"type": "command", "command": gate_script}],
    })
    _write_json(config_path, data)


def remove_claude_hook(config_path: Path) -> None:
    """Remove Synapps hook entries from Claude Code settings."""
    if not config_path.exists():
        return
    data = _read_json(config_path)
    entries = data.get("hooks", {}).get("PreToolUse", [])
    data.setdefault("hooks", {})["PreToolUse"] = [
        e for e in entries if not _is_synapps_entry(e)
    ]
    _write_json(config_path, data)


# ── Cursor ───────────────────────────────────────────────────────────


def upsert_cursor_hook(config_path: Path, gate_script: str) -> None:
    """Add or replace the Synapps preToolUse hook in Cursor config."""
    data = _read_json(config_path)
    data.setdefault("version", 1)
    hooks = data.setdefault("hooks", {})
    entries = hooks.setdefault("preToolUse", [])

    hooks["preToolUse"] = [e for e in entries if not _is_synapps_entry(e)]

    hooks["preToolUse"].append({
        "command": gate_script,
        "matcher": "Read",
    })
    _write_json(config_path, data)


def remove_cursor_hook(config_path: Path) -> None:
    """Remove Synapps hook entries from Cursor config."""
    if not config_path.exists():
        return
    data = _read_json(config_path)
    entries = data.get("hooks", {}).get("preToolUse", [])
    data.setdefault("hooks", {})["preToolUse"] = [
        e for e in entries if not _is_synapps_entry(e)
    ]
    _write_json(config_path, data)


# ── GitHub Copilot ───────────────────────────────────────────────────


def upsert_copilot_hook(config_path: Path, gate_script: str) -> None:
    """Add or replace the Synapps preToolUse hook in Copilot config."""
    data = _read_json(config_path)
    data.setdefault("version", 1)
    hooks = data.setdefault("hooks", {})
    entries = hooks.setdefault("preToolUse", [])

    hooks["preToolUse"] = [e for e in entries if not _is_synapps_entry(e)]

    hooks["preToolUse"].append({
        "type": "command",
        "bash": gate_script,
        "comment": "Synapps: prefer graph tools for code discovery",
    })
    _write_json(config_path, data)


def remove_copilot_hook(config_path: Path) -> None:
    """Remove Synapps hook entries from Copilot config."""
    if not config_path.exists():
        return
    data = _read_json(config_path)
    entries = data.get("hooks", {}).get("preToolUse", [])
    data.setdefault("hooks", {})["preToolUse"] = [
        e for e in entries if not _is_synapps_entry(e)
    ]
    _write_json(config_path, data)
