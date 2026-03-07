from unittest.mock import MagicMock, call
from synapse.graph.schema import ensure_schema


def test_ensure_schema_creates_indices() -> None:
    mock_conn = MagicMock()
    ensure_schema(mock_conn)
    calls = [str(c) for c in mock_conn.execute.call_args_list]
    # Verify at least one index per major node type
    assert any("File" in c for c in calls)
    assert any("Class" in c for c in calls)
    assert any("Method" in c for c in calls)
