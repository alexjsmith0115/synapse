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
    svc.get_hierarchy.return_value = {"parents": [], "children": [], "implements": []}
    # Default: get_symbol returns a Method so callers/callees pass label validation
    svc.get_symbol.return_value = {"full_name": "A.Method", "_labels": ["Method"]}
    if overrides:
        for k, v in overrides.items():
            setattr(svc, k, MagicMock(return_value=v))
    return svc


def test_callers_prints_full_name_and_signature():
    svc = _svc({"find_callers": [{"full_name": "A.Caller", "signature": "Caller() : void"}]})
    with patch("synapse.cli.app._get_service", return_value=svc):
        result = runner.invoke(app, ["callers", "A.Method"])
    assert result.exit_code == 0
    assert "A.Caller" in result.output
    assert "Caller() : void" in result.output


def test_callers_prints_no_results_when_empty():
    svc = _svc()
    with patch("synapse.cli.app._get_service", return_value=svc):
        result = runner.invoke(app, ["callers", "A.Method"])
    assert "No results" in result.output


def test_callees_prints_full_name_and_signature():
    svc = _svc({"find_callees": [{"full_name": "A.Dep", "signature": "Dep() : void"}]})
    with patch("synapse.cli.app._get_service", return_value=svc):
        result = runner.invoke(app, ["callees", "A.Method"])
    assert result.exit_code == 0
    assert "A.Dep" in result.output
    assert "Dep() : void" in result.output


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
        "implements": [],
    }
    with patch("synapse.cli.app._get_service", return_value=svc):
        result = runner.invoke(app, ["hierarchy", "A.Middle"])
    assert "Parents:" in result.output
    assert "A.Base" in result.output
    assert "Children:" in result.output
    assert "A.Child" in result.output


def test_hierarchy_prints_none_for_empty_sections():
    svc = _svc()
    with patch("synapse.cli.app._get_service", return_value=svc):
        result = runner.invoke(app, ["hierarchy", "A.Leaf"])
    assert "Parents:" in result.output
    assert "Children:" in result.output
    assert "(none)" in result.output


def test_type_refs_prints_full_name_and_kind():
    svc = _svc({"find_type_references": [{"symbol": {"full_name": "A.Caller"}, "kind": "parameter"}]})
    with patch("synapse.cli.app._get_service", return_value=svc):
        result = runner.invoke(app, ["type-refs", "A.IFoo"])
    assert "A.Caller" in result.output
    assert "parameter" in result.output


def test_dependencies_prints_full_name_and_depth():
    svc = _svc({"find_dependencies": [{"type": {"full_name": "A.Dep"}, "depth": 1}]})
    with patch("synapse.cli.app._get_service", return_value=svc):
        result = runner.invoke(app, ["dependencies", "A.Method"])
    assert "A.Dep" in result.output
    assert "depth 1" in result.output


def test_index_calls_command_does_not_exist():
    result = runner.invoke(app, ["index-calls", "/some/path"])
    assert result.exit_code != 0


def test_callers_errors_when_given_a_class():
    svc = MagicMock()
    svc.get_symbol.return_value = {"full_name": "A.MyClass", "_labels": ["Class"]}
    with patch("synapse.cli.app._get_service", return_value=svc):
        result = runner.invoke(app, ["callers", "A.MyClass"])
    assert result.exit_code != 0
    assert "Class" in result.output
    assert "not a Method" in result.output


def test_callees_errors_when_given_a_class():
    svc = MagicMock()
    svc.get_symbol.return_value = {"full_name": "A.MyClass", "_labels": ["Class"]}
    with patch("synapse.cli.app._get_service", return_value=svc):
        result = runner.invoke(app, ["callees", "A.MyClass"])
    assert result.exit_code != 0
    assert "not a Method" in result.output


def test_implementations_errors_when_given_a_class():
    svc = MagicMock()
    svc.get_symbol.return_value = {"full_name": "A.MyClass", "_labels": ["Class"]}
    with patch("synapse.cli.app._get_service", return_value=svc):
        result = runner.invoke(app, ["implementations", "A.MyClass"])
    assert result.exit_code != 0
    assert "synapse hierarchy" in result.output


def test_callers_errors_when_symbol_not_found():
    svc = MagicMock()
    svc.get_symbol.return_value = None
    with patch("synapse.cli.app._get_service", return_value=svc):
        result = runner.invoke(app, ["callers", "A.Missing"])
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_implementations_accepts_abstract_class():
    svc = MagicMock()
    svc.get_symbol.return_value = {"full_name": "A.IAnimal", "_labels": ["Class"], "is_abstract": True}
    svc.find_implementations.return_value = [{"full_name": "A.Dog", "signature": None}]
    with patch("synapse.cli.app._get_service", return_value=svc):
        result = runner.invoke(app, ["implementations", "A.IAnimal"])
    assert result.exit_code == 0
    assert "Dog" in result.output


def test_index_missing_dependency_shows_reinstall_hint():
    svc = MagicMock()
    svc.index_project.side_effect = ModuleNotFoundError("No module named 'tree_sitter_typescript'")
    with patch("synapse.cli.app._get_service", return_value=svc):
        result = runner.invoke(app, ["index", "/some/path"])
    assert result.exit_code != 0
    assert "tree_sitter_typescript" in result.output
    assert "pip install" in result.output
