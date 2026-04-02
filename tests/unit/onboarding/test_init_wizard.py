from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import docker
import docker.errors
import pytest
import typer

from synapps.onboarding.mcp_configurator import MCPClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_check_result(name: str, status: str = "pass", fix: str | None = None, group: str = "core"):
    from synapps.doctor.base import CheckResult
    return CheckResult(name=name, status=status, detail="detail", fix=fix, group=group)


def _make_report(results):
    from synapps.doctor.service import DoctorReport
    return DoctorReport(checks=results)


# ---------------------------------------------------------------------------
# _checks_for_languages
# ---------------------------------------------------------------------------

def test_checks_for_languages_python_only():
    from synapps.onboarding.init_wizard import _checks_for_languages
    from synapps.doctor.checks.docker_daemon import DockerDaemonCheck
    from synapps.doctor.checks.memgraph_bolt import MemgraphBoltCheck
    from synapps.doctor.checks.python3 import PythonCheck
    from synapps.doctor.checks.pylsp import PylspCheck
    from synapps.doctor.checks.dotnet import DotNetCheck
    from synapps.doctor.checks.node import NodeCheck
    from synapps.doctor.checks.java import JavaCheck

    checks = _checks_for_languages(["python"])

    check_types = [type(c) for c in checks]
    # Docker and Memgraph are handled by run_init, not in language checks
    assert DockerDaemonCheck not in check_types
    assert MemgraphBoltCheck not in check_types
    assert PythonCheck in check_types
    assert PylspCheck in check_types
    assert DotNetCheck not in check_types
    assert NodeCheck not in check_types
    assert JavaCheck not in check_types


def test_checks_for_languages_empty_returns_nothing():
    from synapps.onboarding.init_wizard import _checks_for_languages

    checks = _checks_for_languages([])
    assert checks == []


def test_checks_for_languages_multi():
    from synapps.onboarding.init_wizard import _checks_for_languages
    from synapps.doctor.checks.docker_daemon import DockerDaemonCheck
    from synapps.doctor.checks.memgraph_bolt import MemgraphBoltCheck
    from synapps.doctor.checks.python3 import PythonCheck
    from synapps.doctor.checks.pylsp import PylspCheck
    from synapps.doctor.checks.node import NodeCheck
    from synapps.doctor.checks.typescript_ls import TypeScriptLSCheck
    from synapps.doctor.checks.dotnet import DotNetCheck
    from synapps.doctor.checks.java import JavaCheck

    checks = _checks_for_languages(["python", "typescript"])

    check_types = [type(c) for c in checks]
    assert DockerDaemonCheck not in check_types
    assert MemgraphBoltCheck not in check_types
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


def _run_with_patches(project_path: str, opts: dict, *, has_existing_db_config: bool = True):
    mock_doctor_service = MagicMock()
    mock_doctor_service.return_value.run.return_value = opts["doctor_report"]

    mock_conn = MagicMock()
    mock_cm = MagicMock()
    mock_cm.return_value.get_connection.return_value = mock_conn

    mock_svc = MagicMock()
    mock_svc.return_value.smart_index.return_value = opts["smart_index_result"]

    mock_docker_client = MagicMock()

    with (
        patch("synapps.onboarding.init_wizard.detect_languages", return_value=opts["detect_languages"]),
        patch("synapps.onboarding.init_wizard.detect_mcp_clients", return_value=opts["detect_mcp_clients"]),
        patch("synapps.onboarding.init_wizard.write_mcp_config") as mock_write,
        patch("synapps.onboarding.init_wizard.DoctorService", mock_doctor_service),
        patch("synapps.onboarding.init_wizard.ConnectionManager", mock_cm),
        patch("synapps.onboarding.init_wizard.ensure_schema"),
        patch("synapps.onboarding.init_wizard.SynappsService", mock_svc),
        patch("synapps.onboarding.init_wizard.docker") as mock_docker_mod,
        patch("synapps.onboarding.init_wizard._has_existing_db_config", return_value=has_existing_db_config),
        patch("synapps.onboarding.init_wizard._write_db_config"),
        patch("synapps.onboarding.init_wizard._configure_agents", return_value=([], [], [])),
        patch("typer.confirm", side_effect=opts["confirm_side_effect"]),
        patch("sys.stdin") as mock_stdin,
    ):
        mock_docker_mod.from_env.return_value = mock_docker_client
        mock_docker_mod.errors = docker.errors
        mock_stdin.isatty.return_value = opts["isatty"]

        from synapps.onboarding.init_wizard import run_init
        run_init(project_path)

    return mock_write, mock_svc, mock_cm


