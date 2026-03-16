from unittest.mock import MagicMock

from synapse.mcp.tools import _GRAPH_SCHEMA


def test_get_schema_has_expected_top_level_keys():
    assert set(_GRAPH_SCHEMA.keys()) == {"node_labels", "relationship_types", "notes"}
    assert "Class" in _GRAPH_SCHEMA["node_labels"]
    assert "Interface" in _GRAPH_SCHEMA["node_labels"]
    assert "CALLS" in _GRAPH_SCHEMA["relationship_types"]


def test_get_schema_tool_returns_schema():
    registered = {}
    real_mcp = MagicMock()
    real_mcp.tool.return_value = lambda f: registered.__setitem__(f.__name__, f) or f
    from synapse.mcp.tools import register_tools
    register_tools(real_mcp, MagicMock())

    result = registered["get_schema"]()
    assert result is _GRAPH_SCHEMA


def _register(service):
    """Register tools and return a dict of {fn_name: fn} for direct testing."""
    registered = {}
    mcp = MagicMock()
    mcp.tool.return_value = lambda f: registered.__setitem__(f.__name__, f) or f
    from synapse.mcp.tools import register_tools
    register_tools(mcp, service)
    return registered


def test_get_symbol_source_node_missing():
    service = MagicMock()
    service.get_symbol_source.return_value = None
    service.get_symbol.return_value = None  # node does not exist
    fns = _register(service)

    result = fns["get_symbol_source"]("Ns.Missing")
    assert result == "Symbol not found: Ns.Missing"


def test_get_symbol_source_stale_index():
    service = MagicMock()
    service.get_symbol_source.return_value = None
    service.get_symbol.return_value = {"full_name": "Ns.Cls"}  # node exists, source missing

    fns = _register(service)

    result = fns["get_symbol_source"]("Ns.Cls")
    assert "re-index" in result.lower()
    assert "Symbol not found" not in result


def test_get_symbol_source_returns_source_when_available():
    service = MagicMock()
    service.get_symbol_source.return_value = "// src/Ns/Cls.cs:5\npublic class Cls {}"
    fns = _register(service)

    result = fns["get_symbol_source"]("Ns.Cls")
    assert result == "// src/Ns/Cls.cs:5\npublic class Cls {}"
    service.get_symbol.assert_not_called()


def test_list_projects_has_description():
    """list_projects must have a docstring so FastMCP generates a tool description."""
    fns = _register(MagicMock())
    assert fns["list_projects"].__doc__, "list_projects must have a docstring"


def test_find_usages_tool_delegates_to_service() -> None:
    service = MagicMock()
    service.find_usages.return_value = {"symbol": "Ns.Svc", "kind": "Class", "type_references": [], "method_callers": {}}
    fns = _register(service)
    result = fns["find_usages"]("Ns.Svc")
    service.find_usages.assert_called_once_with("Ns.Svc", True)
    assert result["kind"] == "Class"


def test_find_usages_tool_passes_exclude_flag() -> None:
    service = MagicMock()
    service.find_usages.return_value = {"symbol": "Ns.M", "kind": "Method", "callers": []}
    fns = _register(service)
    fns["find_usages"]("Ns.M", exclude_test_callers=False)
    service.find_usages.assert_called_once_with("Ns.M", False)
