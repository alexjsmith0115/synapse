from unittest.mock import MagicMock, call
from redis.exceptions import ResponseError
from synapse.graph.schema import ensure_schema


def test_ensure_schema_creates_indices() -> None:
    mock_conn = MagicMock()
    ensure_schema(mock_conn)
    calls = [str(c) for c in mock_conn.execute.call_args_list]
    # Verify at least one index per major node type
    assert any("File" in c for c in calls)
    assert any("Class" in c for c in calls)
    assert any("Method" in c for c in calls)


def test_ensure_schema_tolerates_already_indexed_error() -> None:
    """FalkorDB raises ResponseError when an index already exists on re-index."""
    mock_conn = MagicMock()
    mock_conn.execute.side_effect = ResponseError("Attribute 'path' is already indexed")
    # Should not raise
    ensure_schema(mock_conn)
