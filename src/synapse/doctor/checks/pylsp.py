from __future__ import annotations

import sys
import subprocess

from synapse.doctor.base import CheckResult

_FIX = "Install pyright: `pip install pyright` (or ensure it is in your project's dependencies)"


class PylspCheck:
    """Checks for pyright — the Python language server used by Synapse."""

    group = "python"

    def run(self) -> CheckResult:
        # Use sys.executable to check in the same venv Synapse is running in
        # (matching how pyright_server.py launches pyright via sys.executable)
        try:
            result = subprocess.run(
                [sys.executable, "-c", "import pyright; print(pyright.__file__)"],
                capture_output=True,
                timeout=10,
                text=True,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            return CheckResult(
                name="pyright",
                status="fail",
                detail=f"pyright check failed: {exc}",
                fix=_FIX,
                group=self.group,
            )
        if result.returncode != 0:
            return CheckResult(
                name="pyright",
                status="fail",
                detail="pyright module not found",
                fix=_FIX,
                group=self.group,
            )
        path = result.stdout.strip()
        return CheckResult(
            name="pyright",
            status="pass",
            detail=f"Found at {path}",
            fix=None,
            group=self.group,
        )
