from unittest.mock import MagicMock
from falkordb.node import Node as FalkorNode
from synapse.graph.queries import list_summarized


def _node(labels, props):
    return FalkorNode(node_id=1, labels=labels, properties=props)


def _conn(return_value):
    conn = MagicMock()
    conn.query.return_value = return_value
    return conn


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
