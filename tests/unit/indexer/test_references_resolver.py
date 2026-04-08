"""Unit tests for ReferencesResolver — LSP references-based CALLS edge writer.

All LSP calls are mocked; only the resolver's logic is under test.
Patches: find_enclosing_method_ast, batch_upsert_calls.
"""
# BUG-col-01: ReferencesResolver must use per-method column from symbol_col_map,
# not hardcode column=0. Roslyn (C#) requires the cursor to be on the symbol name.
from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from unittest.mock import MagicMock, call, patch

import pytest
import tree_sitter_python as tspython
from tree_sitter import Language, Parser

from synapps.indexer.references_resolver import ReferencesResolver
from synapps.indexer.tree_sitter_util import ParsedFile

_PY_LANGUAGE = Language(tspython.language())
_py_parser = Parser(_PY_LANGUAGE)


def _make_real_parsed_file(source: str, file_path: str = "/test/file.py") -> ParsedFile:
    """Create a real ParsedFile with a parsed tree-sitter tree."""
    tree = _py_parser.parse(bytes(source, "utf-8"))
    return ParsedFile(file_path=file_path, source=source, tree=tree)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ls(root: str = "/proj") -> MagicMock:
    """Create a mock LSPResolverBackend with the minimum required interface."""
    ls = MagicMock()
    ls.repository_root_path = root
    # open_file must work as a context manager
    ls.open_file.return_value.__enter__ = MagicMock(return_value=None)
    ls.open_file.return_value.__exit__ = MagicMock(return_value=False)
    return ls


def _make_parsed_file(file_path: str) -> ParsedFile:
    """Create a stub ParsedFile (tree is not used by ReferencesResolver directly)."""
    pf = MagicMock(spec=ParsedFile)
    pf.file_path = file_path
    return pf


def _make_ref(abs_path: str, line_0: int, col_0: int) -> dict:
    """Create a reference dict matching the LSP Location structure used by request_references."""
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
) -> tuple[ReferencesResolver, MagicMock]:
    """Build a ReferencesResolver with a mocked GraphConnection."""
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
    )
    return resolver, conn


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPrewarm:
    def test_prewarm_opens_all_files(self):
        """resolve() must call open_file once for each file in parsed_cache."""
        ls = _make_ls(root="/proj")
        parsed_cache = {
            "/proj/a.py": _make_parsed_file("/proj/a.py"),
            "/proj/b.py": _make_parsed_file("/proj/b.py"),
        }
        ls.request_references.return_value = []

        resolver, _ = _make_resolver(ls=ls, parsed_cache=parsed_cache, symbol_map={})

        with patch("synapps.indexer.references_resolver.batch_upsert_calls"):
            resolver.resolve()

        assert ls.open_file.call_count == 2
        opened_args = {c.args[0] for c in ls.open_file.call_args_list}
        assert "a.py" in opened_args
        assert "b.py" in opened_args

    def test_prewarm_continues_on_open_file_failure(self):
        """A failure in open_file for one file must not prevent processing others."""
        ls = _make_ls(root="/proj")
        parsed_cache = {
            "/proj/a.py": _make_parsed_file("/proj/a.py"),
            "/proj/b.py": _make_parsed_file("/proj/b.py"),
        }
        # First open_file raises, second succeeds
        ls.open_file.side_effect = [RuntimeError("LSP failed"), MagicMock(
            __enter__=MagicMock(return_value=None),
            __exit__=MagicMock(return_value=False),
        )]
        ls.request_references.return_value = []

        resolver, _ = _make_resolver(ls=ls, parsed_cache=parsed_cache, symbol_map={})

        # Must not raise
        with patch("synapps.indexer.references_resolver.batch_upsert_calls"):
            resolver.resolve()


class TestIteration:
    def test_iterates_all_method_symbols(self):
        """request_references must be called once per entry in symbol_map."""
        ls = _make_ls(root="/proj")
        symbol_map = {
            ("/proj/a.py", 10): "pkg.A.method_one",
            ("/proj/a.py", 20): "pkg.A.method_two",
            ("/proj/b.py", 5):  "pkg.B.run",
        }
        parsed_cache = {
            "/proj/a.py": _make_parsed_file("/proj/a.py"),
            "/proj/b.py": _make_parsed_file("/proj/b.py"),
        }
        ls.request_references.return_value = []

        resolver, _ = _make_resolver(ls=ls, parsed_cache=parsed_cache, symbol_map=symbol_map)

        with patch("synapps.indexer.references_resolver.batch_upsert_calls"):
            resolver.resolve()

        assert ls.request_references.call_count == 3


