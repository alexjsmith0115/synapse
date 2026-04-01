import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner
from synapps.cli.app import app, _get_service

# Get the actual module (not the Typer `app` object)
cli_module = sys.modules["synapps.cli.app"]

runner = CliRunner()


def _svc(overrides: dict | None = None):
    """Return a MagicMock SynappsService with sensible defaults."""
    svc = MagicMock()
    svc.find_callers.return_value = []
    svc.find_callees.return_value = []
    svc.find_implementations.return_value = []
    svc.search_symbols.return_value = []
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
    with patch("synapps.cli.app._get_service", return_value=svc):
        result = runner.invoke(app, ["callers", "A.Method"])
    assert result.exit_code == 0
    assert "A.Caller" in result.output
    assert "Caller() : void" in result.output


def test_callers_prints_no_results_when_empty():
    svc = _svc()
    with patch("synapps.cli.app._get_service", return_value=svc):
        result = runner.invoke(app, ["callers", "A.Method"])
    assert "No results" in result.output


def test_callees_prints_full_name_and_signature():
    svc = _svc({"find_callees": [{"full_name": "A.Dep", "signature": "Dep() : void"}]})
    with patch("synapps.cli.app._get_service", return_value=svc):
        result = runner.invoke(app, ["callees", "A.Method"])
    assert result.exit_code == 0
    assert "A.Dep" in result.output
    assert "Dep() : void" in result.output


def test_search_prints_full_name():
    svc = _svc({"search_symbols": [{"full_name": "A.MyClass", "name": "MyClass"}]})
    with patch("synapps.cli.app._get_service", return_value=svc):
        result = runner.invoke(app, ["search", "MyClass"])
    assert "A.MyClass" in result.output


def test_hierarchy_prints_labeled_sections():
    svc = _svc()
    svc.get_hierarchy.return_value = {
        "parents": [{"full_name": "A.Base"}],
        "children": [{"full_name": "A.Child"}],
        "implements": [],
    }
    with patch("synapps.cli.app._get_service", return_value=svc):
        result = runner.invoke(app, ["hierarchy", "A.Middle"])
    assert "Parents:" in result.output
    assert "A.Base" in result.output
    assert "Children:" in result.output
    assert "A.Child" in result.output


def test_hierarchy_prints_none_for_empty_sections():
    svc = _svc()
    with patch("synapps.cli.app._get_service", return_value=svc):
        result = runner.invoke(app, ["hierarchy", "A.Leaf"])
    assert "Parents:" in result.output
    assert "Children:" in result.output
    assert "(none)" in result.output



def test_dependencies_prints_full_name_and_depth():
    svc = _svc({"find_dependencies": [{"type": {"full_name": "A.Dep"}, "depth": 1}]})
    with patch("synapps.cli.app._get_service", return_value=svc):
        result = runner.invoke(app, ["dependencies", "A.Method"])
    assert "A.Dep" in result.output
    assert "depth 1" in result.output


def test_index_calls_command_does_not_exist():
    result = runner.invoke(app, ["index-calls", "/some/path"])
    assert result.exit_code != 0


def test_callers_errors_when_given_a_class():
    svc = MagicMock()
    svc.get_symbol.return_value = {"full_name": "A.MyClass", "_labels": ["Class"]}
    with patch("synapps.cli.app._get_service", return_value=svc):
        result = runner.invoke(app, ["callers", "A.MyClass"])
    assert result.exit_code != 0
    assert "Class" in result.output
    assert "not a Method" in result.output


def test_callees_errors_when_given_a_class():
    svc = MagicMock()
    svc.get_symbol.return_value = {"full_name": "A.MyClass", "_labels": ["Class"]}
    with patch("synapps.cli.app._get_service", return_value=svc):
        result = runner.invoke(app, ["callees", "A.MyClass"])
    assert result.exit_code != 0
    assert "not a Method" in result.output


def test_implementations_errors_when_given_a_class():
    svc = MagicMock()
    svc.get_symbol.return_value = {"full_name": "A.MyClass", "_labels": ["Class"]}
    with patch("synapps.cli.app._get_service", return_value=svc):
        result = runner.invoke(app, ["implementations", "A.MyClass"])
    assert result.exit_code != 0
    assert "synapps hierarchy" in result.output


def test_callers_errors_when_symbol_not_found():
    svc = MagicMock()
    svc.get_symbol.return_value = None
    with patch("synapps.cli.app._get_service", return_value=svc):
        result = runner.invoke(app, ["callers", "A.Missing"])
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_implementations_accepts_abstract_class():
    svc = MagicMock()
    svc.get_symbol.return_value = {"full_name": "A.IAnimal", "_labels": ["Class"], "is_abstract": True}
    svc.find_implementations.return_value = [{"full_name": "A.Dog", "signature": None}]
    with patch("synapps.cli.app._get_service", return_value=svc):
        result = runner.invoke(app, ["implementations", "A.IAnimal"])
    assert result.exit_code == 0
    assert "Dog" in result.output