def test_wizard_calls_smart_index():
    opts = _common_patches(confirm_side_effect=[True, True, True, True, True])
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
        patch("synapps.onboarding.init_wizard.detect_languages", return_value=[("python", 10)]),
        patch("synapps.onboarding.init_wizard.detect_mcp_clients", return_value=[]),
        patch("synapps.onboarding.init_wizard.write_mcp_config"),
        patch("synapps.onboarding.init_wizard.DoctorService", mock_doctor_service),
        patch("synapps.onboarding.init_wizard.ConnectionManager", mock_cm),
        patch("synapps.onboarding.init_wizard.ensure_schema"),
        patch("synapps.onboarding.init_wizard.SynappsService", mock_svc),
        patch("synapps.onboarding.init_wizard.docker") as mock_docker_mod,
        patch("synapps.onboarding.init_wizard._has_existing_db_config", return_value=True),
        patch("synapps.onboarding.init_wizard._configure_agents", return_value=([], [], [])),
        patch("typer.confirm", side_effect=[True, True, True]),
        patch("sys.stdin") as mock_stdin,
        patch("rich.console.Console.print", side_effect=capture_print) as mock_console_print,
    ):
        mock_docker_mod.from_env.return_value = MagicMock()
        mock_docker_mod.errors = docker.errors
        mock_stdin.isatty.return_value = True
        from synapps.onboarding.init_wizard import run_init
        run_init("/tmp/myproject")

    all_output = " ".join(output_lines)
    assert fix_text in all_output


def test_wizard_offers_mcp_config(tmp_path):
    """_configure_agents calls write_mcp_config when MCP install is confirmed."""
    from synapps.hooks.detector import DetectedAgent

    claude_agent = DetectedAgent(name="claude", display_name="Claude Code", config_path=tmp_path / "s.json")
    client = MCPClient("Claude Code", Path("/tmp/.config/mcp.json"), "mcpServers")
    console = MagicMock()

    select_mocks = _mock_select_sequence(["__continue__"])
    with (
        patch("synapps.hooks.detector.detect_agents", return_value=[claude_agent]),
        patch("synapps.onboarding.init_wizard.detect_mcp_clients", return_value=[client]),
        patch("synapps.onboarding.init_wizard.write_mcp_config") as mock_write,
        patch("synapps.onboarding.agent_instructions.install_agent_instructions", return_value=[]),
        patch("InquirerPy.inquirer.select", side_effect=select_mocks),
        patch("typer.confirm", side_effect=[True, False, False]),
    ):
        from synapps.onboarding.init_wizard import _configure_agents
        _configure_agents(console, str(tmp_path))

    mock_write.assert_called_once()


def test_wizard_skips_mcp_when_declined(tmp_path):
    """_configure_agents does not call write_mcp_config when MCP install is declined."""
    from synapps.hooks.detector import DetectedAgent

    claude_agent = DetectedAgent(name="claude", display_name="Claude Code", config_path=tmp_path / "s.json")
    client = MCPClient("Claude Code", Path("/tmp/.config/mcp.json"), "mcpServers")
    console = MagicMock()

    select_mocks = _mock_select_sequence(["__continue__"])
    with (
        patch("synapps.hooks.detector.detect_agents", return_value=[claude_agent]),
        patch("synapps.onboarding.init_wizard.detect_mcp_clients", return_value=[client]),
        patch("synapps.onboarding.init_wizard.write_mcp_config") as mock_write,
        patch("synapps.onboarding.agent_instructions.install_agent_instructions", return_value=[]),
        patch("InquirerPy.inquirer.select", side_effect=select_mocks),
        patch("typer.confirm", side_effect=[False, False, False]),
    ):
        from synapps.onboarding.init_wizard import _configure_agents
        _configure_agents(console, str(tmp_path))

    mock_write.assert_not_called()


