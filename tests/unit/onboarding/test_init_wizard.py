from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest
import typer

from synapse.onboarding.mcp_configurator import MCPClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_check_result(name: str, status: str = "pass", fix: str | None = None, group: str = "core"):
    from synapse.doctor.base import CheckResult
    return CheckResult(name=name, status=status, detail="detail", fix=fix, group=group)


def _make_report(results):
    from synapse.doctor.service import DoctorReport
    return DoctorReport(checks=results)


# ---------------------------------------------------------------------------
# _checks_for_languages
# ---------------------------------------------------------------------------

def test_checks_for_languages_python_only():
    from synapse.onboarding.init_wizard import _checks_for_languages
    from synapse.doctor.checks.docker_daemon import DockerDaemonCheck
    from synapse.doctor.checks.memgraph_bolt import MemgraphBoltCheck
    from synapse.doctor.checks.python3 import PythonCheck
    from synapse.doctor.checks.pylsp import PylspCheck
    from synapse.doctor.checks.dotnet import DotNetCheck
    from synapse.doctor.checks.node import NodeCheck
    from synapse.doctor.checks.java import JavaCheck

    checks = _checks_for_languages(["python"])

    check_types = [type(c) for c in checks]
    assert DockerDaemonCheck in check_types
    assert MemgraphBoltCheck in check_types
    assert PythonCheck in check_types
    assert PylspCheck in check_types
    assert DotNetCheck not in check_types
    assert NodeCheck not in check_types
    assert JavaCheck not in check_types


def test_checks_for_languages_includes_core():
    from synapse.onboarding.init_wizard import _checks_for_languages
    from synapse.doctor.checks.docker_daemon import DockerDaemonCheck
    from synapse.doctor.checks.memgraph_bolt import MemgraphBoltCheck

    checks = _checks_for_languages([])

    check_types = [type(c) for c in checks]
    assert DockerDaemonCheck in check_types
    assert MemgraphBoltCheck in check_types


def test_checks_for_languages_multi():
    from synapse.onboarding.init_wizard import _checks_for_languages
    from synapse.doctor.checks.docker_daemon import DockerDaemonCheck
    from synapse.doctor.checks.memgraph_bolt import MemgraphBoltCheck
    from synapse.doctor.checks.python3 import PythonCheck
    from synapse.doctor.checks.pylsp import PylspCheck
    from synapse.doctor.checks.node import NodeCheck
    from synapse.doctor.checks.typescript_ls import TypeScriptLSCheck
    from synapse.doctor.checks.dotnet import DotNetCheck
    from synapse.doctor.checks.java import JavaCheck

    checks = _checks_for_languages(["python", "typescript"])

    check_types = [type(c) for c in checks]
    assert DockerDaemonCheck in check_types
    assert MemgraphBoltCheck in check_types
    assert PythonCheck in check_types
    assert PylspCheck in check_types
    assert NodeCheck in check_types
    assert TypeScriptLSCheck in check_types
    assert DotNetCheck not in check_types
    assert JavaCheck not in check_types


# ---------------------------------------------------------------------------
# run_init — various flows
# ---------------------------------------------------------------------------

def _common_patches(
    *,
    languages=None,
    mcp_clients=None,
    doctor_report=None,
    confirm_side_effect=None,
    isatty=True,
    smart_index_result="full-index",
):
    """Build a dict of all patches needed for run_init tests."""
    if languages is None:
        languages = [("python", 10)]
    if mcp_clients is None:
        mcp_clients = []
    if doctor_report is None:
        doctor_report = _make_report([_make_check_result("Docker daemon", "pass")])
    if confirm_side_effect is None:
        confirm_side_effect = [True]  # default: confirm everything

    return {
        "detect_languages": languages,
        "detect_mcp_clients": mcp_clients,
        "write_mcp_config": None,
        "doctor_report": doctor_report,
        "confirm_side_effect": confirm_side_effect,
        "isatty": isatty,
        "smart_index_result": smart_index_result,
    }


def _run_with_patches(project_path: str, opts: dict):
    mock_doctor_service = MagicMock()
    mock_doctor_service.return_value.run.return_value = opts["doctor_report"]

    mock_conn = MagicMock()
    mock_cm = MagicMock()
    mock_cm.return_value.get_connection.return_value = mock_conn

    mock_svc = MagicMock()
    mock_svc.return_value.smart_index.return_value = opts["smart_index_result"]

    with (
        patch("synapse.onboarding.init_wizard.detect_languages", return_value=opts["detect_languages"]),
        patch("synapse.onboarding.init_wizard.detect_mcp_clients", return_value=opts["detect_mcp_clients"]),
        patch("synapse.onboarding.init_wizard.write_mcp_config") as mock_write,
        patch("synapse.onboarding.init_wizard.DoctorService", mock_doctor_service),
        patch("synapse.onboarding.init_wizard.ConnectionManager", mock_cm),
        patch("synapse.onboarding.init_wizard.ensure_schema"),
        patch("synapse.onboarding.init_wizard.SynapseService", mock_svc),
        patch("typer.confirm", side_effect=opts["confirm_side_effect"]),
        patch("sys.stdin") as mock_stdin,
    ):
        mock_stdin.isatty.return_value = opts["isatty"]

        from synapse.onboarding.init_wizard import run_init
        run_init(project_path)

    return mock_write, mock_svc, mock_cm


