"""LSP references-based CALLS edge resolver.

ReferencesResolver iterates all method symbols in the symbol_map, calls
request_references for each via the LSPResolverBackend, attributes each
reference to its enclosing method via AST parent-chain traversal, and writes
CALLS edges in batches via batch_upsert_calls.

This is the shared infrastructure for Phase 6 of v2.1.  Individual languages
activate this path by returning None from create_call_extractor(), which causes
the indexer to skip SymbolResolver-based call extraction and dispatch here instead.
"""
from __future__ import annotations

import concurrent.futures
import logging
import os
import time
from typing import TYPE_CHECKING, Callable

from synapps.graph.edges import batch_upsert_calls, batch_upsert_module_calls
from synapps.indexer.tree_sitter_util import _is_in_type_checking_block, find_enclosing_method_ast

if TYPE_CHECKING:
    from synapps.graph.connection import GraphConnection
    from synapps.indexer.tree_sitter_util import ParsedFile
    from synapps.lsp.interface import LSPResolverBackend

log = logging.getLogger(__name__)

_DEFAULT_TIMEOUT: float = 30.0
_FLUSH_BATCH_SIZE: int = 200


class _RefStats:
    """Accumulates per-resolution stats for summary logging."""
    __slots__ = (
        "methods_processed",
        "methods_timed_out",
        "refs_seen",
        "refs_attributed",
        "refs_attributed_as_module_calls",
        "refs_skipped_none_scope",
        "refs_skipped_self",
        "edges_written",
    )

    def __init__(self) -> None:
        self.methods_processed: int = 0
        self.methods_timed_out: int = 0
        self.refs_seen: int = 0
        self.refs_attributed: int = 0
        self.refs_attributed_as_module_calls: int = 0
        self.refs_skipped_none_scope: int = 0
        self.refs_skipped_self: int = 0
        self.edges_written: int = 0


