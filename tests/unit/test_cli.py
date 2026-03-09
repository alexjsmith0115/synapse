from unittest.mock import patch, MagicMock
from typer.testing import CliRunner
from synapse.cli.app import app

runner = CliRunner()


def _svc(overrides: dict | None = None):
    """Return a MagicMock SynapseService with sensible defaults."""
    svc = MagicMock()
    svc.find_callers.return_value = []
    svc.find_callees.return_value = []
    svc.find_implementations.return_value = []
    svc.search_symbols.return_value = []
    svc.find_type_references.return_value = []
    svc.find_dependencies.return_value = []
    svc.get_hierarchy.return_value = {"parents": [], "children": []}
    if overrides:
        for k, v in overrides.items():
            setattr(svc, k, MagicMock(return_value=v))
    return svc


def test_callers_prints_full_name_and_signature():
    svc = _svc({"find_callers": [{"full_name": "A.Caller", "signature": "Caller() : void"}]})
    svc.get_symbol.return_value = {"full_name": "A.Method", "_labels": ["Method"]}
    with patch("synapse.cli.app._get_service", return_value=svc):
        result = runner.invoke(app, ["callers", "A.Method"])
    assert result.exit_code == 0
    assert "A.Caller" in result.output
    assert "Caller() : void" in result.output


def test_callers_prints_no_results_when_empty():
    svc = _svc()
    svc.get_symbol.return_value = {"full_name": "A.Method", "_labels": ["Method"]}
    with patch("synapse.cli.app._get_service", return_value=svc):
        result = runner.invoke(app, ["callers", "A.Method"])
    assert "No results" in result.output


def test_search_prints_full_name():
    svc = _svc({"search_symbols": [{"full_name": "A.MyClass", "name": "MyClass"}]})
    with patch("synapse.cli.app._get_service", return_value=svc):
        result = runner.invoke(app, ["search", "MyClass"])
    assert "A.MyClass" in result.output


def test_hierarchy_prints_labeled_sections():
    svc = _svc()
    svc.get_hierarchy.return_value = {
        "parents": [{"full_name": "A.Base"}],
        "children": [{"full_name": "A.Child"}],
    }
    with patch("synapse.cli.app._get_service", return_value=svc):
        result = runner.invoke(app, ["hierarchy", "A.Middle"])
    assert "Parents:" in result.output
    assert "A.Base" in result.output
    assert "Children:" in result.output
    assert "A.Child" in result.output


def test_type_refs_prints_full_name_and_kind():
    svc = _svc({"find_type_references": [{"symbol": {"full_name": "A.Caller"}, "kind": "parameter"}]})
    with patch("synapse.cli.app._get_service", return_value=svc):
        result = runner.invoke(app, ["type-refs", "A.IFoo"])
    assert "A.Caller" in result.output
    assert "parameter" in result.output


def test_dependencies_prints_full_name_and_kind():
    svc = _svc({"find_dependencies": [{"type": {"full_name": "A.Dep"}, "kind": "return_type"}]})
    with patch("synapse.cli.app._get_service", return_value=svc):
        result = runner.invoke(app, ["dependencies", "A.Method"])
    assert "A.Dep" in result.output
    assert "return_type" in result.output


def test_index_calls_command_does_not_exist():
    result = runner.invoke(app, ["index-calls", "/some/path"])
    assert result.exit_code != 0
