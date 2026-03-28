from __future__ import annotations

import glob
import os
import platform
import shutil
from pathlib import Path

from synapse.doctor.base import CheckResult


def _fix() -> str:
    if platform.system() == "Darwin":
        return "Install Eclipse JDT LS: brew install jdtls\nOr download: https://github.com/eclipse-jdtls/eclipse.jdt.ls"
    return (
        "Install Eclipse JDT LS:\n"
        "  1. Download from https://github.com/eclipse-jdtls/eclipse.jdt.ls\n"
        "  2. Extract to ~/.solidlsp/language_servers/static/EclipseJDTLS/jdtls/"
    )


class JdtlsCheck:
    group = "java"

    def run(self) -> CheckResult:
        # Skip if java runtime absent — JDT LS requires java to run
        if shutil.which("java") is None:
            return CheckResult(
                name="Eclipse JDT LS",
                status="warn",
                detail="java not available \u2014 cannot check Eclipse JDT LS",
                fix=None,
                group=self.group,
            )
        jar_path = _find_jdtls_launcher()
        if jar_path is None:
            return CheckResult(
                name="Eclipse JDT LS",
                status="fail",
                detail="Eclipse JDT LS not installed (equinox launcher jar not found)",
                fix=_fix(),
                group=self.group,
            )
        return CheckResult(
            name="Eclipse JDT LS",
            status="pass",
            detail=f"Found at {jar_path}",
            fix=None,
            group=self.group,
        )


def _find_jdtls_launcher() -> str | None:
    # Mirror path from eclipse_jdtls.py; use Path.home() for cross-platform correctness
    base = str(Path.home() / ".solidlsp" / "language_servers" / "static")
    jdtls_dir = os.path.join(base, "EclipseJDTLS", "jdtls")
    pattern = os.path.join(jdtls_dir, "plugins", "org.eclipse.equinox.launcher_*.jar")
    jars = glob.glob(pattern)
    return jars[0] if jars else None