class TestSelfReferenceGuard:
    def test_self_reference_guard_discards_declaration_line_ref(self):
        """A reference on the callee's own declaration line must be discarded."""
        ls = _make_ls(root="/proj")
        # Method at line 10 (1-based) → 0-based is 9
        symbol_map = {("/proj/a.py", 10): "pkg.A.foo"}
        parsed_cache = {"/proj/a.py": _make_parsed_file("/proj/a.py")}

        # Reference on line 9 (0-based) == declaration line 10 (1-based) → self-reference
        ls.request_references.return_value = [_make_ref("/proj/a.py", 9, 4)]

        resolver, _ = _make_resolver(ls=ls, parsed_cache=parsed_cache, symbol_map=symbol_map)

        with patch("synapps.indexer.references_resolver.find_enclosing_method_ast") as mock_find, \
             patch("synapps.indexer.references_resolver.batch_upsert_calls") as mock_batch:
            resolver.resolve()

        # find_enclosing_method_ast must NOT be called for the self-reference
        mock_find.assert_not_called()
        # No CALLS edge written
        if mock_batch.called:
            for c in mock_batch.call_args_list:
                assert len(c.args[1]) == 0

    def test_recursive_call_not_filtered(self):
        """A reference from the same method on a DIFFERENT line is a recursive call and must produce a CALLS edge."""
        ls = _make_ls(root="/proj")
        # Method at line 10 (1-based)
        symbol_map = {("/proj/a.py", 10): "pkg.A.foo"}
        parsed_cache = {"/proj/a.py": _make_parsed_file("/proj/a.py")}

        # Reference on line 15 (0-based) — different line, same file as callee
        ls.request_references.return_value = [_make_ref("/proj/a.py", 15, 4)]

        resolver, _ = _make_resolver(ls=ls, parsed_cache=parsed_cache, symbol_map=symbol_map)

        with patch("synapps.indexer.references_resolver.find_enclosing_method_ast",
                   return_value="pkg.A.foo") as mock_find, \
             patch("synapps.indexer.references_resolver.batch_upsert_calls") as mock_batch:
            resolver.resolve()

        # find_enclosing_method_ast must be called (not filtered as self-ref)
        mock_find.assert_called()
        # CALLS edge must be written (recursive call is valid)
        mock_batch.assert_called()
        all_batches = [row for c in mock_batch.call_args_list for row in c.args[1]]
        assert any(r["caller"] == "pkg.A.foo" and r["callee"] == "pkg.A.foo" for r in all_batches)


class TestNoneScopeFilter:
    def test_none_scope_skipped(self):
        """When find_enclosing_method_ast returns None, the reference is skipped (module-level code)."""
        ls = _make_ls(root="/proj")
        symbol_map = {("/proj/a.py", 10): "pkg.A.foo"}
        parsed_cache = {"/proj/a.py": _make_parsed_file("/proj/a.py")}

        # Reference from a different file at module level
        ls.request_references.return_value = [_make_ref("/proj/b.py", 2, 0)]

        resolver, _ = _make_resolver(ls=ls, parsed_cache=parsed_cache, symbol_map=symbol_map)

        with patch("synapps.indexer.references_resolver.find_enclosing_method_ast",
                   return_value=None), \
             patch("synapps.indexer.references_resolver.batch_upsert_calls") as mock_batch:
            resolver.resolve()

        # No CALLS edge must be written
        if mock_batch.called:
            all_rows = [row for c in mock_batch.call_args_list for row in c.args[1]]
            assert len(all_rows) == 0


