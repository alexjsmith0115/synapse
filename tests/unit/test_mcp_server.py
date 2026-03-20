from pathlib import Path
from unittest.mock import patch, MagicMock

from synapse.mcp.server import main


def test_main_uses_container_manager():
    """Verify MCP server main() routes through ContainerManager with cwd."""
    mock_cm_cls = MagicMock()
    mock_conn = MagicMock()
    mock_cm_cls.return_value.get_connection.return_value = mock_conn

    mock_fastmcp = MagicMock()
    mock_svc_cls = MagicMock()

    with patch("synapse.mcp.server.ContainerManager", mock_cm_cls), \
         patch("synapse.mcp.server.ensure_schema") as mock_ensure, \
         patch("synapse.mcp.server.SynapseService", mock_svc_cls), \
         patch("synapse.mcp.server.FastMCP", return_value=mock_fastmcp), \
         patch("synapse.mcp.server.register_tools") as mock_register, \
         patch("synapse.mcp.server.Path") as mock_path:
        mock_path.cwd.return_value = Path("/mock/project")
        main()

    mock_cm_cls.assert_called_once_with("/mock/project")
    mock_cm_cls.return_value.get_connection.assert_called_once()
    mock_ensure.assert_called_once_with(mock_conn)
    mock_svc_cls.assert_called_once_with(mock_conn)
    mock_register.assert_called_once_with(mock_fastmcp, mock_svc_cls.return_value)
    mock_fastmcp.run.assert_called_once()
