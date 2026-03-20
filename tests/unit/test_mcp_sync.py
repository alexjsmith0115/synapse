from unittest.mock import MagicMock

from synapse.indexer.sync import SyncResult


def test_mcp_sync_project_tool():
    """sync_project MCP tool calls service and returns summary string."""
    from synapse.mcp.tools import register_tools

    mock_mcp = MagicMock()
    registered = {}

    def fake_tool():
        def decorator(fn):
            registered[fn.__name__] = fn
            return fn
        return decorator

    mock_mcp.tool = fake_tool
    service = MagicMock()
    service.sync_project.return_value = SyncResult(updated=2, deleted=1, unchanged=50)

    register_tools(mock_mcp, service)

    assert "sync_project" in registered
    result = registered["sync_project"](path="/proj")
    assert "2 updated" in result
    assert "1 deleted" in result
    assert "50 unchanged" in result


def test_mcp_sync_project_returns_error_for_unindexed():
    """sync_project MCP tool returns error string when project not indexed."""
    from synapse.mcp.tools import register_tools

    mock_mcp = MagicMock()
    registered = {}

    def fake_tool():
        def decorator(fn):
            registered[fn.__name__] = fn
            return fn
        return decorator

    mock_mcp.tool = fake_tool
    service = MagicMock()
    service.sync_project.side_effect = ValueError("Project at '/proj' is not indexed.")

    register_tools(mock_mcp, service)

    result = registered["sync_project"](path="/proj")
    assert "Error" in result
    assert "not indexed" in result
