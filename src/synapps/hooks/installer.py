"""Write and remove hook scripts at ~/.synapps/hooks/."""
from __future__ import annotations

import logging
import shutil
import stat
from pathlib import Path

from synapps.hooks.scripts import (
    CLAUDE_GATE_SH,
    COMMON_SH,
    COPILOT_GATE_SH,
    CURSOR_GATE_SH,
)

log = logging.getLogger(__name__)

_SCRIPTS: dict[str, str] = {
    "common.sh": COMMON_SH,
    "claude-gate.sh": CLAUDE_GATE_SH,
    "cursor-gate.sh": CURSOR_GATE_SH,
    "copilot-gate.sh": COPILOT_GATE_SH,
}


def install_scripts(hooks_dir: Path, *, force: bool = True) -> list[Path]:
    """Write gate scripts to *hooks_dir* and make them executable.

    Returns the list of paths that were actually written.
    """
    hooks_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, content in _SCRIPTS.items():
        dest = hooks_dir / name
        if dest.exists() and not force:
            log.debug("Skipping existing %s (use --force to overwrite)", dest)
            continue
        dest.write_text(content, encoding="utf-8")
        dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        written.append(dest)
    return written


def remove_scripts(hooks_dir: Path) -> None:
    """Delete the hooks directory and all scripts inside it."""
    if hooks_dir.is_dir():
        shutil.rmtree(hooks_dir)
        log.info("Removed %s", hooks_dir)
