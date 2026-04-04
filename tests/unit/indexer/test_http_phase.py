from __future__ import annotations

from unittest.mock import MagicMock, patch

from synapps.indexer.http.interface import HttpEndpointDef, HttpClientCall, HttpExtractionResult
from synapps.indexer.http_phase import HttpPhase


def _def(route: str, method: str, handler: str, line: int = 1) -> HttpEndpointDef:
    return HttpEndpointDef(route=route, http_method=method, handler_full_name=handler, line=line)


def _mock_conn() -> MagicMock:
    return MagicMock()


def test_phase_creates_endpoint_nodes_and_edges() -> None:
    conn = _mock_conn()
    phase = HttpPhase(conn, repo_path="/repo")

    server_result = HttpExtractionResult(
        endpoint_defs=[HttpEndpointDef("/api/items", "GET", "Ctrl.GetAll", 10)],
    )
    client_result = HttpExtractionResult(
        client_calls=[HttpClientCall("/api/items", "GET", "svc.getAll", 5, 2)],
    )

    phase.run([server_result, client_result])

    # Should have called execute for: endpoint MERGE, CONTAINS, SERVES, HTTP_CALLS
    assert conn.execute.call_count >= 3


def test_phase_is_noop_when_no_results() -> None:
    conn = _mock_conn()
    phase = HttpPhase(conn, repo_path="/repo")
    phase.run([])
    conn.execute.assert_not_called()


def test_phase_handles_unmatched_server_endpoint() -> None:
    conn = _mock_conn()
    phase = HttpPhase(conn, repo_path="/repo")

    result = HttpExtractionResult(
        endpoint_defs=[HttpEndpointDef("/api/items", "GET", "Ctrl.GetAll", 10)],
    )
    phase.run([result])

    # Should still create endpoint and SERVES edge
    assert conn.execute.call_count >= 2


def test_phase_handles_unmatched_client_call() -> None:
    conn = _mock_conn()
    phase = HttpPhase(conn, repo_path="/repo")

    result = HttpExtractionResult(
        client_calls=[HttpClientCall("/external/api", "GET", "svc.fetch", 5, 2)],
    )
    phase.run([result])

    # Should create endpoint and HTTP_CALLS edge
    assert conn.execute.call_count >= 1


def test_rebuild_from_graph_queries_existing_data() -> None:
    conn = _mock_conn()
    conn.query = MagicMock(return_value=[])
    phase = HttpPhase(conn, repo_path="/repo")
    defs, calls = phase.rebuild_from_graph()
    assert defs == []
    assert calls == []
    assert conn.query.call_count == 2


def test_conflict_warning_emitted_once_per_pair() -> None:
    conn = _mock_conn()
    phase = HttpPhase(conn, repo_path="/repo")
    result = HttpExtractionResult(
        endpoint_defs=[
            _def("/api/items", "GET", "CtrlA.GetAll", 10),
            _def("/api/items", "GET", "CtrlB.GetAll", 20),
            _def("/api/items", "GET", "CtrlC.GetAll", 30),
        ],
    )
    with patch("synapps.indexer.http_phase.log") as mock_log:
        phase.run([result])
    assert mock_log.warning.call_count == 1
    warning_msg = mock_log.warning.call_args[0]
    assert any("CtrlA.GetAll" in str(a) for a in warning_msg)
    assert any("CtrlB.GetAll" in str(a) for a in warning_msg)
    assert any("CtrlC.GetAll" in str(a) for a in warning_msg)


def test_no_conflict_warning_for_single_handler() -> None:
    conn = _mock_conn()
    phase = HttpPhase(conn, repo_path="/repo")
    result = HttpExtractionResult(
        endpoint_defs=[_def("/api/items", "GET", "Ctrl.GetAll", 10)],
    )
    with patch("synapps.indexer.http_phase.log") as mock_log:
        phase.run([result])
    mock_log.warning.assert_not_called()


def test_no_conflict_for_different_routes() -> None:
    conn = _mock_conn()
    phase = HttpPhase(conn, repo_path="/repo")
    result = HttpExtractionResult(
        endpoint_defs=[
            _def("/api/items", "GET", "Ctrl.GetItems", 10),
            _def("/api/orders", "GET", "Ctrl.GetOrders", 20),
        ],
    )
    with patch("synapps.indexer.http_phase.log") as mock_log:
        phase.run([result])
    mock_log.warning.assert_not_called()