class ReferencesResolver:
    """Resolve CALLS edges using LSP textDocument/references for all indexed methods.

    Design: invert the direction of call indexing relative to SymbolResolver.
    Instead of scanning each file for call sites and asking LSP "what does this
    call point to?", we ask LSP "who calls this method?" for every indexed method.
    This captures method groups, delegate arguments, and variable assignments that
    tree-sitter AST scanning misses.
    """

    def __init__(
        self,
        conn: GraphConnection,
        ls: LSPResolverBackend,
        parsed_cache: dict[str, ParsedFile],
        symbol_map: dict[tuple[str, int], str],
        per_request_timeout: float = _DEFAULT_TIMEOUT,
        symbol_col_map: dict[tuple[str, int], int] | None = None,
        module_name_resolver: Callable[[str], str | None] | None = None,
    ) -> None:
        self._conn = conn
        self._ls = ls
        self._parsed_cache = parsed_cache
        self._symbol_map = symbol_map
        self._timeout = per_request_timeout
        # Maps (file_path, line_1) -> 0-based column of the symbol name start.
        # Used to pass the correct character position to request_references so
        # strict language servers (e.g. Roslyn/C#) resolve the symbol correctly.
        self._symbol_col_map: dict[tuple[str, int], int] = symbol_col_map or {}
        self._module_name_resolver = module_name_resolver
        self._pending_calls: list[dict] = []
        self._pending_module_calls: list[dict] = []
        self._stats = _RefStats()

    def resolve(self) -> None:
        """Run the full references-based CALLS resolution pass."""
        start = time.monotonic()
        self._prewarm_workspace()

        # Collect all method symbols: (abs_file_path, line_1, full_name)
        methods: list[tuple[str, int, str]] = [
            (file_path, line_1, full_name)
            for (file_path, line_1), full_name in self._symbol_map.items()
        ]
        log.info(
            "ReferencesResolver: %d method symbols to process, %d files in cache",
            len(methods), len(self._parsed_cache),
        )

        for file_path, line_1, full_name in methods:
            self._process_method(file_path, line_1, full_name)

        # Flush any remaining pending calls (method-level and module-level)
        if self._pending_calls or self._pending_module_calls:
            self._flush()

        elapsed = time.monotonic() - start
        s = self._stats
        log.info(
            "ReferencesResolver complete in %.1fs — %d methods processed, %d timed out, "
            "%d refs seen, %d attributed, %d module-level attributed, "
            "%d skipped (no scope), %d skipped (self-ref), %d edges written",
            elapsed,
            s.methods_processed, s.methods_timed_out,
            s.refs_seen, s.refs_attributed, s.refs_attributed_as_module_calls,
            s.refs_skipped_none_scope, s.refs_skipped_self,
            s.edges_written,
        )

    def _prewarm_workspace(self) -> None:
        """Open every file in parsed_cache via open_file to ensure LSP has loaded them.

        TypeScript and Python language servers require didOpen notifications before
        request_references can return results for those files.  We use the safe
        enter+exit pattern (not a persistent context) so the file is opened once
        and immediately released.
        """
        root = self._ls.repository_root_path
        for abs_path in self._parsed_cache:
            rel = os.path.relpath(abs_path, root)
            try:
                with self._ls.open_file(rel):
                    pass
            except Exception:
                log.debug("open_file failed during pre-warm for %s — skipping", rel)

    def _process_method(self, file_path: str, line_1: int, callee_full_name: str) -> None:
        """Request all references to one method and attribute each to a caller."""
        root = self._ls.repository_root_path
        rel_path = os.path.relpath(file_path, root)

        # LSP uses 0-based line numbers; column comes from selectionRange so strict
        # language servers (e.g. Roslyn/C#) resolve the symbol name, not whitespace.
        col = self._symbol_col_map.get((file_path, line_1), 0)
        refs = self._request_references_with_timeout(rel_path, line_1 - 1, col, callee_full_name)
        if refs is None:
            return

        self._stats.methods_processed += 1
        self._stats.refs_seen += len(refs)

        for ref in refs:
            self._attribute_reference(ref, callee_full_name, file_path, line_1)

    def _request_references_with_timeout(
        self,
        rel_path: str,
        line_0: int,
        col: int,
        callee_name: str,
    ) -> list[dict] | None:
        """Call request_references with a per-request timeout.

        col should be the 0-based character position of the symbol name on the
        declaration line (from selectionRange.start.character). Strict language
        servers such as Roslyn require the cursor to be on the name, not on
        leading whitespace.

        Returns None on timeout or exception (method is skipped).
        """
        t0 = time.monotonic()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            fut = executor.submit(self._ls.request_references, rel_path, line_0, col)
            try:
                return fut.result(timeout=self._timeout)
            except concurrent.futures.TimeoutError:
                elapsed = time.monotonic() - t0
                log.warning(
                    "ReferencesResolver: request_references timed out after %.1fs for %s — skipping",
                    elapsed, callee_name,
                )
                self._stats.methods_timed_out += 1
                return None
            except Exception:
                log.warning(
                    "ReferencesResolver: request_references raised for %s",
                    callee_name, exc_info=True,
                )
                return None

    def _attribute_reference(
        self,
        ref: dict,
        callee_full_name: str,
        callee_file_path: str,
        callee_line_1: int,
    ) -> None:
        """Attribute one reference location to its enclosing method and queue a CALLS edge."""
        abs_path: str = ref.get("absolutePath", "")
        ref_range = ref.get("range", {})
        ref_start = ref_range.get("start", {})
        ref_line_0: int = ref_start.get("line", 0)
        ref_col_0: int = ref_start.get("character", 0)

        # Self-reference guard (D-12): discard the reference that points at the
        # declaration line of the callee itself.  This is not a call — it's the
        # symbol definition that the language server always includes in its response.
        if abs_path == callee_file_path and ref_line_0 + 1 == callee_line_1:
            self._stats.refs_skipped_self += 1
            return

        caller_full_name = find_enclosing_method_ast(
            abs_path, ref_line_0, ref_col_0, self._parsed_cache, self._symbol_map,
        )
        if caller_full_name is None:
            if not self._try_attribute_as_module_call(abs_path, ref_line_0, ref_col_0, callee_full_name):
                # Reference is in import zone or module-level code — no enclosing method
                self._stats.refs_skipped_none_scope += 1
            return

        self._pending_calls.append({
            "caller": caller_full_name,
            "callee": callee_full_name,
            "line": ref_line_0 + 1,
            "col": ref_col_0,
        })
        self._stats.refs_attributed += 1

        if len(self._pending_calls) >= _FLUSH_BATCH_SIZE:
            self._flush()

    def _try_attribute_as_module_call(
        self,
        abs_path: str,
        ref_line_0: int,
        ref_col_0: int,
        callee_full_name: str,
    ) -> bool:
        """Attempt to attribute a module-level reference to a module CALLS edge.

        Returns True if the reference was attributed (caller queued), False otherwise.
        References inside TYPE_CHECKING blocks are excluded — they are compile-time only.
        """
        if self._module_name_resolver is None:
            return False
        if _is_in_type_checking_block(abs_path, ref_line_0, ref_col_0, self._parsed_cache):
            return False
        module_full_name = self._module_name_resolver(abs_path)
        if module_full_name is None:
            return False
        self._pending_module_calls.append({
            "caller": module_full_name,
            "callee": callee_full_name,
            "line": ref_line_0 + 1,
            "col": ref_col_0,
        })
        self._stats.refs_attributed_as_module_calls += 1
        return True

    def _flush(self) -> None:
        """Deduplicate pending calls by (caller, callee) pair and write to graph."""
        if self._pending_calls:
            # Keep first occurrence of each (caller, callee) pair — duplicates arise
            # when the same method is called multiple times in the same caller or when
            # the same reference location is returned more than once by the language server.
            seen: set[tuple[str, str]] = set()
            deduplicated: list[dict] = []
            for row in self._pending_calls:
                key = (row["caller"], row["callee"])
                if key not in seen:
                    seen.add(key)
                    deduplicated.append(row)

            batch_upsert_calls(self._conn, deduplicated)
            self._stats.edges_written += len(deduplicated)
            self._pending_calls = []

        if self._pending_module_calls:
            seen_module: set[tuple[str, str]] = set()
            deduplicated_module: list[dict] = []
            for row in self._pending_module_calls:
                key = (row["caller"], row["callee"])
                if key not in seen_module:
                    seen_module.add(key)
                    deduplicated_module.append(row)

            batch_upsert_module_calls(self._conn, deduplicated_module)
            self._stats.edges_written += len(deduplicated_module)
            self._pending_module_calls = []