class TestCallsEdgeProduction:
    def test_attributed_reference_produces_calls_edge(self):
        """A valid reference attributed to an enclosing method must write a CALLS edge with correct keys."""
        ls = _make_ls(root="/proj")
        symbol_map = {("/proj/a.py", 10): "pkg.A.callee"}
        parsed_cache = {"/proj/a.py": _make_parsed_file("/proj/a.py")}

        # Reference from b.py at line 5, col 8
        ls.request_references.return_value = [_make_ref("/proj/b.py", 5, 8)]

        resolver, _ = _make_resolver(ls=ls, parsed_cache=parsed_cache, symbol_map=symbol_map)

        with patch("synapps.indexer.references_resolver.find_enclosing_method_ast",
                   return_value="pkg.B.caller"), \
             patch("synapps.indexer.references_resolver.batch_upsert_calls") as mock_batch:
            resolver.resolve()

        mock_batch.assert_called()
        all_rows = [row for c in mock_batch.call_args_list for row in c.args[1]]
        assert len(all_rows) == 1
        row = all_rows[0]
        assert row["caller"] == "pkg.B.caller"
        assert row["callee"] == "pkg.A.callee"
        assert row["line"] == 6   # 0-based ref_line + 1
        assert row["col"] == 8

    def test_method_group_reference_produces_calls_edge(self):
        """A non-call reference (delegate assignment, variable binding) also produces a CALLS edge.

        Per D-11: request_references returns all reference types; no special handling needed.
        A reference at any position that resolves to an enclosing method is treated identically.
        """
        ls = _make_ls(root="/proj")
        symbol_map = {("/proj/handlers.py", 3): "pkg.Handlers.on_event"}
        parsed_cache = {"/proj/handlers.py": _make_parsed_file("/proj/handlers.py")}

        # Reference at a delegate-assignment position (e.g., button.Click += on_event)
        ls.request_references.return_value = [_make_ref("/proj/wiring.py", 20, 15)]

        resolver, _ = _make_resolver(ls=ls, parsed_cache=parsed_cache, symbol_map=symbol_map)

        with patch("synapps.indexer.references_resolver.find_enclosing_method_ast",
                   return_value="pkg.Wiring.setup"), \
             patch("synapps.indexer.references_resolver.batch_upsert_calls") as mock_batch:
            resolver.resolve()

        mock_batch.assert_called()
        all_rows = [row for c in mock_batch.call_args_list for row in c.args[1]]
        assert any(r["caller"] == "pkg.Wiring.setup" and r["callee"] == "pkg.Handlers.on_event"
                   for r in all_rows)


class TestTimeout:
    def test_timeout_skips_method(self):
        """When request_references takes longer than per_request_timeout, the method is skipped gracefully."""
        ls = _make_ls(root="/proj")
        symbol_map = {("/proj/a.py", 10): "pkg.A.slow_method"}
        parsed_cache = {"/proj/a.py": _make_parsed_file("/proj/a.py")}

        # request_references blocks for longer than the timeout
        def _slow_refs(*args, **kwargs):
            time.sleep(5.0)  # much longer than timeout
            return []

        ls.request_references.side_effect = _slow_refs

        # Use a very short timeout so the test doesn't actually wait 5 seconds
        resolver, _ = _make_resolver(
            ls=ls, parsed_cache=parsed_cache, symbol_map=symbol_map,
            per_request_timeout=0.05,
        )

        with patch("synapps.indexer.references_resolver.batch_upsert_calls") as mock_batch:
            resolver.resolve()  # must not raise or hang

        # No CALLS edges written
        if mock_batch.called:
            all_rows = [row for c in mock_batch.call_args_list for row in c.args[1]]
            assert len(all_rows) == 0

        # methods_timed_out stat must be non-zero
        assert resolver._stats.methods_timed_out >= 1


class TestDeduplication:
    def test_deduplication_same_caller_callee_produces_one_edge(self):
        """Multiple references from the same caller to the same callee produce only one CALLS edge."""
        ls = _make_ls(root="/proj")
        symbol_map = {("/proj/a.py", 10): "pkg.A.helper"}
        parsed_cache = {"/proj/a.py": _make_parsed_file("/proj/a.py")}

        # Three references to the same callee — all from the same caller
        ls.request_references.return_value = [
            _make_ref("/proj/b.py", 5, 4),
            _make_ref("/proj/b.py", 8, 4),
            _make_ref("/proj/b.py", 12, 4),
        ]

        resolver, _ = _make_resolver(ls=ls, parsed_cache=parsed_cache, symbol_map=symbol_map)

        with patch("synapps.indexer.references_resolver.find_enclosing_method_ast",
                   return_value="pkg.B.consumer"), \
             patch("synapps.indexer.references_resolver.batch_upsert_calls") as mock_batch:
            resolver.resolve()

        all_rows = [row for c in mock_batch.call_args_list for row in c.args[1]]
        # Deduplicate by (caller, callee) — must result in exactly 1 unique pair
        unique_pairs = {(r["caller"], r["callee"]) for r in all_rows}
        assert unique_pairs == {("pkg.B.consumer", "pkg.A.helper")}
        assert len(unique_pairs) == 1


