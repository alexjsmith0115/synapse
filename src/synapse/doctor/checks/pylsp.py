from __future__ import annotations

import logging
import shutil
import subprocess

from synapse.doctor.base import CheckResult

log = logging.getLogger(__name__)

_FIX = "Install: `pip install python-lsp-server`"


class PylspCheck:
    group = "python"

    def run(self) -> CheckResult:
        # Skip-if-runtime-absent: pylsp is only meaningful when python3 exists
        if shutil.which("python3") is None:
            return CheckResult(
                name="pylsp",
                status="warn",
                detail="python3 not available — cannot check pylsp",
                fix=None,
                group=self.group,
            )
        path = shutil.which("pylsp")
        if path is None:
            return CheckResult(
                name="pylsp",
                status="fail",
                detail="pylsp not found on PATH",
                fix=_FIX,
                group=self.group,
            )
        try:
            result = subprocess.run(
                ["pylsp", "--version"],
                capture_output=True,
                timeout=10,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            return CheckResult(
                name="pylsp",
                status="fail",
                detail=f"pylsp invocation failed: {exc}",
                fix=_FIX,
                group=self.group,
            )
        if result.returncode != 0:
            return CheckResult(
                name="pylsp",
                status="fail",
                detail=f"pylsp exited with code {result.returncode}",
                fix=_FIX,
                group=self.group,
            )
        return CheckResult(
            name="pylsp",
            status="pass",
            detail=f"Found at {path}",
            fix=None,
            group=self.group,
        )
