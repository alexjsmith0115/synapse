from __future__ import annotations

import platform
import re
import shutil
import subprocess

from synapse.doctor.base import CheckResult


def _fix() -> str:
    if platform.system() == "Darwin":
        return "Install .NET SDK: brew install dotnet\nOr download: https://dotnet.microsoft.com/download"
    return "Install .NET SDK: sudo apt-get install dotnet-sdk-9.0\nOr download: https://dotnet.microsoft.com/download"


class DotNetCheck:
    group = "csharp"

    def run(self) -> CheckResult:
        path = shutil.which("dotnet")
        if path is None:
            return CheckResult(
                name=".NET SDK",
                status="fail",
                detail="dotnet not found on PATH",
                fix=_fix(),
                group=self.group,
            )
        try:
            result = subprocess.run(
                ["dotnet", "--list-runtimes"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            return CheckResult(
                name=".NET SDK",
                status="fail",
                detail=f"dotnet invocation failed: {exc}",
                fix=_fix(),
                group=self.group,
            )
        if result.returncode == 0 and re.search(r"Microsoft\.NETCore\.App", result.stdout):
            return CheckResult(
                name=".NET SDK",
                status="pass",
                detail=f"Found at {path}",
                fix=None,
                group=self.group,
            )
        return CheckResult(
            name=".NET SDK",
            status="fail",
            detail="dotnet runtime not installed (no Microsoft.NETCore.App in --list-runtimes)",
            fix=_fix(),
            group=self.group,
        )
