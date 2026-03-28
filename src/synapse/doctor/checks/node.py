from __future__ import annotations

import platform
import shutil
import subprocess

from synapse.doctor.base import CheckResult


def _fix() -> str:
    if platform.system() == "Darwin":
        return "Install Node.js: brew install node\nOr download: https://nodejs.org/"
    return "Install Node.js: sudo apt-get install nodejs\nOr download: https://nodejs.org/"


class NodeCheck:
    group = "typescript"

    def run(self) -> CheckResult:
        path = shutil.which("node")
        if path is None:
            return CheckResult(
                name="Node.js",
                status="fail",
                detail="node not found on PATH",
                fix=_fix(),
                group=self.group,
            )
        try:
            result = subprocess.run(["node", "--version"], capture_output=True, timeout=10)
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            return CheckResult(
                name="Node.js",
                status="fail",
                detail=f"node invocation failed: {exc}",
                fix=_fix(),
                group=self.group,
            )
        if result.returncode != 0:
            return CheckResult(
                name="Node.js",
                status="fail",
                detail=f"node exited with code {result.returncode}",
                fix=_fix(),
                group=self.group,
            )
        return CheckResult(
            name="Node.js",
            status="pass",
            detail=f"Found at {path}",
            fix=None,
            group=self.group,
        )
