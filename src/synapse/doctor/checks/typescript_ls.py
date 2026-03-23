from __future__ import annotations

import shutil
import subprocess

from synapse.doctor.base import CheckResult

_FIX = "Install: `npm install -g typescript-language-server typescript`"


class TypeScriptLSCheck:
    group = "typescript"

    def run(self) -> CheckResult:
        # Skip-if-runtime-absent: node must be present for typescript-language-server to work
        if shutil.which("node") is None:
            return CheckResult(
                name="typescript-language-server",
                status="warn",
                detail="node not available — cannot check typescript-language-server",
                fix=None,
                group=self.group,
            )
        path = shutil.which("typescript-language-server")
        if path is None:
            return CheckResult(
                name="typescript-language-server",
                status="fail",
                detail="typescript-language-server not found on PATH",
                fix=_FIX,
                group=self.group,
            )
        try:
            result = subprocess.run(
                ["typescript-language-server", "--version"],
                capture_output=True,
                timeout=10,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            return CheckResult(
                name="typescript-language-server",
                status="fail",
                detail=f"typescript-language-server invocation failed: {exc}",
                fix=_FIX,
                group=self.group,
            )
        if result.returncode != 0:
            return CheckResult(
                name="typescript-language-server",
                status="fail",
                detail=f"typescript-language-server exited with code {result.returncode}",
                fix=_FIX,
                group=self.group,
            )
        return CheckResult(
            name="typescript-language-server",
            status="pass",
            detail=f"Found at {path}",
            fix=None,
            group=self.group,
        )
