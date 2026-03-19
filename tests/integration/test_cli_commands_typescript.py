"""
CLI command integration tests against the TypeScript fixture (SynapseJSTest).

Requires Memgraph on localhost:7687 and tsserver (TypeScript Language Server).
Run with: pytest tests/integration/test_cli_commands_typescript.py -v -m integration
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from synapse.cli.app import app
from synapse.service import SynapseService
from tests.integration.conftest import TYPESCRIPT_FIXTURE_PATH

runner = CliRunner()


def _invoke(service: SynapseService, args: list[str]):
    """Patch _get_service so CLI commands use the TypeScript test-scoped fixture service."""
    with patch("synapse.cli.app._get_service", return_value=service):
        return runner.invoke(app, args)


# ---------------------------------------------------------------------------
# Project-level commands
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_status(typescript_service: SynapseService) -> None:
    """status command returns exit code 0 for the TypeScript fixture."""
    result = _invoke(typescript_service, ["status"])
    assert result.exit_code == 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_query(typescript_service: SynapseService) -> None:
    """query command executes Cypher against TypeScript-indexed graph."""
    result = _invoke(typescript_service, [
        "query",
        "MATCH (n:Class {language: 'typescript'}) RETURN n.name LIMIT 5",
    ])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Symbol query commands
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_symbol(typescript_service: SynapseService) -> None:
    """symbol command returns info for a TypeScript interface."""
    result = _invoke(typescript_service, ["symbol", "src/animals.IAnimal"])
    assert result.exit_code == 0
    assert "IAnimal" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_source(typescript_service: SynapseService) -> None:
    """source command returns exit code 0 for a TypeScript class."""
    result = _invoke(typescript_service, ["source", "src/animals.Dog"])
    assert result.exit_code == 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_search(typescript_service: SynapseService) -> None:
    """search command returns matching TypeScript symbols."""
    result = _invoke(typescript_service, ["search", "Animal"])
    assert result.exit_code == 0
    assert "Animal" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_search_language_filter(typescript_service: SynapseService) -> None:
    """search with --language typescript filters to only TypeScript symbols."""
    result = _invoke(typescript_service, ["search", "Animal", "--language", "typescript"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Relationship commands
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_hierarchy(typescript_service: SynapseService) -> None:
    """hierarchy command returns parent chain for Dog (Animal ancestor)."""
    result = _invoke(typescript_service, ["hierarchy", "src/animals.Dog"])
    assert result.exit_code == 0
    assert "Animal" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_implementations(typescript_service: SynapseService) -> None:
    """implementations command works for TypeScript interfaces."""
    result = _invoke(typescript_service, [
        "implementations",
        "src/animals.IAnimal",
    ])
    assert result.exit_code == 0
    assert "Animal" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_callers(typescript_service: SynapseService) -> None:
    """callers command returns exit code 0 (may have no results without tsserver)."""
    result = _invoke(typescript_service, ["callers", "src/services.AnimalService.getGreeting"])
    # Exit code 0 = either results found or "No results." printed
    assert result.exit_code == 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_callees(typescript_service: SynapseService) -> None:
    """callees command returns exit code 0 for a TypeScript method."""
    result = _invoke(typescript_service, [
        "callees",
        "src/services.Greeter.greet",
    ])
    assert result.exit_code == 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_usages(typescript_service: SynapseService) -> None:
    """usages command returns exit code 0 for a TypeScript interface."""
    result = _invoke(typescript_service, ["usages", "src/animals.IAnimal"])
    assert result.exit_code == 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_dependencies(typescript_service: SynapseService) -> None:
    """dependencies command returns exit code 0 for a TypeScript class."""
    result = _invoke(typescript_service, [
        "dependencies",
        "src/services.AnimalService",
    ])
    assert result.exit_code == 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_type_refs(typescript_service: SynapseService) -> None:
    """type-refs command returns exit code 0 (may be empty) for a TypeScript interface."""
    result = _invoke(typescript_service, ["type-refs", "src/animals.IAnimal"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Call chain / entry point / impact commands
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_callers_abstract_class(typescript_service: SynapseService) -> None:
    """callers command on abstract Animal.speak returns exit code 0."""
    result = _invoke(typescript_service, ["callers", "src/animals.Animal.speak"])
    assert result.exit_code == 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_context(typescript_service: SynapseService) -> None:
    """context command returns context text for a TypeScript class."""
    result = _invoke(typescript_service, ["context", "src/animals.Dog"])
    assert result.exit_code == 0
    assert "Dog" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_trace(typescript_service: SynapseService) -> None:
    """trace command returns exit code 0 (may find no paths without call edges)."""
    result = _invoke(typescript_service, [
        "trace",
        "src/services.Greeter.greet",
        "src/animals.IAnimal.speak",
    ])
    assert result.exit_code == 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_impact(typescript_service: SynapseService) -> None:
    """impact command returns exit code 0 and prints analysis output."""
    result = _invoke(typescript_service, [
        "impact",
        "src/services.AnimalService.getGreeting",
    ])
    assert result.exit_code == 0
    assert "direct" in result.output.lower() or "impact" in result.output.lower()


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_contract(typescript_service: SynapseService) -> None:
    """contract command returns exit code 0 for a TypeScript method."""
    result = _invoke(typescript_service, [
        "contract",
        "src/services.AnimalService.getGreeting",
    ])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Summary subcommands
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_summary_set_get_list(typescript_service: SynapseService) -> None:
    """summary set/get/list subcommands round-trip correctly for TypeScript symbols."""
    set_result = _invoke(typescript_service, [
        "summary", "set", "src/animals.Cat", "A cat class in TypeScript.",
    ])
    assert set_result.exit_code == 0

    get_result = _invoke(typescript_service, [
        "summary", "get", "src/animals.Cat",
    ])
    assert get_result.exit_code == 0
    assert "A cat class in TypeScript." in get_result.output

    list_result = _invoke(typescript_service, ["summary", "list"])
    assert list_result.exit_code == 0
    assert "Cat" in list_result.output
