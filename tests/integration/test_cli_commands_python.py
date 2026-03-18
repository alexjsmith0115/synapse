"""
CLI command integration tests against the Python fixture (SynapsePyTest).

Requires Memgraph on localhost:7687 and Python indexer.
Run with: pytest tests/integration/test_cli_commands_python.py -v -m integration
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from synapse.cli.app import app
from synapse.service import SynapseService

runner = CliRunner()


def _invoke(service: SynapseService, args: list[str]):
    """Patch _get_service so CLI commands use the Python test-scoped fixture service."""
    with patch("synapse.cli.app._get_service", return_value=service):
        return runner.invoke(app, args)


# ---------------------------------------------------------------------------
# Project-level commands
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_status(python_service: SynapseService) -> None:
    """status command returns exit code 0 for the Python fixture."""
    result = _invoke(python_service, ["status"])
    assert result.exit_code == 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_query(python_service: SynapseService) -> None:
    """query command executes Cypher against Python-indexed graph."""
    result = _invoke(python_service, [
        "query",
        "MATCH (n:Class {language: 'python'}) RETURN n.name LIMIT 5",
    ])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Symbol query commands
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_symbol(python_service: SynapseService) -> None:
    """symbol command returns info for a Python class."""
    result = _invoke(python_service, ["symbol", "synapsepytest.animals.IAnimal"])
    assert result.exit_code == 0
    assert "IAnimal" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_source(python_service: SynapseService) -> None:
    """source command returns Python source for a known method."""
    result = _invoke(python_service, ["source", "synapsepytest.animals.Dog.speak"])
    assert result.exit_code == 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_search(python_service: SynapseService) -> None:
    """search command returns matching symbols from Python fixture."""
    result = _invoke(python_service, ["search", "Animal"])
    assert result.exit_code == 0
    assert "Animal" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_search_language_filter(python_service: SynapseService) -> None:
    """search with --language python filters to only Python symbols."""
    result = _invoke(python_service, ["search", "Animal", "--language", "python"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Relationship commands
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_callers(python_service: SynapseService) -> None:
    """callers command returns exit code 0 (may have no results for Python fixture)."""
    result = _invoke(python_service, ["callers", "synapsepytest.animals.IAnimal.speak"])
    # Exit code 0 = either results found or "No results." printed
    assert result.exit_code == 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_callees(python_service: SynapseService) -> None:
    """callees command returns exit code 0 for a Python method."""
    result = _invoke(python_service, [
        "callees",
        "synapsepytest.services.AnimalService.get_greeting",
    ])
    assert result.exit_code == 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_implementations(python_service: SynapseService) -> None:
    """implementations command works for Python ABC classes."""
    result = _invoke(python_service, [
        "implementations",
        "synapsepytest.animals.IAnimal",
    ])
    assert result.exit_code == 0
    assert "Dog" in result.output
    assert "Cat" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_hierarchy(python_service: SynapseService) -> None:
    """hierarchy command returns parent chain for Dog (Animal → IAnimal)."""
    result = _invoke(python_service, ["hierarchy", "synapsepytest.animals.Dog"])
    assert result.exit_code == 0
    assert "Animal" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_type_refs(python_service: SynapseService) -> None:
    """type-refs command returns exit code 0 (may be empty for Python fixture)."""
    result = _invoke(python_service, ["type-refs", "synapsepytest.animals.IAnimal"])
    assert result.exit_code == 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_usages(python_service: SynapseService) -> None:
    """usages command returns exit code 0 for a Python class."""
    result = _invoke(python_service, ["usages", "synapsepytest.animals.IAnimal"])
    assert result.exit_code == 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_dependencies(python_service: SynapseService) -> None:
    """dependencies command returns exit code 0 for AnimalService."""
    result = _invoke(python_service, [
        "dependencies",
        "synapsepytest.services.AnimalService",
    ])
    assert result.exit_code == 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_context(python_service: SynapseService) -> None:
    """context command returns context text for a Python class."""
    result = _invoke(python_service, ["context", "synapsepytest.animals.Dog"])
    assert result.exit_code == 0
    assert "Dog" in result.output


# ---------------------------------------------------------------------------
# Call chain / entry point / impact commands
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_trace(python_service: SynapseService) -> None:
    """trace command returns exit code 0 (may find no paths for Python fixture)."""
    result = _invoke(python_service, [
        "trace",
        "synapsepytest.services.AnimalService.get_greeting",
        "synapsepytest.animals.IAnimal.speak",
    ])
    assert result.exit_code == 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_entry_points(python_service: SynapseService) -> None:
    """entry-points command returns exit code 0 for a Python method."""
    result = _invoke(python_service, [
        "entry-points",
        "synapsepytest.services.AnimalService.get_greeting",
    ])
    assert result.exit_code == 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_call_depth(python_service: SynapseService) -> None:
    """call-depth command returns exit code 0 for a Python method."""
    result = _invoke(python_service, [
        "call-depth",
        "synapsepytest.services.AnimalService.get_greeting",
    ])
    assert result.exit_code == 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_impact(python_service: SynapseService) -> None:
    """impact command returns exit code 0 and prints analysis output."""
    result = _invoke(python_service, [
        "impact",
        "synapsepytest.services.AnimalService.get_greeting",
    ])
    assert result.exit_code == 0
    assert "direct" in result.output.lower() or "impact" in result.output.lower()


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_contract(python_service: SynapseService) -> None:
    """contract command returns exit code 0 (may report no interface for Python methods)."""
    result = _invoke(python_service, [
        "contract",
        "synapsepytest.services.AnimalService.get_greeting",
    ])
    assert result.exit_code == 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_type_impact(python_service: SynapseService) -> None:
    """type-impact command returns exit code 0 for a Python class."""
    result = _invoke(python_service, [
        "type-impact",
        "synapsepytest.animals.IAnimal",
    ])
    assert result.exit_code == 0
    assert "IAnimal" in result.output


# ---------------------------------------------------------------------------
# Audit / summarize commands
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_audit(python_service: SynapseService) -> None:
    """audit command returns exit code 0 (empty violations for Python is OK)."""
    result = _invoke(python_service, ["audit", "layering_violations"])
    assert result.exit_code == 0
    assert "layering_violations" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_summarize(python_service: SynapseService) -> None:
    """summarize command returns exit code 0 and prints a summary for a Python class."""
    result = _invoke(python_service, ["summarize", "synapsepytest.animals.Dog"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Summary subcommands
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_summary_set_get_list(python_service: SynapseService) -> None:
    """summary set/get/list subcommands round-trip correctly for Python symbols."""
    set_result = _invoke(python_service, [
        "summary", "set", "synapsepytest.animals.Cat", "A cat that meows.",
    ])
    assert set_result.exit_code == 0

    get_result = _invoke(python_service, [
        "summary", "get", "synapsepytest.animals.Cat",
    ])
    assert get_result.exit_code == 0
    assert "A cat that meows." in get_result.output

    list_result = _invoke(python_service, ["summary", "list"])
    assert list_result.exit_code == 0
    assert "Cat" in list_result.output