class TestSymbolColMap:
    """BUG-col-01: ReferencesResolver must pass per-method column from symbol_col_map to
    request_references so strict language servers (e.g. Roslyn/C#) can resolve the symbol
    from its name position rather than from leading whitespace at column 0.
    """

    def test_uses_column_from_symbol_col_map(self):
        """request_references must be called with the column stored in symbol_col_map, not 0."""
        ls = _make_ls(root="/proj")
        # Method at line 77 (1-based); name starts at column 17 (e.g. `    private void UpdateTimestamps()`)
        symbol_map = {("/proj/Ctx.cs", 77): "Ns.Ctx.UpdateTimestamps"}
        parsed_cache = {"/proj/Ctx.cs": _make_parsed_file("/proj/Ctx.cs")}
        symbol_col_map = {("/proj/Ctx.cs", 77): 17}

        ls.request_references.return_value = []

        resolver, _ = _make_resolver(
            ls=ls, parsed_cache=parsed_cache,
            symbol_map=symbol_map, symbol_col_map=symbol_col_map,
        )

        with patch("synapps.indexer.references_resolver.batch_upsert_calls"):
            resolver.resolve()

        assert ls.request_references.call_count == 1
        args = ls.request_references.call_args
        # args: (rel_path, line_0, col)
        _rel, line_0, col = args[0]
        assert line_0 == 76, f"Expected 0-based line 76, got {line_0}"
        assert col == 17, (
            f"Expected col=17 from symbol_col_map, got col={col}. "
            "Roslyn/C# requires the cursor on the symbol name to return references."
        )

    def test_defaults_to_column_zero_when_no_col_map_entry(self):
        """When no symbol_col_map entry exists for a method, column defaults to 0."""
        ls = _make_ls(root="/proj")
        symbol_map = {("/proj/a.cs", 10): "Ns.A.method"}
        parsed_cache = {"/proj/a.cs": _make_parsed_file("/proj/a.cs")}
        # Empty col map — no entry for this method
        symbol_col_map: dict = {}

        ls.request_references.return_value = []

        resolver, _ = _make_resolver(
            ls=ls, parsed_cache=parsed_cache,
            symbol_map=symbol_map, symbol_col_map=symbol_col_map,
        )

        with patch("synapps.indexer.references_resolver.batch_upsert_calls"):
            resolver.resolve()

        assert ls.request_references.call_count == 1
        _rel, _line, col = ls.request_references.call_args[0]
        assert col == 0

    def test_omitting_col_map_defaults_to_column_zero(self):
        """When symbol_col_map is None (not provided), column falls back to 0."""
        ls = _make_ls(root="/proj")
        symbol_map = {("/proj/a.cs", 5): "Ns.A.run"}
        parsed_cache = {"/proj/a.cs": _make_parsed_file("/proj/a.cs")}

        ls.request_references.return_value = []

        # No symbol_col_map passed at all
        resolver, _ = _make_resolver(
            ls=ls, parsed_cache=parsed_cache, symbol_map=symbol_map,
        )

        with patch("synapps.indexer.references_resolver.batch_upsert_calls"):
            resolver.resolve()

        assert ls.request_references.call_count == 1
        _rel, _line, col = ls.request_references.call_args[0]
        assert col == 0


