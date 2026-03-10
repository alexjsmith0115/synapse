import pytest
from unittest.mock import MagicMock
from falkordb.node import Node as FalkorNode
from synapse.graph.queries import find_callers, list_summarized, search_symbols, _VALID_KINDS


def _node(labels, props):
    return FalkorNode(node_id=1, labels=labels, properties=props)


def _conn(return_value):
    conn = MagicMock()
    conn.query.return_value = return_value
    return conn


def test_search_symbols_invalid_kind_lists_valid_values():
    conn = _conn([])
    with pytest.raises(ValueError, match="Valid values"):
        search_symbols(conn, "Foo", kind="widget")


def test_search_symbols_interface_kind_is_valid():
    conn = _conn([])
    # Should not raise
    search_symbols(conn, "IRepo", kind="Interface")


def test_valid_kinds_contains_interface():
    assert "Interface" in _VALID_KINDS


def test_find_callers_direct_only_when_disabled():
    direct_caller = _node(["Method"], {"full_name": "A.Direct"})
    conn = _conn([[direct_caller]])
    result = find_callers(conn, "Svc.DoWork", include_interface_dispatch=False)
    assert len(result) == 1
    conn.query.assert_called_once()


def test_find_callers_includes_interface_dispatch_by_default():
    direct_caller_node = FalkorNode(node_id=1, labels=["Method"], properties={"full_name": "A.Direct"})
    iface_caller_node = FalkorNode(node_id=2, labels=["Method"], properties={"full_name": "A.ViaInterface"})
    conn = MagicMock()
    conn.query.side_effect = [[[direct_caller_node]], [[iface_caller_node]]]
    result = find_callers(conn, "Svc.DoWork")
    assert len(result) == 2
    assert conn.query.call_count == 2


def test_find_callers_deduplicates_across_both_queries():
    shared_node_a = FalkorNode(node_id=5, labels=["Method"], properties={"full_name": "A.Both"})
    shared_node_b = FalkorNode(node_id=5, labels=["Method"], properties={"full_name": "A.Both"})
    conn = MagicMock()
    conn.query.side_effect = [[[shared_node_a]], [[shared_node_b]]]
    result = find_callers(conn, "Svc.DoWork")
    assert len(result) == 1


def test_list_summarized_deduplicates():
    # Two distinct Python objects with the same node_id simulate two traversal paths
    # to the same graph node — the real production scenario
    node_a = _node(["Class", "Summarized"], {"full_name": "A.B"})
    node_b = _node(["Class", "Summarized"], {"full_name": "A.B"})
    assert node_a is not node_b  # different objects
    assert node_a.id == node_b.id  # same graph node
    conn = _conn([[node_a], [node_b]])
    result = list_summarized(conn)
    assert len(result) == 1
