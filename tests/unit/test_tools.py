import importlib
import inspect
import json
from unittest.mock import MagicMock, create_autospec

from synapps.service import SynappsService

from synapps.mcp.tools import _GRAPH_SCHEMA


def test_get_schema_has_expected_top_level_keys():
    assert set(_GRAPH_SCHEMA.keys()) == {"node_labels", "relationship_types", "notes"}
    assert "Class" in _GRAPH_SCHEMA["node_labels"]
    assert "Interface" in _GRAPH_SCHEMA["node_labels"]
    assert "CALLS" in _GRAPH_SCHEMA["relationship_types"]


def test_get_schema_tool_returns_schema():
    registered = {}
    real_mcp = MagicMock()
    real_mcp.tool.return_value = lambda f: registered.__setitem__(f.__name__, f) or f
    from synapps.mcp.tools import register_tools
    register_tools(real_mcp, create_autospec(SynappsService))

    result = registered["get_schema"]()
    assert result is _GRAPH_SCHEMA


def _register(service):
    """Register tools and return a dict of {fn_name: fn} for direct testing."""
    registered = {}
    mcp = MagicMock()
    mcp.tool.return_value = lambda f: registered.__setitem__(f.__name__, f) or f
    from synapps.mcp.tools import register_tools
    register_tools(mcp, service)
    return registered


def test_list_projects_has_description():
    """list_projects must have a docstring so FastMCP generates a tool description."""
    fns = _register(create_autospec(SynappsService))
    assert fns["list_projects"].__doc__, "list_projects must have a docstring"


def test_find_usages_tool_delegates_to_service() -> None:
    service = create_autospec(SynappsService)
    service.find_usages.return_value = "## Usages of Ns.Svc (Class)\n\n0 type references"
    fns = _register(service)
    result = fns["find_usages"]("Ns.Svc")
    service.find_usages.assert_called_once_with("Ns.Svc", True, limit=0)
    assert "(Class)" in result


def test_find_usages_tool_passes_exclude_flag() -> None:
    service = create_autospec(SynappsService)
    service.find_usages.return_value = "## Usages of Ns.M (Method)\n\n0 callers"
    fns = _register(service)
    fns["find_usages"]("Ns.M", exclude_test_callers=False)
    service.find_usages.assert_called_once_with("Ns.M", False, limit=0)


def test_graph_schema_has_overrides_relationship() -> None:
    assert "OVERRIDES" in _GRAPH_SCHEMA["relationship_types"]


def test_graph_schema_method_has_language_property() -> None:
    assert "language" in _GRAPH_SCHEMA["node_labels"]["Method"]


def test_graph_schema_method_has_is_async_flag() -> None:
    assert "is_async" in _GRAPH_SCHEMA["node_labels"]["Method"]


def test_graph_schema_method_has_is_classmethod_flag() -> None:
    assert "is_classmethod" in _GRAPH_SCHEMA["node_labels"]["Method"]


def test_graph_schema_has_imports_relationship() -> None:
    assert "IMPORTS" in _GRAPH_SCHEMA["relationship_types"]


def test_graph_schema_nodes_have_language_property() -> None:
    # Repository uses 'languages' (list) for polyglot support; all others use 'language' (string)
    assert "languages" in _GRAPH_SCHEMA["node_labels"]["Repository"], "Repository missing 'languages'"
    for label in ("File", "Class", "Interface", "Method", "Property", "Field"):
        assert "language" in _GRAPH_SCHEMA["node_labels"][label], f"{label} missing 'language'"


def test_tool_docstrings_contain_disambiguation_cues():
    """Verify that key tools have disambiguation guidance in their docstrings."""
    service = create_autospec(SynappsService)
    fns = _register(service)

    # get_context_for should indicate it's the recommended starting point
    assert "recommended starting point" in fns["get_context_for"].__doc__.lower()

    # execute_query should indicate it's a last resort
    assert "last resort" in fns["execute_query"].__doc__.lower()

    # find_usages should describe what it does
    assert "find all code that uses a symbol" in fns["find_usages"].__doc__.lower()

    # search_symbols should mention discovering names for other tools
    assert "discover" in fns["search_symbols"].__doc__.lower()


def test_graph_schema_notes_include_python_kinds() -> None:
    notes_text = " ".join(_GRAPH_SCHEMA["notes"])
    assert "module" in notes_text
    assert "function" in notes_text


# --- summary tool tests ---

def test_summary_action_get() -> None:
    service = create_autospec(SynappsService)
    service.get_summary.return_value = "A summary"
    fns = _register(service)
    result = fns["summary"](action="get", full_name="Ns.Cls")
    service.get_summary.assert_called_once_with("Ns.Cls")
    assert result == "A summary"


