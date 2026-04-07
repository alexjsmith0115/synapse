from __future__ import annotations

from synapps.doctor.base import CheckResult
from synapps.util.java import check_java_version


class JavaCheck:
    group = "java"

    def run(self) -> CheckResult:
        ok, version, message = check_java_version(minimum=17)
        if ok:
            return CheckResult(
                name="Java",
                status="pass",
                detail=message,
                fix=None,
                group=self.group,
            )
        return CheckResult(
            name="Java",
            status="fail",
            detail=message.split("\n")[0],
            fix=message,
            group=self.group,
        )