def test_summary_printed():
    opts = _common_patches(confirm_side_effect=[True, True, True, True, True])

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
        patch("synapps.onboarding.init_wizard.detect_languages", return_value=[("python", 42)]),
        patch("synapps.onboarding.init_wizard.detect_mcp_clients", return_value=[]),
        patch("synapps.onboarding.init_wizard.write_mcp_config"),
        patch("synapps.onboarding.init_wizard.DoctorService", mock_doctor_service),
        patch("synapps.onboarding.init_wizard.ConnectionManager", mock_cm),
        patch("synapps.onboarding.init_wizard.ensure_schema"),
        patch("synapps.onboarding.init_wizard.SynappsService", mock_svc),
        patch("synapps.onboarding.init_wizard.docker") as mock_docker_mod,
        patch("synapps.onboarding.init_wizard._has_existing_db_config", return_value=True),
        patch("synapps.onboarding.init_wizard._configure_agents", return_value=([], [], [])),
        patch("typer.confirm", return_value=True),
        patch("sys.stdin") as mock_stdin,
        patch("rich.console.Console.print", side_effect=capture),
    ):
        mock_docker_mod.from_env.return_value = MagicMock()
        mock_docker_mod.errors = docker.errors
        mock_stdin.isatty.return_value = True
        from synapps.onboarding.init_wizard import run_init
        run_init("/tmp/myproject")

    all_output = " ".join(printed_output)
    assert "python" in all_output.lower()


def test_non_interactive_stdin():
    with (
        patch("sys.stdin") as mock_stdin,
        patch("synapps.onboarding.init_wizard.detect_languages", return_value=[("python", 10)]),
    ):
        mock_stdin.isatty.return_value = False
        from synapps.onboarding.init_wizard import run_init
        with pytest.raises((typer.Exit, SystemExit)) as exc_info:
            run_init("/tmp/myproject")
        # Should exit with code 1
        exc = exc_info.value
        if isinstance(exc, typer.Exit):
            assert exc.exit_code == 1
        else:
            assert exc.code == 1


def test_docker_not_running_exits_with_error():
    """Init should fail early with a clear message when Docker is not running."""
    with (
        patch("sys.stdin") as mock_stdin,
        patch("synapps.onboarding.init_wizard.docker") as mock_docker_mod,
        patch("synapps.onboarding.init_wizard.detect_languages", return_value=[("python", 10)]),
    ):
        mock_stdin.isatty.return_value = True
        mock_docker_mod.from_env.return_value.ping.side_effect = docker.errors.DockerException("not running")
        mock_docker_mod.errors = docker.errors

        from synapps.onboarding.init_wizard import run_init
        with pytest.raises((typer.Exit, SystemExit)) as exc_info:
            run_init("/tmp/myproject")

        exc = exc_info.value
        if isinstance(exc, typer.Exit):
            assert exc.exit_code == 1
        else:
            assert exc.code == 1


def test_memgraph_auto_started_via_connection_manager():
    """Init should start Memgraph automatically instead of failing on a bolt check."""
    opts = _common_patches(confirm_side_effect=[True, True, True, True, True])
    _, _, mock_cm = _run_with_patches("/tmp/myproject", opts)
    # ConnectionManager.get_connection() is called (which auto-starts Memgraph)
    mock_cm.return_value.get_connection.assert_called_once()


# ---------------------------------------------------------------------------
# Database mode prompt
# ---------------------------------------------------------------------------

def test_db_mode_prompt_shown_when_no_existing_config():
    """Init should ask shared vs dedicated when no db config exists."""
    # confirm_side_effect: [want_index, language confirm, db mode (shared=True)]
    opts = _common_patches(confirm_side_effect=[True, True, True])
    _run_with_patches("/tmp/myproject", opts, has_existing_db_config=False)


def test_db_mode_prompt_skipped_when_config_exists():
    """Init should skip db mode prompt when project already has db config."""
    # confirm_side_effect: [want_index, language confirm] — no db mode confirm needed
    opts = _common_patches(confirm_side_effect=[True, True])
    _run_with_patches("/tmp/myproject", opts, has_existing_db_config=True)


def test_has_existing_db_config_returns_false_for_missing_file(tmp_path):
    from synapps.onboarding.init_wizard import _has_existing_db_config
    assert _has_existing_db_config(str(tmp_path)) is False