def test_summary_action_set() -> None:
    service = create_autospec(SynappsService)
    fns = _register(service)
    result = fns["summary"](action="set", full_name="Ns.Cls", content="My summary")
    service.set_summary.assert_called_once_with("Ns.Cls", "My summary")
    assert "saved" in result.lower()


def test_summary_action_list() -> None:
    service = create_autospec(SynappsService)
    service.list_summarized.return_value = [{"full_name": "Ns.Cls"}]
    fns = _register(service)
    result = fns["summary"](action="list")
    service.list_summarized.assert_called_once_with(None)
    assert isinstance(result, list)


def test_summary_set_missing_params() -> None:
    service = create_autospec(SynappsService)
    fns = _register(service)
    result = fns["summary"](action="set", full_name=None, content=None)
    assert "error" in result.lower()
    service.set_summary.assert_not_called()


def test_summary_get_missing_full_name() -> None:
    service = create_autospec(SynappsService)
    fns = _register(service)
    result = fns["summary"](action="get", full_name=None)
    assert "error" in result.lower()
    service.get_summary.assert_not_called()


# --- find_callees depth tests ---

def test_find_callees_with_depth_delegates_to_get_call_depth() -> None:
    service = create_autospec(SynappsService)
    service.get_call_depth.return_value = {"root": "Ns.M", "callees": [], "depth_limit": 3}
    fns = _register(service)
    result = fns["find_callees"](full_name="Ns.M", depth=3)
    service.get_call_depth.assert_called_once_with("Ns.M", 3)
    service.find_callees.assert_not_called()
    assert result["depth_limit"] == 3


def test_find_callees_without_depth_uses_normal_path() -> None:
    service = create_autospec(SynappsService)
    service.find_callees.return_value = [{"name": "callee"}]
    fns = _register(service)
    result = fns["find_callees"](full_name="Ns.M")
    service.find_callees.assert_called_once_with("Ns.M", True, limit=50)
    service.get_call_depth.assert_not_called()


# --- find_usages kind/breakdown tests ---

def test_find_usages_with_kind_delegates_to_type_references() -> None:
    service = create_autospec(SynappsService)
    service.find_type_references.return_value = [{"symbol": {"full_name": "Ns.X"}, "kind": "parameter"}]
    fns = _register(service)
    result = fns["find_usages"](full_name="Ns.Cls", kind="parameter")
    service.find_type_references.assert_called_once_with("Ns.Cls", kind="parameter", limit=0)
    service.find_usages.assert_not_called()


# --- list_projects path filter tests ---

def test_list_projects_with_path_returns_index_status() -> None:
    service = create_autospec(SynappsService)
    service.get_index_status.return_value = {"path": "/my/proj", "file_count": 10}
    fns = _register(service)
    result = fns["list_projects"](path="/my/proj")
    service.get_index_status.assert_called_once_with("/my/proj")
    service.list_projects.assert_not_called()
    assert result["file_count"] == 10
    assert "synapps_mcp_version" in result


def test_list_projects_without_path_returns_all() -> None:
    service = create_autospec(SynappsService)
    service.list_projects.return_value = [{"path": "/a"}, {"path": "/b"}]
    fns = _register(service)
    result = fns["list_projects"]()
    service.list_projects.assert_called_once()
    assert "synapps_mcp_version" in result
    assert len(result["projects"]) == 2


# --- HTTP endpoint tool tests ---

def test_find_http_endpoints_delegates_to_service() -> None:
    service = create_autospec(SynappsService)
    service.find_http_endpoints.return_value = [
        {"route": "/api/items", "http_method": "GET", "handler_full_name": "ItemsController.GetAll",
         "file_path": "src/Controllers/Items.cs", "line": 15, "language": "csharp", "has_server_handler": True}
    ]
    fns = _register(service)
    result = fns["find_http_endpoints"](route="items")
    service.find_http_endpoints.assert_called_once_with("items", None, None, limit=50)
    assert result[0]["has_server_handler"] is True
    assert result[0]["route"] == "/api/items"


def test_find_http_endpoints_passes_all_params() -> None:
    service = create_autospec(SynappsService)
    service.find_http_endpoints.return_value = []
    fns = _register(service)
    fns["find_http_endpoints"](route="/api", http_method="POST", language="python", limit=10)
    service.find_http_endpoints.assert_called_once_with("/api", "POST", "python", limit=10)


