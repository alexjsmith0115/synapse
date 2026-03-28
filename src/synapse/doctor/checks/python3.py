from __future__ import annotations

import logging
import platform
import shutil
import subprocess

from synapse.doctor.base import CheckResult

log = logging.getLogger(__name__)


def _fix() -> str:
    if platform.system() == "Darwin":
        return "Install Python 3: brew install python3\nOr download: https://python.org/downloads/"
    return "Install Python 3: sudo apt-get install python3\nOr download: https://python.org/downloads/"


class PythonCheck:
    group = "python"

    def run(self) -> CheckResult:
        path = shutil.which("python3")
        if path is None:
            return CheckResult(
                name="Python 3",
                status="fail",
                detail="python3 not found on PATH",
                fix=_fix(),
                group=self.group,
            )
        try:
            result = subprocess.run(
                ["python3", "--version"],
                capture_output=True,
                timeout=10,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            return CheckResult(
                name="Python 3",
                status="fail",
                detail=f"python3 invocation failed: {exc}",
                fix=_fix(),
                group=self.group,
            )
        if result.returncode != 0:
            return CheckResult(
                name="Python 3",
                status="fail",
                detail=f"python3 exited with code {result.returncode}",
                fix=_fix(),
                group=self.group,
            )
        return CheckResult(
            name="Python 3",
            status="pass",
            detail=f"Found at {path}",
            fix=None,
            group=self.group,
        )