def test_has_existing_db_config_returns_false_without_key(tmp_path):
    from synapps.onboarding.init_wizard import _has_existing_db_config
    config_dir = tmp_path / ".synapps"
    config_dir.mkdir()
    (config_dir / "config.json").write_text('{"some_key": true}')
    assert _has_existing_db_config(str(tmp_path)) is False


def test_has_existing_db_config_returns_true_with_key(tmp_path):
    from synapps.onboarding.init_wizard import _has_existing_db_config
    config_dir = tmp_path / ".synapps"
    config_dir.mkdir()
    (config_dir / "config.json").write_text('{"dedicated_instance": false}')
    assert _has_existing_db_config(str(tmp_path)) is True


def test_write_db_config_creates_file(tmp_path):
    from synapps.onboarding.init_wizard import _write_db_config
    import json

    _write_db_config(str(tmp_path), dedicated=True)

    config = json.loads((tmp_path / ".synapps" / "config.json").read_text())
    assert config["dedicated_instance"] is True


def test_write_db_config_preserves_existing_keys(tmp_path):
    from synapps.onboarding.init_wizard import _write_db_config
    import json

    config_dir = tmp_path / ".synapps"
    config_dir.mkdir()
    (config_dir / "config.json").write_text('{"existing_key": "value"}')

    _write_db_config(str(tmp_path), dedicated=False)

    config = json.loads((config_dir / "config.json").read_text())
    assert config["dedicated_instance"] is False
    assert config["existing_key"] == "value"


# ---------------------------------------------------------------------------
# Indexing opt-out flow
# ---------------------------------------------------------------------------

def test_wizard_skips_indexing_when_declined():
    """Declining 'Index now?' must skip Memgraph startup and indexing entirely."""
    mock_cm = MagicMock()
    mock_svc = MagicMock()

    with (
        patch("synapps.onboarding.init_wizard.detect_languages", return_value=[("python", 10)]),
        patch("synapps.onboarding.init_wizard.ConnectionManager", mock_cm),
        patch("synapps.onboarding.init_wizard.ensure_schema"),
        patch("synapps.onboarding.init_wizard.SynappsService", mock_svc),
        patch("synapps.onboarding.init_wizard.docker") as mock_docker_mod,
        patch("synapps.onboarding.init_wizard._has_existing_db_config", return_value=True),
        patch("synapps.onboarding.init_wizard._write_db_config"),
        patch("synapps.onboarding.init_wizard._configure_agents", return_value=([], [], [])),
        patch("typer.confirm", side_effect=[False]),  # decline indexing
        patch("sys.stdin") as mock_stdin,
    ):
        mock_docker_mod.from_env.return_value = MagicMock()
        mock_docker_mod.errors = docker.errors
        mock_stdin.isatty.return_value = True
        from synapps.onboarding.init_wizard import run_init
        run_init("/tmp/myproject")

    mock_cm.assert_not_called()
    mock_svc.assert_not_called()


def test_wizard_skips_indexing_persists_db_config():
    """Declining 'Index now?' with no existing DB config must still call _write_db_config."""
    mock_write_db_config = MagicMock()
    mock_cm = MagicMock()
    mock_svc = MagicMock()

    with (
        patch("synapps.onboarding.init_wizard.detect_languages", return_value=[("python", 10)]),
        patch("synapps.onboarding.init_wizard.ConnectionManager", mock_cm),
        patch("synapps.onboarding.init_wizard.ensure_schema"),
        patch("synapps.onboarding.init_wizard.SynappsService", mock_svc),
        patch("synapps.onboarding.init_wizard.docker") as mock_docker_mod,
        patch("synapps.onboarding.init_wizard._has_existing_db_config", return_value=False),
        patch("synapps.onboarding.init_wizard._write_db_config", mock_write_db_config),
        patch("synapps.onboarding.init_wizard._configure_agents", return_value=([], [], [])),
        patch("typer.confirm", side_effect=[False, True]),  # decline indexing, accept shared DB
        patch("sys.stdin") as mock_stdin,
    ):
        mock_docker_mod.from_env.return_value = MagicMock()
        mock_docker_mod.errors = docker.errors
        mock_stdin.isatty.return_value = True
        from synapps.onboarding.init_wizard import run_init
        run_init("/tmp/myproject")

    mock_write_db_config.assert_called_once()
    mock_svc.assert_not_called()


# ---------------------------------------------------------------------------
# smart_index allowed_languages filtering
# ---------------------------------------------------------------------------

