from unittest.mock import MagicMock, patch

from synapse.service import SynapseService


class _MockNode:
    """Minimal neo4j graph.Node stand-in for unit tests."""
    def __init__(self, labels: list[str], props: dict, element_id: str | None = None) -> None:
        self._props = props
        self.labels = frozenset(labels)
        self.element_id = element_id or str(id(self))

    def keys(self): return list(self._props.keys())
    def values(self): return list(self._props.values())
    def items(self): return list(self._props.items())
    def __getitem__(self, key): return self._props[key]
    def __iter__(self): return iter(self._props)
    def __len__(self): return len(self._props)
    def get(self, key, default=None): return self._props.get(key, default)


def _make_service() -> tuple[SynapseService, MagicMock]:
    conn = MagicMock()
    service = SynapseService(conn)
    return service, conn


def test_resolve_single_match_returns_string() -> None:
    service, conn = _make_service()
    node = _MockNode(["Class"], {"full_name": "Ns.MyClass", "name": "MyClass", "kind": "class"})
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
        [["A.MyClass", ["Class"]], ["B.MyClass", ["Class"]]],  # suffix match returns multiple
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