def test_wizard_calls_smart_index():
    opts = _common_patches(confirm_side_effect=[True, True, True, True])
    _, mock_svc, _ = _run_with_patches("/tmp/myproject", opts)
    mock_svc.return_value.smart_index.assert_called_once()
    call_args = mock_svc.return_value.smart_index.call_args
    assert "/tmp/myproject" in call_args[0] or "/tmp/myproject" in str(call_args)


def test_wizard_shows_fix_on_failure(capsys):
    from rich.console import Console

    fix_text = "brew install dotnet"
    failed_result = _make_check_result("DotNet", status="fail", fix=fix_text, group="csharp")
    report = _make_report([failed_result])

    # confirm_side_effect: [language confirm, continue-with-failures, mcp confirm (none)]
    opts = _common_patches(
        doctor_report=report,
        confirm_side_effect=[True, True],
    )

    mock_doctor_service = MagicMock()
    mock_doctor_service.return_value.run.return_value = report

    mock_conn = MagicMock()
    mock_cm = MagicMock()
    mock_cm.return_value.get_connection.return_value = mock_conn
    mock_svc = MagicMock()
    mock_svc.return_value.smart_index.return_value = "full-index"

    output_lines = []

    def capture_print(*args, **kwargs):
        output_lines.append(str(args))

    with (
        patch("synapse.onboarding.init_wizard.detect_languages", return_value=[("python", 10)]),
        patch("synapse.onboarding.init_wizard.detect_mcp_clients", return_value=[]),
        patch("synapse.onboarding.init_wizard.write_mcp_config"),
        patch("synapse.onboarding.init_wizard.DoctorService", mock_doctor_service),
        patch("synapse.onboarding.init_wizard.ConnectionManager", mock_cm),
        patch("synapse.onboarding.init_wizard.ensure_schema"),
        patch("synapse.onboarding.init_wizard.SynapseService", mock_svc),
        patch("typer.confirm", side_effect=[True, True]),
        patch("sys.stdin") as mock_stdin,
        patch("rich.console.Console.print", side_effect=capture_print) as mock_console_print,
    ):
        mock_stdin.isatty.return_value = True
        from synapse.onboarding.init_wizard import run_init
        run_init("/tmp/myproject")

    all_output = " ".join(output_lines)
    assert fix_text in all_output


def test_wizard_offers_mcp_config():
    client = MCPClient("Claude Code", Path("/tmp/.config/mcp.json"), "mcpServers")
    opts = _common_patches(
        mcp_clients=[client],
        confirm_side_effect=[True, True],  # language confirm, mcp confirm
    )
    mock_write, _, _ = _run_with_patches("/tmp/myproject", opts)
    mock_write.assert_called_once()


def test_wizard_skips_mcp_when_declined():
    client = MCPClient("Claude Code", Path("/tmp/.config/mcp.json"), "mcpServers")
    opts = _common_patches(
        mcp_clients=[client],
        confirm_side_effect=[True, False],  # language confirm, decline mcp
    )
    mock_write, _, _ = _run_with_patches("/tmp/myproject", opts)
    mock_write.assert_not_called()


def test_summary_printed():
    opts = _common_patches(confirm_side_effect=[True, True, True, True])

    mock_doctor_service = MagicMock()
    mock_doctor_service.return_value.run.return_value = _make_report(
        [_make_check_result("Docker daemon", "pass")]
    )
    mock_conn = MagicMock()
    mock_cm = MagicMock()
    mock_cm.return_value.get_connection.return_value = mock_conn
    mock_svc = MagicMock()
    mock_svc.return_value.smart_index.return_value = "full-index"

    printed_output = []

    def capture(*args, **kwargs):
        printed_output.append(str(args))

    with (
        patch("synapse.onboarding.init_wizard.detect_languages", return_value=[("python", 42)]),
        patch("synapse.onboarding.init_wizard.detect_mcp_clients", return_value=[]),
        patch("synapse.onboarding.init_wizard.write_mcp_config"),
        patch("synapse.onboarding.init_wizard.DoctorService", mock_doctor_service),
        patch("synapse.onboarding.init_wizard.ConnectionManager", mock_cm),
        patch("synapse.onboarding.init_wizard.ensure_schema"),
        patch("synapse.onboarding.init_wizard.SynapseService", mock_svc),
        patch("typer.confirm", return_value=True),
        patch("sys.stdin") as mock_stdin,
        patch("rich.console.Console.print", side_effect=capture),
    ):
        mock_stdin.isatty.return_value = True
        from synapse.onboarding.init_wizard import run_init
        run_init("/tmp/myproject")

    all_output = " ".join(printed_output)
    assert "python" in all_output.lower()


def test_non_interactive_stdin():
    with (
        patch("sys.stdin") as mock_stdin,
        patch("synapse.onboarding.init_wizard.detect_languages", return_value=[("python", 10)]),
    ):
        mock_stdin.isatty.return_value = False
        from synapse.onboarding.init_wizard import run_init
        with pytest.raises((typer.Exit, SystemExit)) as exc_info:
            run_init("/tmp/myproject")
        # Should exit with code 1
        exc = exc_info.value
        if isinstance(exc, typer.Exit):
            assert exc.exit_code == 1
        else:
            assert exc.code == 1