class TestModuleLevelCalls:
    """Module-level call attribution tests.

    When find_enclosing_method_ast returns None and module_name_resolver is available,
    the reference should produce a CALLS edge via batch_upsert_module_calls.
    """

    def test_module_level_ref_produces_module_calls_edge(self):
        """Reference at module scope with module_name_resolver returns a module name produces a CALLS edge."""
        ls = _make_ls(root="/proj")
        symbol_map = {("/proj/app.py", 10): "pkg.app_module.create_app"}
        parsed_cache = {"/proj/app.py": _make_parsed_file("/proj/app.py")}
        callee = "pkg.app_module.create_app"
        module_name_resolver = lambda fp: "pkg.app_module" if fp == "/proj/caller.py" else None

        # Reference at module scope in caller.py (line 3, col 6)
        ls.request_references.return_value = [_make_ref("/proj/caller.py", 3, 6)]

        resolver, _ = _make_resolver(
            ls=ls, parsed_cache=parsed_cache, symbol_map=symbol_map,
            module_name_resolver=module_name_resolver,
        )

        with patch("synapps.indexer.references_resolver.find_enclosing_method_ast",
                   return_value=None), \
             patch("synapps.indexer.references_resolver.batch_upsert_module_calls") as mock_module_calls, \
             patch("synapps.indexer.references_resolver.batch_upsert_calls"):
            resolver.resolve()

        mock_module_calls.assert_called()
        all_rows = [row for c in mock_module_calls.call_args_list for row in c.args[1]]
        assert len(all_rows) == 1
        row = all_rows[0]
        assert row["caller"] == "pkg.app_module"
        assert row["callee"] == callee
        assert row["line"] == 4   # 0-based ref_line + 1
        assert row["col"] == 6

    def test_module_call_increments_refs_attributed_as_module_calls_not_skipped(self):
        """refs_attributed_as_module_calls increments (not refs_skipped_none_scope) when module call attributed."""
        ls = _make_ls(root="/proj")
        symbol_map = {("/proj/app.py", 10): "pkg.app.create_app"}
        parsed_cache = {"/proj/app.py": _make_parsed_file("/proj/app.py")}
        module_name_resolver = lambda fp: "pkg.main_module"

        ls.request_references.return_value = [_make_ref("/proj/main.py", 5, 0)]

        resolver, _ = _make_resolver(
            ls=ls, parsed_cache=parsed_cache, symbol_map=symbol_map,
            module_name_resolver=module_name_resolver,
        )

        with patch("synapps.indexer.references_resolver.find_enclosing_method_ast",
                   return_value=None), \
             patch("synapps.indexer.references_resolver.batch_upsert_module_calls"), \
             patch("synapps.indexer.references_resolver.batch_upsert_calls"):
            resolver.resolve()

        assert resolver._stats.refs_attributed_as_module_calls == 1
        assert resolver._stats.refs_skipped_none_scope == 0

    def test_no_module_name_resolver_falls_back_to_skip(self):
        """No module_name_resolver (default None): refs_skipped_none_scope increments, no module calls emitted."""
        ls = _make_ls(root="/proj")
        symbol_map = {("/proj/app.py", 10): "pkg.app.create_app"}
        parsed_cache = {"/proj/app.py": _make_parsed_file("/proj/app.py")}

        ls.request_references.return_value = [_make_ref("/proj/main.py", 5, 0)]

        # No module_name_resolver
        resolver, _ = _make_resolver(
            ls=ls, parsed_cache=parsed_cache, symbol_map=symbol_map,
        )

        with patch("synapps.indexer.references_resolver.find_enclosing_method_ast",
                   return_value=None), \
             patch("synapps.indexer.references_resolver.batch_upsert_module_calls") as mock_module_calls, \
             patch("synapps.indexer.references_resolver.batch_upsert_calls"):
            resolver.resolve()

        mock_module_calls.assert_not_called()
        assert resolver._stats.refs_skipped_none_scope == 1

    def test_module_name_resolver_returns_none_falls_back_to_skip(self):
        """module_name_resolver returns None for unknown file: refs_skipped_none_scope increments."""
        ls = _make_ls(root="/proj")
        symbol_map = {("/proj/app.py", 10): "pkg.app.create_app"}
        parsed_cache = {"/proj/app.py": _make_parsed_file("/proj/app.py")}
        # Always returns None (unknown file)
        module_name_resolver = lambda fp: None

        ls.request_references.return_value = [_make_ref("/proj/main.py", 5, 0)]

        resolver, _ = _make_resolver(
            ls=ls, parsed_cache=parsed_cache, symbol_map=symbol_map,
            module_name_resolver=module_name_resolver,
        )

        with patch("synapps.indexer.references_resolver.find_enclosing_method_ast",
                   return_value=None), \
             patch("synapps.indexer.references_resolver.batch_upsert_module_calls") as mock_module_calls, \
             patch("synapps.indexer.references_resolver.batch_upsert_calls"):
            resolver.resolve()

        mock_module_calls.assert_not_called()
        assert resolver._stats.refs_skipped_none_scope == 1

    def test_module_calls_deduplicated_by_caller_callee(self):
        """Multiple module-level refs to same callee from same module — deduplicated to 1 edge."""
        ls = _make_ls(root="/proj")
        symbol_map = {("/proj/app.py", 10): "pkg.app.create_app"}
        parsed_cache = {"/proj/app.py": _make_parsed_file("/proj/app.py")}
        module_name_resolver = lambda fp: "pkg.main_module"

        # Two refs to the same callee from the same module
        ls.request_references.return_value = [
            _make_ref("/proj/main.py", 5, 0),
            _make_ref("/proj/main.py", 8, 0),
        ]

        resolver, _ = _make_resolver(
            ls=ls, parsed_cache=parsed_cache, symbol_map=symbol_map,
            module_name_resolver=module_name_resolver,
        )

        with patch("synapps.indexer.references_resolver.find_enclosing_method_ast",
                   return_value=None), \
             patch("synapps.indexer.references_resolver.batch_upsert_module_calls") as mock_module_calls, \
             patch("synapps.indexer.references_resolver.batch_upsert_calls"):
            resolver.resolve()

        all_rows = [row for c in mock_module_calls.call_args_list for row in c.args[1]]
        unique_pairs = {(r["caller"], r["callee"]) for r in all_rows}
        assert len(unique_pairs) == 1
        assert ("pkg.main_module", "pkg.app.create_app") in unique_pairs

    def test_final_flush_emits_module_calls(self):
        """Pending module calls below _FLUSH_BATCH_SIZE are flushed at end of resolve()."""
        ls = _make_ls(root="/proj")
        # Only one method in symbol_map — one method processed, one module-level ref
        symbol_map = {("/proj/app.py", 10): "pkg.app.create_app"}
        parsed_cache = {"/proj/app.py": _make_parsed_file("/proj/app.py")}
        module_name_resolver = lambda fp: "pkg.main_module"

        ls.request_references.return_value = [_make_ref("/proj/main.py", 5, 0)]

        resolver, _ = _make_resolver(
            ls=ls, parsed_cache=parsed_cache, symbol_map=symbol_map,
            module_name_resolver=module_name_resolver,
        )

        with patch("synapps.indexer.references_resolver.find_enclosing_method_ast",
                   return_value=None), \
             patch("synapps.indexer.references_resolver.batch_upsert_module_calls") as mock_module_calls, \
             patch("synapps.indexer.references_resolver.batch_upsert_calls"):
            resolver.resolve()

        # batch_upsert_module_calls must have been called (final flush executed)
        mock_module_calls.assert_called()
        all_rows = [row for c in mock_module_calls.call_args_list for row in c.args[1]]
        assert len(all_rows) >= 1


