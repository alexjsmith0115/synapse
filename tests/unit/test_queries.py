import pytest
from unittest.mock import MagicMock
from falkordb.node import Node as FalkorNode
from synapse.graph.queries import find_callers, find_implementations, get_hierarchy, list_summarized, search_symbols, _VALID_KINDS
from synapse.graph.queries import search_symbols as qs_search


def _node(labels, props):
    return FalkorNode(node_id=1, labels=labels, properties=props)


def _conn(return_value):
    conn = MagicMock()
    conn.query.return_value = return_value
    return conn


def test_find_implementations_exact_match_does_not_fallback():
    impl = FalkorNode(node_id=10, labels=["Class"], properties={"full_name": "MyNs.MyClass"})
    conn = _conn([[impl]])
    result = find_implementations(conn, "MyNs.IMyInterface")
    assert len(result) == 1
    assert conn.query.call_count == 1  # no fallback needed


def test_find_implementations_falls_back_to_short_name():
    impl = FalkorNode(node_id=10, labels=["Class"], properties={"full_name": "MyNs.MyClass"})
    conn = MagicMock()
    # First call (exact match) returns empty; second call (suffix fallback) returns result
    conn.query.side_effect = [[], [[impl]]]
    result = find_implementations(conn, "IMyInterface")
    assert len(result) == 1
    assert conn.query.call_count == 2


def test_find_implementations_returns_empty_when_not_found():
    conn = MagicMock()
    conn.query.side_effect = [[], []]
    result = find_implementations(conn, "INotFound")
    assert result == []


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


def test_get_hierarchy_includes_implements():
    iface = FalkorNode(node_id=20, labels=["Interface"], properties={"full_name": "MyNs.IFoo"})
    conn = MagicMock()
    # Three queries: parents, children, implements
    conn.query.side_effect = [[], [], [[iface]]]
    result = get_hierarchy(conn, "MyNs.Foo")
    assert "implements" in result
    assert len(result["implements"]) == 1


def test_get_hierarchy_implements_empty_when_none():
    conn = MagicMock()
    conn.query.side_effect = [[], [], []]
    result = get_hierarchy(conn, "MyNs.Foo")
    assert result["implements"] == []


def test_get_hierarchy_always_has_all_three_keys():
    conn = MagicMock()
    conn.query.side_effect = [[], [], []]
    result = get_hierarchy(conn, "MyNs.Foo")
    assert set(result.keys()) == {"parents", "children", "implements"}


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


def test_search_symbols_namespace_filter():
    node = FalkorNode(node_id=30, labels=["Method"], properties={"full_name": "MyNs.Svc.DoWork", "name": "DoWork"})
    conn = _conn([[node]])
    result = qs_search(conn, "Do", namespace="MyNs.Svc")
    assert len(result) == 1
    cypher = conn.query.call_args[0][0]
    assert "STARTS WITH" in cypher


def test_search_symbols_file_path_filter():
    node = FalkorNode(node_id=31, labels=["Method"], properties={"full_name": "MyNs.Svc.DoWork", "name": "DoWork"})
    conn = _conn([[node]])
    result = qs_search(conn, "Do", file_path="src/Svc.cs")
    assert len(result) == 1
    cypher = conn.query.call_args[0][0]
    assert "file_path" in cypher


def test_search_symbols_combined_filters():
    conn = _conn([])
    qs_search(conn, "Do", kind="Method", namespace="MyNs", file_path="src/Svc.cs")
    cypher = conn.query.call_args[0][0]
    assert "STARTS WITH" in cypher
    assert "file_path" in cypher
    assert "Method" in cypher


def test_search_symbols_no_filters_unchanged():
    conn = _conn([])
    qs_search(conn, "Foo")
    cypher = conn.query.call_args[0][0]
    # Basic query without extra conditions
    assert "CONTAINS" in cypher
