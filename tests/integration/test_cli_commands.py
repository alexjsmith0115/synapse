"""
CLI command integration tests.

Requires Memgraph on localhost:7687 and .NET SDK.
Run with: pytest tests/integration/test_cli_commands.py -v -m integration
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from synapps.cli.app import app
from synapps.service import SynappsService

runner = CliRunner()


def _invoke(service: SynappsService, args: list[str]):
    """Patch _get_service so CLI commands use the test-scoped fixture service.

    Without this, _get_service() constructs a live GraphConnection from env
    vars, bypassing the session fixture and hitting a different (empty) graph.
    """
    with patch("synapps.cli.app._get_service", return_value=service):
        return runner.invoke(app, args)


# ---------------------------------------------------------------------------
# Bug 1 regression: CLI callers/callees for controller actions
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_callees_controller_create(service: SynappsService) -> None:
    result = _invoke(service, ["callees", "SynappsTest.Controllers.TaskController.Create"])
    assert result.exit_code == 0
    assert "CreateTaskAsync" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_callers_service_method(service: SynappsService) -> None:
    result = _invoke(service, ["callers", "--include-tests", "SynappsTest.Services.TaskService.CreateTaskAsync"])
    assert result.exit_code == 0
    assert "Create" in result.output


# ---------------------------------------------------------------------------
# Project management commands
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_delete(service: SynappsService) -> None:
    result = _invoke(service, ["delete", "/tmp/nonexistent-project"])
    assert result.exit_code == 0
    assert "Deleted" in result.output


# ---------------------------------------------------------------------------
# Relationship commands
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_implementations(service: SynappsService) -> None:
    result = _invoke(service, ["implementations", "SynappsTest.Services.ITaskService"])
    assert result.exit_code == 0
    assert "TaskService" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_usages(service: SynappsService) -> None:
    """usages command returns exit code 0 for a C# interface."""
    result = _invoke(service, ["usages", "SynappsTest.Services.ITaskService"])
    assert result.exit_code == 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_hierarchy(service: SynappsService) -> None:
    result = _invoke(service, ["hierarchy", "SynappsTest.Models.TaskItem"])
    assert result.exit_code == 0
    assert "BaseEntity" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_trace(service: SynappsService) -> None:
    result = _invoke(service, [
        "trace",
        "SynappsTest.Controllers.TaskController.Create",
        "SynappsTest.Services.ProjectService.ValidateProjectAsync",
    ])
    assert result.exit_code == 0
    assert "Path" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_entry_points(service: SynappsService) -> None:
    result = _invoke(service, [
        "entry-points",
        "--include-tests",
        "SynappsTest.Services.ProjectService.ValidateProjectAsync",
    ])
    assert result.exit_code == 0
    assert "TaskController" in result.output



# ---------------------------------------------------------------------------
# Symbol query commands
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_symbol(service: SynappsService) -> None:
    result = _invoke(service, ["symbol", "SynappsTest.Services.TaskService"])
    assert result.exit_code == 0
    assert "TaskService" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_source(service: SynappsService) -> None:
    result = _invoke(service, ["source", "SynappsTest.Controllers.TaskController"])
    assert result.exit_code == 0
    assert "TaskController" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_search(service: SynappsService) -> None:
    result = _invoke(service, ["search", "Task"])
    assert result.exit_code == 0
    assert "Task" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_search_language_filter(service: SynappsService) -> None:
    """search with --language csharp filters to only C# symbols."""
    result = _invoke(service, ["search", "Task", "--language", "csharp"])
    assert result.exit_code == 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_dependencies(service: SynappsService) -> None:
    result = _invoke(service, ["dependencies", "SynappsTest.Controllers.TaskController"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Project-level commands
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_status(service: SynappsService) -> None:
    result = _invoke(service, ["status"])
    assert result.exit_code == 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_query(service: SynappsService) -> None:
    result = _invoke(service, ["query", "MATCH (n:Class) RETURN n.name LIMIT 5"])
    assert result.exit_code == 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_context(service: SynappsService) -> None:
    result = _invoke(service, ["context", "SynappsTest.Controllers.TaskController"])
    assert result.exit_code == 0
    assert "TaskController" in result.output



# ---------------------------------------------------------------------------
# Summary subcommands
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_summary_set_get_list(service: SynappsService) -> None:
    set_result = _invoke(service, [
        "summary", "set", "SynappsTest.Models.TaskItem", "A task entity."
    ])
    assert set_result.exit_code == 0

    get_result = _invoke(service, ["summary", "get", "SynappsTest.Models.TaskItem"])
    assert get_result.exit_code == 0
    assert "A task entity." in get_result.output

    list_result = _invoke(service, ["summary", "list"])
    assert list_result.exit_code == 0
    assert "TaskItem" in list_result.output
