from __future__ import annotations

import pytest

from synapps.doctor.base import CheckResult, DoctorCheck
from synapps.doctor.service import DoctorService


class _PassCheck:
    def run(self) -> CheckResult:
        return CheckResult(name="stub-pass", status="pass", detail="ok", fix=None, group="core")


class _FailCheck:
    def run(self) -> CheckResult:
        return CheckResult(name="stub-fail", status="fail", detail="missing", fix="install X", group="core")


class _WarnCheck:
    def run(self) -> CheckResult:
        return CheckResult(name="stub-warn", status="warn", detail="degraded", fix=None, group="core")


class _ExplodingCheck:
    def run(self) -> CheckResult:
        raise RuntimeError("boom")


def test_service_returns_all_results() -> None:
    report = DoctorService([_PassCheck(), _FailCheck()]).run()
    assert len(report.checks) == 2


def test_service_absorbs_exception() -> None:
    report = DoctorService([_ExplodingCheck()]).run()
    assert len(report.checks) == 1
    assert report.checks[0].status == "fail"


def test_service_absorbed_exception_detail_contains_message() -> None:
    report = DoctorService([_ExplodingCheck()]).run()
    assert report.checks[0].detail == "boom"


def test_has_failures_true_on_fail() -> None:
    report = DoctorService([_FailCheck()]).run()
    assert report.has_failures is True


def test_has_failures_false_on_pass_only() -> None:
    report = DoctorService([_PassCheck()]).run()
    assert report.has_failures is False


def test_has_failures_false_on_warn_only() -> None:
    report = DoctorService([_WarnCheck()]).run()
    assert report.has_failures is False


def test_empty_service_returns_empty_report() -> None:
    report = DoctorService([]).run()
    assert report.checks == []
    assert report.has_failures is False