def test_find_http_endpoints_trace_delegates_to_service() -> None:
    service = create_autospec(SynappsService)
    service.trace_http_dependency.return_value = {
        "route": "/api/items", "http_method": "GET", "has_server_handler": True,
        "server_handler": {"full_name": "ItemsController.GetAll", "file_path": "src/Controllers/Items.cs", "line": 15, "language": "csharp"},
        "client_callers": [],
    }
    fns = _register(service)
    result = fns["find_http_endpoints"](route="/api/items", http_method="GET", trace=True)
    service.trace_http_dependency.assert_called_once_with("/api/items", "GET")
    service.find_http_endpoints.assert_not_called()
    assert result["has_server_handler"] is True
    assert result["server_handler"]["full_name"] == "ItemsController.GetAll"


def test_find_http_endpoints_trace_no_server_handler() -> None:
    service = create_autospec(SynappsService)
    service.trace_http_dependency.return_value = {
        "route": "/api/external", "http_method": "GET", "has_server_handler": False,
        "server_handler": None, "client_callers": [{"full_name": "MyService.fetchData", "file_path": "src/service.ts", "line": 42, "language": "typescript"}],
    }
    fns = _register(service)
    result = fns["find_http_endpoints"](route="/api/external", http_method="GET", trace=True)
    assert result["has_server_handler"] is False
    assert result["server_handler"] is None
    assert len(result["client_callers"]) == 1


def test_find_http_endpoints_trace_requires_route_and_method() -> None:
    service = create_autospec(SynappsService)
    fns = _register(service)
    result = fns["find_http_endpoints"](route="/api/items", trace=True)
    assert "error" in result
    service.trace_http_dependency.assert_not_called()


def test_trace_http_dependency_not_registered() -> None:
    """trace_http_dependency was merged into find_http_endpoints(trace=True) and must not exist as a separate tool."""
    fns = _register(create_autospec(SynappsService))
    assert "trace_http_dependency" not in fns


def test_graph_schema_no_experimental_note() -> None:
    for note in _GRAPH_SCHEMA["notes"]:
        assert "experimental" not in note.lower(), f"Experimental language still in schema note: {note}"


# --- read_symbol tool tests ---

def test_read_symbol_delegates_to_service() -> None:
    service = create_autospec(SynappsService)
    service.read_symbol.return_value = "// src/foo.py:10\ndef foo(): pass"
    fns = _register(service)
    result = fns["read_symbol"](full_name="mod.foo")
    service.read_symbol.assert_called_once_with("mod.foo", max_lines=100)
    assert "foo" in result


def test_read_symbol_returns_not_found_when_service_returns_none() -> None:
    service = create_autospec(SynappsService)
    service.read_symbol.return_value = None
    fns = _register(service)
    result = fns["read_symbol"](full_name="mod.missing")
    assert result == "Symbol not found."


def test_read_symbol_passes_max_lines() -> None:
    service = create_autospec(SynappsService)
    service.read_symbol.return_value = "// src/foo.py:10\ndef foo(): pass"
    fns = _register(service)
    fns["read_symbol"](full_name="mod.foo", max_lines=-1)
    service.read_symbol.assert_called_once_with("mod.foo", max_lines=-1)


# --- assess_impact tool tests ---

def test_assess_impact_delegates_to_service() -> None:
    service = create_autospec(SynappsService)
    service.assess_impact.return_value = "## Direct Callers\n\nNo direct callers found."
    fns = _register(service)
    result = fns["assess_impact"](full_name="mod.Cls.method")
    service.assess_impact.assert_called_once_with("mod.Cls.method")
    assert "Direct Callers" in result


def test_assess_impact_returns_error_string_on_value_error() -> None:
    service = create_autospec(SynappsService)
    service.assess_impact.side_effect = ValueError("Ambiguous name 'method' — matches: A.method, B.method")
    fns = _register(service)
    result = fns["assess_impact"](full_name="method")
    assert "Ambiguous" in result
    assert isinstance(result, str)


# --- get_context_for uses members_only ---

def test_get_context_for_passes_members_only() -> None:
    service = create_autospec(SynappsService)
    service.get_context_for.return_value = "## Members: Ns.Cls\n\n- method()"
    service._staleness_warning.return_value = None
    fns = _register(service)
    fns["get_context_for"](full_name="Ns.Cls", members_only=True)
    service.get_context_for.assert_called_once_with("Ns.Cls", members_only=True, max_lines=200)


# --- removed tools absence test ---

def test_removed_tools_not_registered() -> None:
    fns = _register(create_autospec(SynappsService))
    removed = {"set_summary", "get_summary", "list_summarized", "get_call_depth",
                "find_type_references", "find_type_impact", "get_index_status",
                "find_interface_contract", "audit_architecture", "check_environment",
                "delete_project", "summarize_from_graph", "trace_http_dependency"}
    present = removed & set(fns.keys())
    assert not present, f"Removed tools still registered: {present}"


# --- deprecated tool stub tests ---

