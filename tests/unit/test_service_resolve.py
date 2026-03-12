from unittest.mock import MagicMock, patch

from synapse.service import SynapseService


def _make_service() -> tuple[SynapseService, MagicMock]:
    conn = MagicMock()
    service = SynapseService(conn)
    return service, conn


def test_resolve_single_match_returns_string() -> None:
    service, conn = _make_service()
    node = MagicMock()
    node.properties = {"full_name": "Ns.MyClass", "name": "MyClass", "kind": "class"}
    node.labels = ["Class"]
    conn.query.side_effect = [
        [["Ns.MyClass"]],  # exact match in resolve_full_name
        [[node]],  # get_symbol query returns a node
    ]
    result = service.get_symbol("MyClass")
    assert result is not None
    assert result["full_name"] == "Ns.MyClass"


def test_resolve_ambiguous_raises() -> None:
    service, conn = _make_service()
    conn.query.side_effect = [
        [],  # exact match fails
        [["A.MyClass"], ["B.MyClass"]],  # suffix match returns multiple
    ]
    import pytest
    with pytest.raises(ValueError, match="Ambiguous"):
        service.get_symbol("MyClass")


def test_set_summary_does_not_resolve() -> None:
    """Write operations must not go through resolution."""
    service, conn = _make_service()
    conn.query.return_value = []
    conn.execute.return_value = None
    service.set_summary("ShortName", "some content")
    query_calls = conn.query.call_args_list
    assert len(query_calls) == 0, "set_summary should not call resolve_full_name"
