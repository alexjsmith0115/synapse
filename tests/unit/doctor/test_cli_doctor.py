from __future__ import annotations

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


def test_doctor_exits_0_when_all_pass() -> None:
    with patch("synapse.cli.app.DockerDaemonCheck") as mock_docker, patch("synapse.cli.app.MemgraphBoltCheck") as mock_mg:
        mock_docker.return_value.run.return_value = _pass_result("Docker daemon")
        mock_mg.return_value.run.return_value = _pass_result("Memgraph")
        result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0


def test_doctor_exits_1_when_docker_fails() -> None:
    with patch("synapse.cli.app.DockerDaemonCheck") as mock_docker, patch("synapse.cli.app.MemgraphBoltCheck") as mock_mg:
        mock_docker.return_value.run.return_value = _fail_result("Docker daemon")
        mock_mg.return_value.run.return_value = _pass_result("Memgraph")
        result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 1


def test_doctor_exits_0_when_warn_only() -> None:
    # warn is not failure — degraded-but-working semantics per Phase 1 decision
    with patch("synapse.cli.app.DockerDaemonCheck") as mock_docker, patch("synapse.cli.app.MemgraphBoltCheck") as mock_mg:
        mock_docker.return_value.run.return_value = _warn_result("Docker daemon")
        mock_mg.return_value.run.return_value = _warn_result("Memgraph")
        result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0


def test_doctor_output_contains_check_name() -> None:
    with patch("synapse.cli.app.DockerDaemonCheck") as mock_docker, patch("synapse.cli.app.MemgraphBoltCheck") as mock_mg:
        mock_docker.return_value.run.return_value = _pass_result("Docker daemon")
        mock_mg.return_value.run.return_value = _pass_result("Memgraph")
        result = runner.invoke(app, ["doctor"])
    assert "Docker daemon" in result.output


def test_doctor_output_contains_pass_status() -> None:
    with patch("synapse.cli.app.DockerDaemonCheck") as mock_docker, patch("synapse.cli.app.MemgraphBoltCheck") as mock_mg:
        mock_docker.return_value.run.return_value = _pass_result("Docker daemon")
        mock_mg.return_value.run.return_value = _pass_result("Memgraph")
        result = runner.invoke(app, ["doctor"])
    assert "pass" in result.output


def test_doctor_output_contains_fail_status() -> None:
    with patch("synapse.cli.app.DockerDaemonCheck") as mock_docker, patch("synapse.cli.app.MemgraphBoltCheck") as mock_mg:
        mock_docker.return_value.run.return_value = _fail_result("Docker daemon")
        mock_mg.return_value.run.return_value = _pass_result("Memgraph")
        result = runner.invoke(app, ["doctor"])
    assert "fail" in result.output


def test_doctor_output_contains_fix_for_failing_check() -> None:
    with patch("synapse.cli.app.DockerDaemonCheck") as mock_docker, patch("synapse.cli.app.MemgraphBoltCheck") as mock_mg:
        mock_docker.return_value.run.return_value = _fail_result("Docker daemon", fix="run docker start")
        mock_mg.return_value.run.return_value = _pass_result("Memgraph")
        result = runner.invoke(app, ["doctor"])
    assert "run docker start" in result.output


def test_doctor_output_no_fix_for_passing_check() -> None:
    # D-03: passing checks show no fix text
    with patch("synapse.cli.app.DockerDaemonCheck") as mock_docker, patch("synapse.cli.app.MemgraphBoltCheck") as mock_mg:
        mock_docker.return_value.run.return_value = _pass_result("Docker daemon")
        mock_mg.return_value.run.return_value = _pass_result("Memgraph")
        result = runner.invoke(app, ["doctor"])
    assert "Fix" not in result.output


def test_doctor_output_contains_group_header() -> None:
    with patch("synapse.cli.app.DockerDaemonCheck") as mock_docker, patch("synapse.cli.app.MemgraphBoltCheck") as mock_mg:
        mock_docker.return_value.run.return_value = _pass_result("Docker daemon", group="core")
        mock_mg.return_value.run.return_value = _pass_result("Memgraph", group="core")
        result = runner.invoke(app, ["doctor"])
    assert "core" in result.output


def test_doctor_output_contains_summary_line() -> None:
    with patch("synapse.cli.app.DockerDaemonCheck") as mock_docker, patch("synapse.cli.app.MemgraphBoltCheck") as mock_mg:
        mock_docker.return_value.run.return_value = _pass_result("Docker daemon")
        mock_mg.return_value.run.return_value = _pass_result("Memgraph")
        result = runner.invoke(app, ["doctor"])
    assert any(word in result.output for word in ("passed", "failed", "warning"))
