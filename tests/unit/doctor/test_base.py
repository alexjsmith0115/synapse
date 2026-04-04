from __future__ import annotations

import dataclasses
import pytest

from synapps.doctor.base import CheckResult, DoctorCheck


def test_checkresult_is_frozen() -> None:
    result = CheckResult(name="x", status="pass", detail="ok", fix=None, group="infra")
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.name = "y"  # type: ignore[misc]


def test_checkresult_fix_can_be_string() -> None:
    result = CheckResult(name="x", status="pass", detail="ok", fix="install foo", group="infra")
    assert result.fix == "install foo"


def test_doctor_check_is_runtime_checkable() -> None:
    class _PassCheck:
        def run(self) -> CheckResult:
            return CheckResult(name="t", status="pass", detail="ok", fix=None, group="x")

    assert isinstance(_PassCheck(), DoctorCheck) is True


def test_incomplete_object_fails_protocol_check() -> None:
    class NoRunMethod:
        pass

    assert isinstance(NoRunMethod(), DoctorCheck) is False