def test_smart_index_respects_allowed_languages():
    """smart_index with allowed_languages=["python"] must pass only the python plugin to index_project."""
    from unittest.mock import MagicMock, patch
    from synapps.service.indexing import IndexingService

    mock_python_plugin = MagicMock()
    mock_python_plugin.name = "python"
    mock_typescript_plugin = MagicMock()
    mock_typescript_plugin.name = "typescript"

    mock_conn = MagicMock()
    mock_conn.query.return_value = []  # no existing Repository -> full-index path

    mock_registry = MagicMock()
    mock_registry.detect_with_files.return_value = [
        (mock_python_plugin, ["/a.py"]),
        (mock_typescript_plugin, ["/b.ts"]),
    ]

    svc = IndexingService(conn=mock_conn, registry=mock_registry)

    captured_plugin_files: list = []

    def fake_index_project(path, language="csharp", on_progress=None, plugin_files=None):
        if plugin_files is not None:
            captured_plugin_files.extend(plugin_files)

    svc.index_project = fake_index_project  # type: ignore[method-assign]

    with (
        patch("synapps.service.indexing.get_last_indexed_commit", return_value=None),
        patch("synapps.service.indexing.is_git_repo", return_value=False),
    ):
        svc.smart_index("/proj", allowed_languages=["python"])

    passed_names = [p.name for p, _ in captured_plugin_files]
    assert "python" in passed_names
    assert "typescript" not in passed_names


def test_smart_index_allowed_languages_none_passes_all():
    """smart_index without allowed_languages must pass all detected plugins (backward compat)."""
    from unittest.mock import MagicMock, patch
    from synapps.service.indexing import IndexingService

    mock_python_plugin = MagicMock()
    mock_python_plugin.name = "python"
    mock_typescript_plugin = MagicMock()
    mock_typescript_plugin.name = "typescript"

    mock_conn = MagicMock()
    mock_conn.query.return_value = []

    mock_registry = MagicMock()
    mock_registry.detect_with_files.return_value = [
        (mock_python_plugin, ["/a.py"]),
        (mock_typescript_plugin, ["/b.ts"]),
    ]

    svc = IndexingService(conn=mock_conn, registry=mock_registry)

    captured_plugin_files: list = []

    def fake_index_project(path, language="csharp", on_progress=None, plugin_files=None):
        if plugin_files is not None:
            captured_plugin_files.extend(plugin_files)

    svc.index_project = fake_index_project  # type: ignore[method-assign]

    with (
        patch("synapps.service.indexing.get_last_indexed_commit", return_value=None),
        patch("synapps.service.indexing.is_git_repo", return_value=False),
    ):
        svc.smart_index("/proj")

    passed_names = [p.name for p, _ in captured_plugin_files]
    assert "python" in passed_names
    assert "typescript" in passed_names


class TestInitWizardHookOffer:
    def test_init_offers_hook_installation(self, tmp_path: Path) -> None:
        """Verify the wizard calls _configure_agents for unified agent configuration."""
        from unittest.mock import patch, MagicMock

        with patch("synapps.onboarding.init_wizard._configure_agents", return_value=([], [], [])) as mock_configure, \
             patch("synapps.onboarding.init_wizard.detect_languages", return_value=[("python", 10)]), \
             patch("synapps.onboarding.init_wizard._prompt_language_confirmation", return_value=["python"]), \
             patch("synapps.onboarding.init_wizard._checks_for_languages", return_value=[]), \
             patch("synapps.onboarding.init_wizard.DoctorService") as mock_doctor, \
             patch("synapps.onboarding.init_wizard.ConnectionManager") as mock_conn, \
             patch("synapps.onboarding.init_wizard.ensure_schema"), \
             patch("synapps.onboarding.init_wizard.SynappsService") as mock_svc, \
             patch("synapps.onboarding.init_wizard._has_existing_db_config", return_value=True), \
             patch("synapps.onboarding.init_wizard.docker") as mock_docker_mod, \
             patch("typer.confirm", return_value=True), \
             patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            mock_docker_mod.from_env.return_value = MagicMock()
            mock_docker_mod.errors = docker.errors
            mock_report = MagicMock()
            mock_report.checks = []
            mock_report.has_failures = False
            mock_doctor.return_value.run.return_value = mock_report
            mock_svc.return_value.smart_index.return_value = "42 symbols"

            from synapps.onboarding.init_wizard import run_init
            run_init(str(tmp_path))

        mock_configure.assert_called_once()


