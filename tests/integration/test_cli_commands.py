"""
CLI command integration tests.

Requires Memgraph on localhost:7687 and .NET SDK.
Run with: pytest tests/integration/test_cli_commands.py -v -m integration
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from synapse.cli.app import app
from synapse.service import SynapseService

runner = CliRunner()


def _invoke(service: SynapseService, args: list[str]):
    """Patch _get_service so CLI commands use the test-scoped fixture service.

    Without this, _get_service() constructs a live GraphConnection from env
    vars, bypassing the session fixture and hitting a different (empty) graph.
    """
    with patch("synapse.cli.app._get_service", return_value=service):
        return runner.invoke(app, args)


# ---------------------------------------------------------------------------
# Bug 1 regression: CLI callers/callees for controller actions
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_callees_controller_create(service: SynapseService) -> None:
    result = _invoke(service, ["callees", "SynapseTest.Controllers.TaskController.Create"])
    assert result.exit_code == 0
    assert "CreateTaskAsync" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_callers_service_method(service: SynapseService) -> None:
    result = _invoke(service, ["callers", "SynapseTest.Services.TaskService.CreateTaskAsync"])
    assert result.exit_code == 0
    assert "Create" in result.output


# ---------------------------------------------------------------------------
# Relationship commands
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_implementations(service: SynapseService) -> None:
    result = _invoke(service, ["implementations", "SynapseTest.Services.ITaskService"])
    assert result.exit_code == 0
    assert "TaskService" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_hierarchy(service: SynapseService) -> None:
    result = _invoke(service, ["hierarchy", "SynapseTest.Models.TaskItem"])
    assert result.exit_code == 0
    assert "BaseEntity" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_trace(service: SynapseService) -> None:
    result = _invoke(service, [
        "trace",
        "SynapseTest.Controllers.TaskController.Create",
        "SynapseTest.Services.ProjectService.ValidateProjectAsync",
    ])
    assert result.exit_code == 0
    assert "Path" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_entry_points(service: SynapseService) -> None:
    result = _invoke(service, [
        "entry-points",
        "SynapseTest.Services.ProjectService.ValidateProjectAsync",
    ])
    assert result.exit_code == 0
    assert "TaskController" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_call_depth(service: SynapseService) -> None:
    result = _invoke(service, [
        "call-depth",
        "SynapseTest.Controllers.TaskController.Create",
    ])
    assert result.exit_code == 0
    assert "depth" in result.output.lower()


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_impact(service: SynapseService) -> None:
    result = _invoke(service, [
        "impact",
        "SynapseTest.Services.TaskService.CreateTaskAsync",
    ])
    assert result.exit_code == 0
    assert "TaskController" in result.output or "direct" in result.output.lower()


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_contract(service: SynapseService) -> None:
    result = _invoke(service, [
        "contract",
        "SynapseTest.Services.TaskService.CreateTaskAsync",
    ])
    assert result.exit_code == 0
    assert "ITaskService" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_type_impact(service: SynapseService) -> None:
    result = _invoke(service, [
        "type-impact",
        "SynapseTest.Services.ITaskService",
    ])
    assert result.exit_code == 0
    assert "ITaskService" in result.output


# ---------------------------------------------------------------------------
# Symbol query commands
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_symbol(service: SynapseService) -> None:
    result = _invoke(service, ["symbol", "SynapseTest.Services.TaskService"])
    assert result.exit_code == 0
    assert "TaskService" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_source(service: SynapseService) -> None:
    result = _invoke(service, ["source", "SynapseTest.Controllers.TaskController"])
    assert result.exit_code == 0
    assert "TaskController" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_search(service: SynapseService) -> None:
    result = _invoke(service, ["search", "Task"])
    assert result.exit_code == 0
    assert "Task" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_type_refs(service: SynapseService) -> None:
    result = _invoke(service, ["type-refs", "SynapseTest.Services.ITaskService"])
    assert result.exit_code == 0
    assert "TaskController" in result.output or "ITaskService" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_dependencies(service: SynapseService) -> None:
    result = _invoke(service, ["dependencies", "SynapseTest.Controllers.TaskController"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Project-level commands
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_status(service: SynapseService) -> None:
    result = _invoke(service, ["status"])
    assert result.exit_code == 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_query(service: SynapseService) -> None:
    result = _invoke(service, ["query", "MATCH (n:Class) RETURN n.name LIMIT 5"])
    assert result.exit_code == 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_context(service: SynapseService) -> None:
    result = _invoke(service, ["context", "SynapseTest.Controllers.TaskController"])
    assert result.exit_code == 0
    assert "TaskController" in result.output


# ---------------------------------------------------------------------------
# Audit / summarize commands
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_audit(service: SynapseService) -> None:
    result = _invoke(service, ["audit", "untested_services"])
    assert result.exit_code == 0
    assert "untested_services" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_summarize(service: SynapseService) -> None:
    result = _invoke(service, ["summarize", "SynapseTest.Services.TaskService"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Summary subcommands
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_summary_set_get_list(service: SynapseService) -> None:
    set_result = _invoke(service, [
        "summary", "set", "SynapseTest.Models.TaskItem", "A task entity."
    ])
    assert set_result.exit_code == 0

    get_result = _invoke(service, ["summary", "get", "SynapseTest.Models.TaskItem"])
    assert get_result.exit_code == 0
    assert "A task entity." in get_result.output

    list_result = _invoke(service, ["summary", "list"])
    assert list_result.exit_code == 0
    assert "TaskItem" in list_result.output
