"""
CLI command integration tests against the Java fixture (SynappsJavaTest).

Requires Memgraph on localhost:7687 and Eclipse JDT LS (Java JDK 11+).
Run with: pytest tests/integration/test_cli_commands_java.py -v -m integration
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from synapps.cli.app import app
from synapps.service import SynappsService
from tests.integration.conftest import JAVA_FIXTURE_PATH

runner = CliRunner()


def _invoke(service: SynappsService, args: list[str]):
    """Patch _get_service so CLI commands use the Java test-scoped fixture service."""
    with patch("synapps.cli.app._get_service", return_value=service):
        return runner.invoke(app, args)


# ---------------------------------------------------------------------------
# Project-level commands
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(30)
def test_status(java_service: SynappsService) -> None:
    """status command returns exit code 0 for the Java fixture."""
    result = _invoke(java_service, ["status"])
    assert result.exit_code == 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_query(java_service: SynappsService) -> None:
    """query command executes Cypher against Java-indexed graph."""
    result = _invoke(java_service, [
        "query",
        "MATCH (n:Class {language: 'java'}) RETURN n.name LIMIT 5",
    ])
    assert result.exit_code == 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_delete(java_service: SynappsService) -> None:
    """delete command returns exit code 0 for a nonexistent project."""
    result = _invoke(java_service, ["delete", "/tmp/nonexistent-project"])
    assert result.exit_code == 0
    assert "Deleted" in result.output


# ---------------------------------------------------------------------------
# Symbol query commands
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_symbol(java_service: SynappsService) -> None:
    """symbol command returns info for a Java interface."""
    result = _invoke(java_service, ["symbol", "com.synappstest.IAnimal"])
    assert result.exit_code == 0
    assert "IAnimal" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_source(java_service: SynappsService) -> None:
    """source command returns exit code 0 for a Java class."""
    result = _invoke(java_service, ["source", "com.synappstest.Dog"])
    assert result.exit_code == 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_search(java_service: SynappsService) -> None:
    """search command returns matching symbols from Java fixture."""
    result = _invoke(java_service, ["search", "Animal"])
    assert result.exit_code == 0
    assert "Animal" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_search_language_filter(java_service: SynappsService) -> None:
    """search with --language java filters to only Java symbols."""
    result = _invoke(java_service, ["search", "Animal", "--language", "java"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Relationship commands
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_hierarchy(java_service: SynappsService) -> None:
    """hierarchy command returns parent chain for Dog (Animal ancestor)."""
    result = _invoke(java_service, ["hierarchy", "com.synappstest.Dog"])
    assert result.exit_code == 0
    assert "Animal" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_implementations(java_service: SynappsService) -> None:
    """implementations command works for Java interfaces."""
    result = _invoke(java_service, [
        "implementations",
        "com.synappstest.IAnimal",
    ])
    assert result.exit_code == 0
    assert "Animal" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_callers(java_service: SynappsService) -> None:
    """callers command returns exit code 0 (may have no results without JDT LS)."""
    result = _invoke(java_service, ["callers", "com.synappstest.IAnimal.speak()"])
    assert result.exit_code == 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_callees(java_service: SynappsService) -> None:
    """callees command returns exit code 0 for a Java method."""
    result = _invoke(java_service, [
        "callees",
        "com.synappstest.AnimalService.greet()",
    ])
    assert result.exit_code == 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_usages(java_service: SynappsService) -> None:
    """usages command returns exit code 0 for a Java interface."""
    result = _invoke(java_service, ["usages", "com.synappstest.IAnimal"])
    assert result.exit_code == 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_dependencies(java_service: SynappsService) -> None:
    """dependencies command returns exit code 0 for a Java class."""
    result = _invoke(java_service, [
        "dependencies",
        "com.synappstest.AnimalService",
    ])
    assert result.exit_code == 0



# ---------------------------------------------------------------------------
# Call chain / entry point / impact commands
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_context(java_service: SynappsService) -> None:
    """context command returns context text for a Java class."""
    result = _invoke(java_service, ["context", "com.synappstest.Dog"])
    assert result.exit_code == 0
    assert "Dog" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_trace(java_service: SynappsService) -> None:
    """trace command returns exit code 0 (may find no paths without call edges)."""
    result = _invoke(java_service, [
        "trace",
        "com.synappstest.AnimalService.greet",
        "com.synappstest.IAnimal.speak",
    ])
    assert result.exit_code == 0



@pytest.mark.integration
@pytest.mark.timeout(10)
def test_entry_points(java_service: SynappsService) -> None:
    """entry-points command returns exit code 0 for a Java method."""
    result = _invoke(java_service, [
        "entry-points",
        "com.synappstest.AnimalService.greet",
    ])
    assert result.exit_code == 0



# ---------------------------------------------------------------------------
# Summary subcommands
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_summary_set_get_list(java_service: SynappsService) -> None:
    """summary set/get/list subcommands round-trip correctly for Java symbols."""
    set_result = _invoke(java_service, [
        "summary", "set", "com.synappstest.Cat", "A cat class in Java.",
    ])
    assert set_result.exit_code == 0

    get_result = _invoke(java_service, [
        "summary", "get", "com.synappstest.Cat",
    ])
    assert get_result.exit_code == 0
    assert "A cat class in Java." in get_result.output

    list_result = _invoke(java_service, ["summary", "list"])
    assert list_result.exit_code == 0
    assert "Cat" in list_result.output