# ---------------------------------------------------------------------------
# _prompt_multiselect
# ---------------------------------------------------------------------------

def _mock_select_sequence(values):
    """Create a mock that returns values sequentially for inquirer.select calls."""
    from unittest.mock import MagicMock
    mocks = []
    for v in values:
        m = MagicMock()
        m.execute.return_value = v
        mocks.append(m)
    return mocks


def test_harness_multiselect_shows_all():
    from unittest.mock import MagicMock, patch
    from synapps.onboarding.init_wizard import _prompt_multiselect, _ALL_HARNESSES

    console = MagicMock()

    # Nothing pre-checked, user hits Continue immediately -> empty list
    mocks = _mock_select_sequence(["__continue__"])
    with patch("InquirerPy.inquirer.select", side_effect=mocks):
        result = _prompt_multiselect(console, _ALL_HARNESSES, set(), "AI agent harnesses:")
    assert result == []

    # Pre-checked claude and copilot, user hits Continue -> those two returned
    mocks = _mock_select_sequence(["__continue__"])
    with patch("InquirerPy.inquirer.select", side_effect=mocks):
        result = _prompt_multiselect(console, _ALL_HARNESSES, {"claude", "copilot"}, "AI agent harnesses:")
    assert sorted(result) == ["claude", "copilot"]


def test_harness_multiselect_toggle():
    from unittest.mock import MagicMock, patch
    from synapps.onboarding.init_wizard import _prompt_multiselect, _ALL_HARNESSES

    console = MagicMock()

    # Pre-checked claude, user toggles claude off then copilot on, then Continue
    mocks = _mock_select_sequence(["claude", "copilot", "__continue__"])
    with patch("InquirerPy.inquirer.select", side_effect=mocks):
        result = _prompt_multiselect(console, _ALL_HARNESSES, {"claude"}, "AI agent harnesses:")
    assert result == ["copilot"]


# ---------------------------------------------------------------------------
# _configure_agents — global install options
# ---------------------------------------------------------------------------

def test_global_install_options_applied_to_all(tmp_path):
    from unittest.mock import MagicMock, patch, call
    from synapps.hooks.detector import DetectedAgent
    from synapps.onboarding.mcp_configurator import MCPClient

    claude_agent = DetectedAgent(name="claude", display_name="Claude Code", config_path=tmp_path / "claude.json")
    cursor_agent = DetectedAgent(name="cursor", display_name="Cursor", config_path=tmp_path / "cursor.json")
    claude_client = MCPClient(name="Claude Code", config_path=tmp_path / "claude.json", servers_key="mcpServers")
    cursor_client = MCPClient(name="Cursor", config_path=tmp_path / "cursor.json", servers_key="mcpServers")

    console = MagicMock()

    select_mocks = _mock_select_sequence(["__continue__"])
    with (
        patch("synapps.hooks.detector.detect_agents", return_value=[claude_agent, cursor_agent]),
        patch("synapps.onboarding.init_wizard.detect_mcp_clients", return_value=[claude_client, cursor_client]),
        patch("synapps.onboarding.init_wizard.write_mcp_config") as mock_write_mcp,
        patch("synapps.hooks.config_upsert.upsert_claude_hook"),
        patch("synapps.hooks.config_upsert.upsert_cursor_hook"),
        patch("synapps.onboarding.agent_instructions.install_agent_instructions") as mock_install_instr,
        patch("InquirerPy.inquirer.select", side_effect=select_mocks),
        patch("typer.confirm", side_effect=[True, True, False]),
    ):
        from synapps.onboarding.init_wizard import _configure_agents
        configured_clients, hook_agents, agent_files = _configure_agents(console, str(tmp_path))

    assert mock_write_mcp.call_count == 2
    mock_install_instr.assert_not_called()
    assert agent_files == []


def test_agent_instructions_filtered_by_harness(tmp_path):
    from synapps.onboarding.agent_instructions import install_agent_instructions

    written = install_agent_instructions(tmp_path, harnesses=["cursor"])

    assert ".cursor/rules/synapps.mdc" in written
    assert "CLAUDE.md" not in written
    assert ".github/copilot-instructions.md" not in written
