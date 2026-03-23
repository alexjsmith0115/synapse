from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from synapse.cli.app import app
from synapse.doctor.base import CheckResult

runner = CliRunner()


def _pass_result(name: str = "Docker daemon", group: str = "core") -> CheckResult:
    return CheckResult(name=name, status="pass", detail="ok", fix=None, group=group)


def _fail_result(name: str = "Docker daemon", fix: str = "fix me", group: str = "core") -> CheckResult:
    return CheckResult(name=name, status="fail", detail="broken", fix=fix, group=group)


def _warn_result(name: str = "Memgraph", group: str = "core") -> CheckResult:
    return CheckResult(name=name, status="warn", detail="degraded", fix=None, group=group)


_ALL_CHECKS = [
    ("DockerDaemonCheck", "Docker daemon", "core"),
    ("MemgraphBoltCheck", "Memgraph", "core"),
    ("DotNetCheck", ".NET SDK", "csharp"),
    ("CSharpLSCheck", "csharp-ls", "csharp"),
    ("NodeCheck", "Node.js", "typescript"),
    ("TypeScriptLSCheck", "typescript-language-server", "typescript"),
    ("PythonCheck", "Python 3", "python"),
    ("PylspCheck", "pylsp", "python"),
    ("JavaCheck", "Java", "java"),
    ("JdtlsCheck", "Eclipse JDT LS", "java"),
]


class _AllChecksPassingContext:
    """Context manager that patches all 10 doctor checks with pass results."""

    def __enter__(self) -> None:
        self._stack = ExitStack()
        self._stack.__enter__()
        patches = [patch(f"synapse.cli.app.{cls}") for cls, _, _ in _ALL_CHECKS]
        mocks = [self._stack.enter_context(p) for p in patches]
        for mock, (_, name, group) in zip(mocks, _ALL_CHECKS):
            mock.return_value.run.return_value = _pass_result(name, group)

    def __exit__(self, *args: object) -> None:
        self._stack.__exit__(*args)


def _all_checks_passing() -> _AllChecksPassingContext:
    return _AllChecksPassingContext()


def test_doctor_exits_0_when_all_pass() -> None:
    with _all_checks_passing():
        result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0


def test_doctor_exits_1_when_docker_fails() -> None:
    patches = [patch(f"synapse.cli.app.{cls}") for cls, _, _ in _ALL_CHECKS]
    with ExitStack() as stack:
        mocks = [stack.enter_context(p) for p in patches]
        for mock, (_, name, group) in zip(mocks, _ALL_CHECKS):
            mock.return_value.run.return_value = _pass_result(name, group)
        # Override Docker check to fail
        mocks[0].return_value.run.return_value = _fail_result("Docker daemon")
        result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 1


def test_doctor_exits_0_when_warn_only() -> None:
    # warn is not failure — degraded-but-working semantics per Phase 1 decision
    patches = [patch(f"synapse.cli.app.{cls}") for cls, _, _ in _ALL_CHECKS]
    with ExitStack() as stack:
        mocks = [stack.enter_context(p) for p in patches]
        for mock, (_, name, group) in zip(mocks, _ALL_CHECKS):
            mock.return_value.run.return_value = _warn_result(name, group)
        result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0


def test_doctor_output_contains_check_name() -> None:
    with _all_checks_passing():
        result = runner.invoke(app, ["doctor"])
    assert "Docker daemon" in result.output


def test_doctor_output_contains_pass_status() -> None:
    with _all_checks_passing():
        result = runner.invoke(app, ["doctor"])
    assert "pass" in result.output


def test_doctor_output_contains_fail_status() -> None:
    patches = [patch(f"synapse.cli.app.{cls}") for cls, _, _ in _ALL_CHECKS]
    with ExitStack() as stack:
        mocks = [stack.enter_context(p) for p in patches]
        for mock, (_, name, group) in zip(mocks, _ALL_CHECKS):
            mock.return_value.run.return_value = _pass_result(name, group)
        mocks[0].return_value.run.return_value = _fail_result("Docker daemon")
        result = runner.invoke(app, ["doctor"])
    assert "fail" in result.output


def test_doctor_output_contains_fix_for_failing_check() -> None:
    patches = [patch(f"synapse.cli.app.{cls}") for cls, _, _ in _ALL_CHECKS]
    with ExitStack() as stack:
        mocks = [stack.enter_context(p) for p in patches]
        for mock, (_, name, group) in zip(mocks, _ALL_CHECKS):
            mock.return_value.run.return_value = _pass_result(name, group)
        mocks[0].return_value.run.return_value = _fail_result("Docker daemon", fix="run docker start")
        result = runner.invoke(app, ["doctor"])
    assert "run docker start" in result.output


def test_doctor_output_no_fix_for_passing_check() -> None:
    # D-03: passing checks show no fix text
    with _all_checks_passing():
        result = runner.invoke(app, ["doctor"])
    assert "Fix" not in result.output


def test_doctor_output_contains_group_header() -> None:
    with _all_checks_passing():
        result = runner.invoke(app, ["doctor"])
    assert "core" in result.output


def test_doctor_output_contains_summary_line() -> None:
    with _all_checks_passing():
        result = runner.invoke(app, ["doctor"])
    assert any(word in result.output for word in ("passed", "failed", "warning"))


def test_doctor_runs_all_ten_checks() -> None:
    with _all_checks_passing():
        result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    for name in [".NET SDK", "csharp-ls", "Node.js", "typescript-language-server",
                 "Python 3", "pylsp", "Java", "Eclipse JDT LS"]:
        assert name in result.output, f"Expected '{name}' in doctor output"
