"""Unit tests for orphan endpoint cleanup in shared-mode graphs."""
from __future__ import annotations

from unittest.mock import MagicMock, call

from synapse.graph.edges import delete_orphan_endpoints


def test_cleanup_removes_repo_contains_edge_and_orphaned_endpoint():
    """When an endpoint has no SERVES/HTTP_CALLS, remove CONTAINS edge and delete endpoint."""
    conn = MagicMock()
    delete_orphan_endpoints(conn, "/project/a")
    # Should execute two queries: remove CONTAINS, then delete fully orphaned
    assert conn.execute.call_count == 2
    first_query = conn.execute.call_args_list[0][0][0]
    second_query = conn.execute.call_args_list[1][0][0]
    # First query removes the repo's CONTAINS edge only (not DETACH DELETE)
    assert "DELETE c" in first_query
    assert "DETACH DELETE" not in first_query
    assert "Repository {path: $repo}" in first_query
    # Second query deletes fully orphaned endpoints (no CONTAINS from any repo)
    # Must be plain DELETE, not DETACH DELETE (no edges should remain)
    assert "DETACH DELETE" not in second_query
    assert "DELETE ep" in second_query
    assert "CONTAINS" in second_query
    assert "SERVES" in second_query
    assert "HTTP_CALLS" in second_query


def test_cleanup_passes_repo_path():
    """Verify repo path is passed as parameter to scoped query."""
    conn = MagicMock()
    delete_orphan_endpoints(conn, "/project/a")
    first_call_params = conn.execute.call_args_list[0][0][1]
    assert first_call_params["repo"] == "/project/a"