def test_index_missing_dependency_shows_reinstall_hint():
    svc = MagicMock()
    svc.smart_index.side_effect = ModuleNotFoundError("No module named 'tree_sitter_typescript'")
    with patch("synapps.cli.app._get_service", return_value=svc):
        result = runner.invoke(app, ["index", "/some/path"])
    assert result.exit_code != 0
    assert "tree_sitter_typescript" in result.output
    assert "pip install" in result.output


def test_get_service_uses_connection_manager():
    """Verify _get_service routes through ConnectionManager with explicit path."""
    mock_cm_cls = MagicMock()
    mock_conn = MagicMock()
    mock_cm_cls.return_value.get_connection.return_value = mock_conn

    original_svc = cli_module._svc
    try:
        cli_module._svc = None
        with patch.object(cli_module, "ConnectionManager", mock_cm_cls), \
             patch.object(cli_module, "ensure_schema"), \
             patch.object(cli_module, "SynappsService") as mock_svc_cls:
            result = _get_service("/some/project")
            mock_cm_cls.assert_called_once_with("/some/project")
            mock_cm_cls.return_value.get_connection.assert_called_once()
            mock_svc_cls.assert_called_once_with(mock_conn)
            assert result is mock_svc_cls.return_value
    finally:
        cli_module._svc = original_svc


def test_get_service_defaults_to_cwd():
    """Verify _get_service falls back to Path.cwd() when no path given."""
    mock_cm_cls = MagicMock()
    mock_conn = MagicMock()
    mock_cm_cls.return_value.get_connection.return_value = mock_conn

    original_svc = cli_module._svc
    try:
        cli_module._svc = None
        with patch.object(cli_module, "ConnectionManager", mock_cm_cls), \
             patch.object(cli_module, "ensure_schema"), \
             patch.object(cli_module, "SynappsService"), \
             patch("synapps.cli.app.Path") as mock_path:
            mock_path.cwd.return_value = Path("/mock/cwd")
            _get_service()
            mock_cm_cls.assert_called_once_with("/mock/cwd")
    finally:
        cli_module._svc = original_svc


def test_index_no_longer_shows_banner():
    """Index command does not show banner (moved to synapps init)."""
    svc = _svc()
    svc.get_index_status.return_value = None
    svc.smart_index.return_value = "indexed 42 symbols"
    with patch("synapps.cli.app._get_service", return_value=svc), \
         patch("synapps.cli.app.print_banner") as mock_banner:
        result = runner.invoke(app, ["index", "/tmp/test"])
    assert result.exit_code == 0
    mock_banner.assert_not_called()


def test_index_still_works_end_to_end():
    """Index command still calls smart_index and prints Done."""
    svc = _svc()
    svc.get_index_status.return_value = None
    svc.smart_index.return_value = "indexed 10 files"
    with patch("synapps.cli.app._get_service", return_value=svc), \
         patch("synapps.cli.app.print_banner"):
        result = runner.invoke(app, ["index", "/tmp/test"])
    assert result.exit_code == 0
    svc.smart_index.assert_called_once()
    assert "Done" in result.output


# --- ERR-05: Not-indexed suggestion in sync command ---


def test_sync_suggests_index_when_project_not_indexed():
    """ERR-05: sync on unindexed project suggests 'synapps index'."""
    svc = _svc()
    svc.sync_project.side_effect = ValueError("No language plugin found")
    svc.get_index_status.return_value = None  # project not indexed
    with patch("synapps.cli.app._get_service", return_value=svc):
        result = runner.invoke(app, ["sync", "/tmp/myproject"])
    assert result.exit_code != 0
    assert "synapps index" in result.output


def test_sync_shows_original_error_when_project_indexed():
    """ERR-05: sync error on indexed project shows original error, not index suggestion."""
    svc = _svc()
    svc.sync_project.side_effect = ValueError("Something else went wrong")
    svc.get_index_status.return_value = {"path": "/tmp/myproject", "commit": "abc123"}
    with patch("synapps.cli.app._get_service", return_value=svc):
        result = runner.invoke(app, ["sync", "/tmp/myproject"])
    assert result.exit_code != 0
    assert "Something else went wrong" in result.output
    assert "synapps index" not in result.output


def test_init_command_calls_run_init():
    with patch("synapps.onboarding.init_wizard.run_init") as mock_run:
        result = runner.invoke(app, ["init", "/tmp/test-project"])
    mock_run.assert_called_once()


# --- HK-01 / HK-02: _get_service singleton invalidation and path forwarding ---


def _make_mock_cm(mock_cm_cls: MagicMock) -> MagicMock:
    """Configure mock ConnectionManager to return a fresh mock connection each call."""
    def _cm_factory(path: str) -> MagicMock:
        instance = MagicMock()
        instance.get_connection.return_value = MagicMock()
        return instance
    mock_cm_cls.side_effect = _cm_factory
    return mock_cm_cls