def test_find_dependencies_returns_deprecation_error() -> None:
    fns = _register(create_autospec(SynappsService))
    result = fns["find_dependencies"](full_name="Ns.Foo")
    assert isinstance(result, str)
    assert "removed" in result.lower()
    assert "get_context_for" in result


def test_get_hierarchy_returns_deprecation_error() -> None:
    fns = _register(create_autospec(SynappsService))
    result = fns["get_hierarchy"](full_name="Ns.IFoo")
    assert isinstance(result, str)
    assert "removed" in result.lower()
    assert "get_context_for" in result


def test_find_tests_for_returns_deprecation_error() -> None:
    fns = _register(create_autospec(SynappsService))
    result = fns["find_tests_for"](full_name="Ns.Foo.bar")
    assert isinstance(result, str)
    assert "removed" in result.lower()
    assert "assess_impact" in result


def test_find_entry_points_returns_deprecation_error() -> None:
    fns = _register(create_autospec(SynappsService))
    result = fns["find_entry_points"](full_name="Ns.Foo.bar")
    assert isinstance(result, str)
    assert "removed" in result.lower()
    assert "get_architecture" in result


# --- bench logging tests (INST-03) ---

def test_bench_wrap_writes_jsonl_record(tmp_path, monkeypatch) -> None:
    import synapps.mcp.tools as tools_mod
    from synapps.mcp.tools import _bench_wrap

    log_file = tmp_path / "bench.jsonl"
    monkeypatch.setattr(tools_mod, "_BENCH_LOG", str(log_file))

    def my_tool(full_name: str = "") -> str:
        return "hello world"

    wrapped = _bench_wrap(my_tool, "my_tool")
    result = wrapped(full_name="test")

    assert result == "hello world"
    lines = log_file.read_text().strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["tool"] == "my_tool"
    assert record["bytes"] == len("hello world".encode("utf-8"))
    assert record["args"]["full_name"] == "test"
    assert record["ms"] >= 0
    assert record["ts"] > 0


def test_bench_wrap_handles_none_result(tmp_path, monkeypatch) -> None:
    import synapps.mcp.tools as tools_mod
    from synapps.mcp.tools import _bench_wrap

    log_file = tmp_path / "bench.jsonl"
    monkeypatch.setattr(tools_mod, "_BENCH_LOG", str(log_file))

    def my_tool() -> None:
        return None

    wrapped = _bench_wrap(my_tool, "my_tool")
    wrapped()

    record = json.loads(log_file.read_text().strip())
    assert record["bytes"] == 4  # len("null")


def test_register_tools_activates_bench_logging(tmp_path, monkeypatch) -> None:
    import synapps.mcp.tools as tools_mod

    log_file = tmp_path / "bench.jsonl"
    monkeypatch.setattr(tools_mod, "_BENCH_LOG", str(log_file))

    mcp = MagicMock()
    original_tool = mcp.tool

    tools_mod.register_tools(mcp, create_autospec(SynappsService))

    # When bench logging is active, mcp.tool is replaced by _instrumented_tool
    assert mcp.tool is not original_tool


# --- instructions content tests (INST-01, INST-02) ---

def test_instructions_contain_primary_tools_section() -> None:
    from synapps.mcp.instructions import SERVER_INSTRUCTIONS
    assert "PRIMARY TOOLS" in SERVER_INSTRUCTIONS


def test_instructions_primary_tools_list() -> None:
    from synapps.mcp.instructions import SERVER_INSTRUCTIONS
    assert "read_symbol" in SERVER_INSTRUCTIONS
    assert "search_symbols" in SERVER_INSTRUCTIONS
    assert "find_usages" in SERVER_INSTRUCTIONS


def test_instructions_contain_grep_replacement_mappings() -> None:
    from synapps.mcp.instructions import SERVER_INSTRUCTIONS
    lower = SERVER_INSTRUCTIONS.lower()
    assert "instead of" in lower


def test_instructions_no_stale_scope_references() -> None:
    from synapps.mcp.instructions import SERVER_INSTRUCTIONS
    assert "scope=" not in SERVER_INSTRUCTIONS
    assert 'scope="' not in SERVER_INSTRUCTIONS


# --- get_context_for parameter shape tests (restoring Phase 18 tests) ---

def test_get_context_for_tool_no_scope_param() -> None:
    fns = _register(create_autospec(SynappsService))
    sig = inspect.signature(fns["get_context_for"])
    assert "scope" not in sig.parameters


def test_get_context_for_tool_has_members_only_param() -> None:
    fns = _register(create_autospec(SynappsService))
    sig = inspect.signature(fns["get_context_for"])
    assert "members_only" in sig.parameters
    assert sig.parameters["members_only"].default is False
