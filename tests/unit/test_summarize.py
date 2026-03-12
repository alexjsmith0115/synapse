from unittest.mock import MagicMock, patch

from synapse.service import SynapseService


def test_summarize_from_graph_formats_output() -> None:
    conn = MagicMock()
    service = SynapseService(conn)

    with patch("synapse.service.resolve_full_name", return_value="Ns.MyService"):
        with patch("synapse.service.get_symbol") as mock_sym:
            mock_sym.return_value = {
                "full_name": "Ns.MyService",
                "name": "MyService",
                "kind": "class",
                "file_path": "/proj/MyService.cs",
            }
            with patch("synapse.service.get_implemented_interfaces") as mock_ifaces:
                mock_ifaces.return_value = [{"full_name": "Ns.IMyService"}]
                with patch("synapse.service.get_members_overview") as mock_members:
                    mock_members.return_value = [
                        {"name": "DoA"}, {"name": "DoB"}, {"name": "DoC"},
                    ]
                    with patch.object(service, "find_dependencies", return_value=[
                        {"type": {"full_name": "Ns.DbContext"}},
                    ]):
                        with patch.object(service, "find_type_impact", return_value={
                            "references": [
                                {"full_name": "Ns.Controller.Action", "context": "prod"},
                            ],
                            "prod_count": 1,
                            "test_count": 0,
                        }):
                            result = service.summarize_from_graph("MyService")

    assert result["full_name"] == "Ns.MyService"
    assert "MyService" in result["summary"]
    assert "IMyService" in result["summary"]
    assert result["data"]["method_count"] == 3
    assert "Ns.DbContext" in result["data"]["dependencies"]


def test_summarize_from_graph_unknown_symbol() -> None:
    conn = MagicMock()
    service = SynapseService(conn)

    with patch("synapse.service.resolve_full_name", return_value="Unknown"):
        with patch("synapse.service.get_symbol", return_value=None):
            result = service.summarize_from_graph("Unknown")

    assert result is None
