from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from synapse.mcp.instructions import SERVER_INSTRUCTIONS
from synapse.mcp.server import main


@pytest.fixture
def _patched_main():
    """Run main() with all external dependencies patched."""
    mock_cm_cls = MagicMock()
    mock_cm_cls.return_value.get_connection.return_value = MagicMock()

    mock_fastmcp = MagicMock()

    with patch("synapse.mcp.server.ContainerManager", mock_cm_cls), \
         patch("synapse.mcp.server.ensure_schema") as mock_ensure, \
         patch("synapse.mcp.server.SynapseService") as mock_svc_cls, \
         patch("synapse.mcp.server.FastMCP", return_value=mock_fastmcp) as mock_fmcp_cls, \
         patch("synapse.mcp.server.register_tools") as mock_register, \
         patch("synapse.mcp.server.Path") as mock_path:
        mock_path.cwd.return_value = Path("/mock/project")
        main()
        yield {
            "cm_cls": mock_cm_cls,
            "ensure": mock_ensure,
            "svc_cls": mock_svc_cls,
            "fmcp_cls": mock_fmcp_cls,
            "fastmcp": mock_fastmcp,
            "register": mock_register,
        }


def test_main_uses_container_manager(_patched_main):
    """Verify MCP server main() routes through ContainerManager with cwd."""
    cm_cls = _patched_main["cm_cls"]
    conn = cm_cls.return_value.get_connection.return_value

    cm_cls.assert_called_once_with("/mock/project")
    cm_cls.return_value.get_connection.assert_called_once()
    _patched_main["ensure"].assert_called_once_with(conn)
    _patched_main["svc_cls"].assert_called_once_with(conn)
    _patched_main["register"].assert_called_once_with(
        _patched_main["fastmcp"], _patched_main["svc_cls"].return_value
    )
    _patched_main["fastmcp"].run.assert_called_once()


def test_main_passes_instructions_to_fastmcp(_patched_main):
    """Verify MCP server passes SERVER_INSTRUCTIONS to FastMCP."""
    instructions = _patched_main["fmcp_cls"].call_args.kwargs["instructions"]
    assert instructions is SERVER_INSTRUCTIONS