def test_get_service_invalidates_on_path_change():
    """_get_service("/a") then _get_service("/b") must create two separate services."""
    original_svc = cli_module._svc
    original_svc_path = getattr(cli_module, "_svc_path", None)
    try:
        cli_module._svc = None
        cli_module._svc_path = None
        with patch.object(cli_module, "ConnectionManager") as mock_cm_cls, \
             patch.object(cli_module, "ensure_schema"), \
             patch.object(cli_module, "SynappsService") as mock_svc_cls:
            mock_cm_cls.return_value.get_connection.return_value = MagicMock()
            mock_svc_cls.side_effect = lambda conn: MagicMock()

            _get_service("/project-a")
            _get_service("/project-b")

            assert mock_cm_cls.call_count == 2, (
                "ConnectionManager must be called twice for two different paths"
            )
            calls = [c[0][0] for c in mock_cm_cls.call_args_list]
            assert "/project-a" in calls
            assert "/project-b" in calls
    finally:
        cli_module._svc = original_svc
        if hasattr(cli_module, "_svc_path"):
            cli_module._svc_path = original_svc_path


def test_get_service_reuses_for_same_path():
    """_get_service("/a") called twice must NOT create two separate services."""
    original_svc = cli_module._svc
    original_svc_path = getattr(cli_module, "_svc_path", None)
    try:
        cli_module._svc = None
        cli_module._svc_path = None
        with patch.object(cli_module, "ConnectionManager") as mock_cm_cls, \
             patch.object(cli_module, "ensure_schema"), \
             patch.object(cli_module, "SynappsService"):
            mock_cm_cls.return_value.get_connection.return_value = MagicMock()

            _get_service("/project-a")
            _get_service("/project-a")

            assert mock_cm_cls.call_count == 1, (
                "ConnectionManager must be called only once for the same path"
            )
    finally:
        cli_module._svc = original_svc
        if hasattr(cli_module, "_svc_path"):
            cli_module._svc_path = original_svc_path


def test_get_service_invalidates_when_path_changes_from_none():
    """_get_service(None) then _get_service("/b") must create a new service."""
    original_svc = cli_module._svc
    original_svc_path = getattr(cli_module, "_svc_path", None)
    try:
        cli_module._svc = None
        cli_module._svc_path = None
        with patch.object(cli_module, "ConnectionManager") as mock_cm_cls, \
             patch.object(cli_module, "ensure_schema"), \
             patch.object(cli_module, "SynappsService") as mock_svc_cls, \
             patch("synapps.cli.app.Path") as mock_path:
            mock_path.cwd.return_value = Path("/mock/cwd")
            mock_cm_cls.return_value.get_connection.return_value = MagicMock()
            mock_svc_cls.side_effect = lambda conn: MagicMock()

            _get_service(None)
            _get_service("/project-b")

            assert mock_cm_cls.call_count == 2, (
                "ConnectionManager must be called twice when path changes"
            )
    finally:
        cli_module._svc = original_svc
        if hasattr(cli_module, "_svc_path"):
            cli_module._svc_path = original_svc_path


def test_status_with_path_passes_to_get_service():
    """status --path /some/project must pass resolved path to _get_service."""
    svc = _svc()
    svc.get_index_status.return_value = None
    captured_paths = []

    def fake_get_service(path=None):
        captured_paths.append(path)
        return svc

    with patch("synapps.cli.app._get_service", side_effect=fake_get_service):
        runner.invoke(app, ["status", "--path", "/some/project"])

    assert any(p is not None and "some" in p for p in captured_paths), (
        f"Expected resolved path passed to _get_service, got: {captured_paths}"
    )


def test_delete_passes_path_to_get_service():
    """delete command must pass resolved path to _get_service."""
    svc = _svc()
    captured_paths = []

    def fake_get_service(path=None):
        captured_paths.append(path)
        return svc

    with patch("synapps.cli.app._get_service", side_effect=fake_get_service):
        runner.invoke(app, ["delete", "/some/project"])

    assert any(p is not None and "some" in p for p in captured_paths), (
        f"Expected resolved path passed to _get_service, got: {captured_paths}"
    )


def test_watch_passes_path_to_get_service():
    """watch command must pass resolved path to _get_service."""
    svc = _svc()
    captured_paths = []

    def fake_get_service(path=None):
        captured_paths.append(path)
        return svc

    # watch blocks on time.sleep; interrupt it immediately
    import time
    with patch("synapps.cli.app._get_service", side_effect=fake_get_service), \
         patch("time.sleep", side_effect=KeyboardInterrupt):
        runner.invoke(app, ["watch", "/some/project"])

    assert any(p is not None and "some" in p for p in captured_paths), (
        f"Expected resolved path passed to _get_service, got: {captured_paths}"
    )