class TestTypeCheckingExclusion:
    """References inside if TYPE_CHECKING: blocks must NOT produce CALLS edges.

    Uses a real ParsedFile (not MagicMock) because _is_in_type_checking_block
    does AST traversal on the actual tree.
    """

    def test_module_level_ref_inside_type_checking_block_is_excluded(self):
        """Reference at module scope inside TYPE_CHECKING block does NOT produce a CALLS edge."""
        source = """\
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    create_app()
"""
        file_path = "/proj/caller.py"
        pf = _make_real_parsed_file(source, file_path=file_path)

        ls = _make_ls(root="/proj")
        symbol_map = {("/proj/app.py", 10): "pkg.app.create_app"}
        parsed_cache = {
            "/proj/app.py": _make_parsed_file("/proj/app.py"),
            file_path: pf,
        }
        module_name_resolver = lambda fp: "pkg.caller_module"

        # Reference at line 2 (0-based), col 4 — inside the TYPE_CHECKING block
        ls.request_references.return_value = [_make_ref(file_path, 2, 4)]

        resolver, _ = _make_resolver(
            ls=ls, parsed_cache=parsed_cache, symbol_map=symbol_map,
            module_name_resolver=module_name_resolver,
        )

        with patch("synapps.indexer.references_resolver.find_enclosing_method_ast",
                   return_value=None), \
             patch("synapps.indexer.references_resolver.batch_upsert_module_calls") as mock_module_calls, \
             patch("synapps.indexer.references_resolver.batch_upsert_calls"):
            resolver.resolve()

        mock_module_calls.assert_not_called()
        assert resolver._stats.refs_skipped_none_scope == 1
