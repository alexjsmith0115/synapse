"""Unit tests for concurrent ReferencesResolver processing.

Verifies that max_workers parameter enables concurrent method processing,
that all methods are processed correctly, that thread-safety is maintained
for pending_calls accumulation, and that the default sequential behavior
(max_workers=1) is preserved.

Patches: find_enclosing_method_ast, batch_upsert_calls, batch_upsert_module_calls.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from synapps.indexer.references_resolver import ReferencesResolver
from synapps.indexer.tree_sitter_util import ParsedFile


# ---------------------------------------------------------------------------
# Helpers (mirror patterns from test_references_resolver.py)
# ---------------------------------------------------------------------------

def _make_ls(root: str = "/proj") -> MagicMock:
    ls = MagicMock()
    ls.repository_root_path = root
    ls.open_file.return_value.__enter__ = MagicMock(return_value=None)
    ls.open_file.return_value.__exit__ = MagicMock(return_value=False)
    return ls


def _make_parsed_file(file_path: str) -> ParsedFile:
    pf = MagicMock(spec=ParsedFile)
    pf.file_path = file_path
    return pf


def _make_ref(abs_path: str, line_0: int, col_0: int) -> dict:
    return {
        "absolutePath": abs_path,
        "range": {
            "start": {"line": line_0, "character": col_0},
            "end": {"line": line_0, "character": col_0 + 5},
        },
    }


def _make_resolver(
    ls: MagicMock | None = None,
    parsed_cache: dict | None = None,
    symbol_map: dict | None = None,
    per_request_timeout: float = 30.0,
    symbol_col_map: dict | None = None,
    module_name_resolver=None,
    max_workers: int = 1,
) -> tuple[ReferencesResolver, MagicMock]:
    conn = MagicMock()
    if ls is None:
        ls = _make_ls()
    if parsed_cache is None:
        parsed_cache = {}
    if symbol_map is None:
        symbol_map = {}
    resolver = ReferencesResolver(
        conn=conn,
        ls=ls,
        parsed_cache=parsed_cache,
        symbol_map=symbol_map,
        per_request_timeout=per_request_timeout,
        symbol_col_map=symbol_col_map,
        module_name_resolver=module_name_resolver,
        max_workers=max_workers,
    )
    return resolver, conn


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestConcurrentProcessing:
    def test_max_workers_parameter_accepted(self):
        """ReferencesResolver must accept and store max_workers."""
        resolver, _ = _make_resolver(max_workers=4)
        assert resolver._max_workers == 4

    def test_max_workers_clamped_to_one_for_zero_or_negative(self):
        """max_workers <= 0 must be clamped to 1."""
        resolver_zero, _ = _make_resolver(max_workers=0)
        assert resolver_zero._max_workers == 1

        resolver_neg, _ = _make_resolver(max_workers=-3)
        assert resolver_neg._max_workers == 1

    def test_default_max_workers_is_one(self):
        """Default max_workers=1 preserves sequential behavior."""
        resolver, _ = _make_resolver()
        assert resolver._max_workers == 1

    def test_concurrent_processing_completes_all_methods(self):
        """All methods processed when using concurrent workers (max_workers=2, 4 methods)."""
        ls = _make_ls(root="/proj")
        symbol_map = {
            ("/proj/a.py", 10): "pkg.A.method_one",
            ("/proj/a.py", 20): "pkg.A.method_two",
            ("/proj/b.py", 5):  "pkg.B.run",
            ("/proj/b.py", 15): "pkg.B.setup",
        }
        parsed_cache = {
            "/proj/a.py": _make_parsed_file("/proj/a.py"),
            "/proj/b.py": _make_parsed_file("/proj/b.py"),
        }
        ls.request_references.return_value = []

        resolver, _ = _make_resolver(
            ls=ls, parsed_cache=parsed_cache, symbol_map=symbol_map, max_workers=2,
        )

        with patch("synapps.indexer.references_resolver.batch_upsert_calls"), \
             patch("synapps.indexer.references_resolver.batch_upsert_module_calls"):
            resolver.resolve()

        assert resolver._stats.methods_processed == 4

    def test_thread_safety_of_pending_calls(self):
        """Concurrent workers must not corrupt pending_calls list (no data loss)."""
        # 20 methods, each with one reference attributed to a distinct caller
        # max_workers=4 — all 20 should produce edges without data corruption
        ls = _make_ls(root="/proj")

        num_methods = 20
        symbol_map = {
            ("/proj/file.py", i + 1): f"pkg.Module.method_{i}"
            for i in range(num_methods)
        }
        parsed_cache = {"/proj/file.py": _make_parsed_file("/proj/file.py")}

        # Each method has one reference from a unique caller in caller.py.
        # request_references is called with (rel_path, line_0, col).
        # Caller lines are offset by 1000 to avoid collision with callee declaration lines.
        # line_0 is 0-based; methods are at lines 1..num_methods (1-based), so line_0 = i.
        def _make_refs_for_method(rel_path, line_0, col):
            # line_0 is 0-based declaration line; method_i is at 1-based line i+1
            return [_make_ref("/proj/caller.py", 1000 + line_0, 0)]

        ls.request_references.side_effect = _make_refs_for_method

        resolver, _ = _make_resolver(
            ls=ls, parsed_cache=parsed_cache, symbol_map=symbol_map, max_workers=4,
        )

        # Each reference is attributed to a unique caller.
        # ref line_0 is 1000 + method_declaration_line_0 (0-based).
        def _find_enclosing(abs_path, line_0, col_0, parsed_cache, symbol_map):
            return f"pkg.Caller.caller_{line_0}"

        collected_calls: list[dict] = []

        def _capture_upsert(conn, rows):
            collected_calls.extend(rows)

        with patch(
            "synapps.indexer.references_resolver.find_enclosing_method_ast",
            side_effect=_find_enclosing,
        ), patch(
            "synapps.indexer.references_resolver.batch_upsert_calls",
            side_effect=_capture_upsert,
        ), patch(
            "synapps.indexer.references_resolver.batch_upsert_module_calls",
        ):
            resolver.resolve()

        # All 20 methods must have been processed and produced edges
        assert resolver._stats.methods_processed == num_methods

        # Collect all unique (caller, callee) pairs written
        unique_pairs = {(r["caller"], r["callee"]) for r in collected_calls}

        # Each method should have exactly one edge written — none lost due to race conditions
        assert len(unique_pairs) == num_methods, (
            f"Expected {num_methods} unique caller-callee pairs, got {len(unique_pairs)}. "
            "Data may have been lost due to thread-safety issues."
        )

    def test_sequential_and_concurrent_produce_same_edge_count(self):
        """Sequential (max_workers=1) and concurrent (max_workers=4) must write the same edges."""
        ls = _make_ls(root="/proj")
        symbol_map = {
            ("/proj/a.py", 10): "pkg.A.alpha",
            ("/proj/a.py", 20): "pkg.A.beta",
            ("/proj/b.py", 5):  "pkg.B.gamma",
        }
        parsed_cache = {
            "/proj/a.py": _make_parsed_file("/proj/a.py"),
            "/proj/b.py": _make_parsed_file("/proj/b.py"),
        }

        # Each method yields a single reference from a unique caller
        ref_table = {
            "pkg.A.alpha": [_make_ref("/proj/c.py", 100, 0)],
            "pkg.A.beta":  [_make_ref("/proj/c.py", 200, 0)],
            "pkg.B.gamma": [_make_ref("/proj/c.py", 300, 0)],
        }

        def _refs_by_name(rel_path, line_0, col):
            # Identify method by line (1-based in symbol_map)
            line_1 = line_0 + 1
            abs_path = "/proj/" + rel_path
            full_name = symbol_map.get((abs_path, line_1), "")
            return ref_table.get(full_name, [])

        ls.request_references.side_effect = _refs_by_name

        caller_name_by_line = {100: "pkg.C.call_alpha", 200: "pkg.C.call_beta", 300: "pkg.C.call_gamma"}

        def _find_enclosing(abs_path, line_0, col_0, parsed_cache, symbol_map):
            return caller_name_by_line.get(line_0)

        def _run_resolver(workers: int) -> list[dict]:
            ls.reset_mock()
            ls.repository_root_path = "/proj"
            ls.open_file.return_value.__enter__ = MagicMock(return_value=None)
            ls.open_file.return_value.__exit__ = MagicMock(return_value=False)
            ls.request_references.side_effect = _refs_by_name

            resolver, _ = _make_resolver(
                ls=ls, parsed_cache=parsed_cache, symbol_map=symbol_map, max_workers=workers,
            )
            collected: list[dict] = []

            with patch(
                "synapps.indexer.references_resolver.find_enclosing_method_ast",
                side_effect=_find_enclosing,
            ), patch(
                "synapps.indexer.references_resolver.batch_upsert_calls",
                side_effect=lambda conn, rows: collected.extend(rows),
            ), patch(
                "synapps.indexer.references_resolver.batch_upsert_module_calls",
            ):
                resolver.resolve()

            return collected

        sequential_edges = _run_resolver(1)
        concurrent_edges = _run_resolver(4)

        seq_pairs = {(r["caller"], r["callee"]) for r in sequential_edges}
        con_pairs = {(r["caller"], r["callee"]) for r in concurrent_edges}

        assert seq_pairs == con_pairs, (
            f"Sequential produced {seq_pairs}, concurrent produced {con_pairs}"
        )
