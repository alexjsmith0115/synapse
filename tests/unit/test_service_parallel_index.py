from __future__ import annotations

import threading
from unittest.mock import MagicMock, call, patch

import pytest

from synapps.service import SynappsService


def _make_plugin(name: str, ext: str) -> MagicMock:
    plugin = MagicMock()
    plugin.name = name
    plugin.file_extensions = frozenset({ext})
    lsp = MagicMock()
    plugin.create_lsp_adapter.return_value = lsp
    return plugin


def _make_indexer_mock(http_results: list | None = None) -> MagicMock:
    indexer = MagicMock()
    indexer._http_extraction_results = http_results or []
    return indexer


@pytest.fixture
def conn() -> MagicMock:
    return MagicMock()


class TestParallelIndexing:
    def test_multiple_languages_both_indexed(self, conn: MagicMock) -> None:
        """When multiple plugins are present, both get indexed."""
        py_plugin = _make_plugin("python", ".py")
        ts_plugin = _make_plugin("typescript", ".ts")

        registry = MagicMock()
        registry.detect_with_files.return_value = [
            (py_plugin, ["/project/main.py"]),
            (ts_plugin, ["/project/app.ts"]),
        ]

        indexer_calls: list[str] = []

        def make_indexer(conn, lsp, plugin):
            m = _make_indexer_mock()
            m.index_project.side_effect = lambda *a, **kw: indexer_calls.append(plugin.name)
            return m

        svc = SynappsService(conn, registry=registry)

        with patch("synapps.service.indexing.Indexer", side_effect=make_indexer), \
             patch("synapps.service.indexing.HttpPhase"), \
             patch("synapps.service.indexing.TestsPhase"):
            svc._indexing.index_project("/project")

        assert sorted(indexer_calls) == ["python", "typescript"]

    def test_single_language_no_thread_pool(self, conn: MagicMock) -> None:
        """Single plugin should not create a ThreadPoolExecutor."""
        py_plugin = _make_plugin("python", ".py")

        registry = MagicMock()
        registry.detect_with_files.return_value = [(py_plugin, ["/project/main.py"])]

        indexer_mock = _make_indexer_mock()

        svc = SynappsService(conn, registry=registry)

        with patch("synapps.service.indexing.Indexer", return_value=indexer_mock), \
             patch("synapps.service.indexing.TestsPhase"), \
             patch("concurrent.futures.ThreadPoolExecutor") as mock_pool_cls:
            svc._indexing.index_project("/project")

        # ThreadPoolExecutor must not be created for a single language
        mock_pool_cls.assert_not_called()
        indexer_mock.index_project.assert_called_once()

    def test_http_results_collected_from_all_languages(self, conn: MagicMock) -> None:
        """HTTP extraction results from all languages must all be combined."""
        py_plugin = _make_plugin("python", ".py")
        ts_plugin = _make_plugin("typescript", ".ts")

        registry = MagicMock()
        registry.detect_with_files.return_value = [
            (py_plugin, ["/project/main.py"]),
            (ts_plugin, ["/project/app.ts"]),
        ]

        py_results = [MagicMock()]
        ts_results = [MagicMock(), MagicMock()]

        def make_indexer(conn, lsp, plugin):
            if plugin.name == "python":
                return _make_indexer_mock(py_results)
            return _make_indexer_mock(ts_results)

        svc = SynappsService(conn, registry=registry)

        captured_http_results: list = []

        def capture_http_phase(conn_arg, path_arg):
            phase = MagicMock()
            def run(results):
                captured_http_results.extend(results)
            phase.run.side_effect = run
            return phase

        with patch("synapps.service.indexing.Indexer", side_effect=make_indexer), \
             patch("synapps.service.indexing.HttpPhase", side_effect=capture_http_phase), \
             patch("synapps.service.indexing.TestsPhase"):
            svc._indexing.index_project("/project")

        # All http results from both languages must reach HttpPhase.run
        all_results_passed = []
        for r in captured_http_results:
            if hasattr(r, "endpoint_defs"):
                pass
            all_results_passed.append(r)

        # py_results has 1, ts_results has 2 → total 3 items must be in combined list
        assert len(captured_http_results) == len(py_results) + len(ts_results)

    def test_post_indexing_phases_run_after_all_languages(self, conn: MagicMock) -> None:
        """HTTP and TESTS phases must run only after all language indexing completes."""
        py_plugin = _make_plugin("python", ".py")
        ts_plugin = _make_plugin("typescript", ".ts")

        registry = MagicMock()
        registry.detect_with_files.return_value = [
            (py_plugin, ["/project/main.py"]),
            (ts_plugin, ["/project/app.ts"]),
        ]

        call_order: list[str] = []
        lock = threading.Lock()

        def make_indexer(conn, lsp, plugin):
            m = _make_indexer_mock([MagicMock()])  # give each a result so HttpPhase runs
            def record_index(*a, **kw):
                with lock:
                    call_order.append(f"index:{plugin.name}")
            m.index_project.side_effect = record_index
            return m

        http_phase_mock = MagicMock()
        http_phase_mock.run.side_effect = lambda *a, **kw: call_order.append("http_phase")

        tests_phase_mock = MagicMock()
        tests_phase_mock.run.side_effect = lambda: call_order.append("tests_phase")

        svc = SynappsService(conn, registry=registry)

        with patch("synapps.service.indexing.Indexer", side_effect=make_indexer), \
             patch("synapps.service.indexing.HttpPhase", return_value=http_phase_mock), \
             patch("synapps.service.indexing.TestsPhase", return_value=tests_phase_mock):
            svc._indexing.index_project("/project")

        # Both languages must have been indexed before either post-phase ran
        http_idx = call_order.index("http_phase")
        tests_idx = call_order.index("tests_phase")
        python_idx = call_order.index("index:python")
        ts_idx = call_order.index("index:typescript")

        assert python_idx < http_idx, "python indexing must precede HTTP phase"
        assert ts_idx < http_idx, "typescript indexing must precede HTTP phase"
        assert http_idx < tests_idx, "HTTP phase must precede TESTS phase"
