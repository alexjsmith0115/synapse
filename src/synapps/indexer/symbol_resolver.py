from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING

from synapps.graph.connection import GraphConnection
from synapps.graph.edges import (
    batch_upsert_calls,
    batch_upsert_module_calls,
    batch_upsert_references,
    upsert_calls,
    upsert_module_calls,
    upsert_references,
)
from synapps.indexer.assignment_ref import AssignmentRef
from synapps.indexer.csharp.csharp_call_extractor import CSharpCallExtractor
from synapps.indexer.csharp.csharp_type_ref_extractor import CSharpTypeRefExtractor
from synapps.indexer.type_ref import TypeRef
from synapps.lsp.interface import LSPResolverBackend
from synapps.lsp.util import build_full_name

if TYPE_CHECKING:
    from tree_sitter import Tree
    from synapps.indexer.tree_sitter_util import ParsedFile

log = logging.getLogger(__name__)

_METHOD_KINDS = {6, 9, 12}  # Method, Constructor, Function
_TYPE_KINDS = {5, 11}  # Class, Interface


def _build_class_lines_per_file(
    class_symbol_map: dict[tuple[str, int], str],
) -> dict[str, list[tuple[int, str]]]:
    """Group and sort class symbol positions by file for efficient enclosing-class lookup."""
    per_file: dict[str, list[tuple[int, str]]] = {}
    for (file_path, line), full_name in class_symbol_map.items():
        per_file.setdefault(file_path, []).append((line, full_name))
    for entries in per_file.values():
        entries.sort()
    return per_file


class _ResolveStats:
    """Accumulates timing and count stats for resolution logging."""
    __slots__ = (
        "calls_resolved", "calls_unresolved", "calls_resolved_via_assignment",
        "calls_resolved_via_import",
        "type_refs_resolved",
        "lsp_definition_time", "lsp_containing_time", "callee_name_time",
        "extraction_calls_time", "extraction_typerefs_time",
    )

    def __init__(self) -> None:
        self.calls_resolved = 0
        self.calls_unresolved = 0
        self.calls_resolved_via_assignment = 0
        self.calls_resolved_via_import = 0
        self.type_refs_resolved = 0
        self.lsp_definition_time = 0.0
        self.lsp_containing_time = 0.0
        self.callee_name_time = 0.0
        self.extraction_calls_time = 0.0
        self.extraction_typerefs_time = 0.0


class SymbolResolver:
    """
    Walks source files once, runs call extraction and type reference extraction,
    then resolves both via LSP and writes CALLS and REFERENCES edges.
    """

    def __init__(
        self,
        conn: GraphConnection,
        ls: LSPResolverBackend,
        call_extractor: CSharpCallExtractor | None = None,
        type_ref_extractor: CSharpTypeRefExtractor | None = None,
        name_to_full_names: dict[str, list[str]] | None = None,
        file_extensions: frozenset[str] | None = None,
        module_full_names: set[str] | None = None,
        assignment_position_map: dict[tuple[str, int], AssignmentRef] | None = None,
        parsed_cache: dict[str, ParsedFile] | None = None,
        class_lines_per_file: dict[str, list[tuple[int, str]]] | None = None,
        import_map: dict[str, dict[str, str]] | None = None,
    ) -> None:
        self._conn = conn
        self._ls = ls
        self._call_extractor = call_extractor or CSharpCallExtractor()
        self._type_ref_extractor = type_ref_extractor
        self._name_to_full_names = name_to_full_names or {}
        self._import_map = import_map or {}
        self._file_extensions = file_extensions or frozenset({".cs"})
        self._module_full_names = module_full_names or set()
        self._assignment_position_map = assignment_position_map or {}
        self._parsed_cache = parsed_cache
        self._class_lines_per_file = class_lines_per_file
        self._unresolved_sites: list[str] = []
        self._callee_name_cache: dict[str, str] = {}
        self._pending_calls: list[dict] = []
        self._pending_module_calls: list[dict] = []
        self._pending_refs: list[dict] = []

    def resolve(
        self,
        root_path: str,
        symbol_map: dict[tuple[str, int], str],
        class_symbol_map: dict[tuple[str, int], str] | None = None,
    ) -> None:
        if self._class_lines_per_file is not None:
            class_lines_per_file = self._class_lines_per_file
        else:
            class_lines_per_file = _build_class_lines_per_file(class_symbol_map or {})

        if self._parsed_cache is not None:
            files = list(self._parsed_cache.keys())
        else:
            files = list(self._iter_files(root_path))
        total_files = len(files)
        log.info("Call/type-ref resolution: %d files to process, %d method symbols in map", total_files, len(symbol_map))

        resolve_start = time.monotonic()
        self._stats = _ResolveStats()

        for i, file_path in enumerate(files, 1):
            if self._parsed_cache and file_path in self._parsed_cache:
                pf = self._parsed_cache[file_path]
                source = pf.source
                tree = pf.tree
            else:
                try:
                    source = Path(file_path).read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    log.warning("Could not read %s", file_path)
                    continue
                tree = self._parse_source(file_path, source)
                if tree is None:
                    continue
            self._resolve_file(file_path, source, tree, symbol_map, class_lines_per_file.get(file_path, []))
            if i % 50 == 0 or i == total_files:
                elapsed = time.monotonic() - resolve_start
                log.info(
                    "Progress: %d/%d files (%.1fs elapsed, %d calls resolved, %d unresolved, %d type refs)",
                    i, total_files, elapsed,
                    self._stats.calls_resolved, self._stats.calls_unresolved, self._stats.type_refs_resolved,
                )

        self._flush_pending()

        elapsed = time.monotonic() - resolve_start
        s = self._stats
        cache_hits = len(self._callee_name_cache)
        log.info(
            "Resolution complete in %.1fs — %d files, %d call sites (%d resolved, %d unresolved, "
            "%d via assignment fallback, %d via import fallback), "
            "%d type refs resolved, %d callee name cache entries. "
            "LSP: %.1fs definition, %.1fs containing_symbol, "
            "%.1fs callee_name. Extraction: %.1fs calls, %.1fs type_refs",
            elapsed, total_files,
            s.calls_resolved + s.calls_unresolved, s.calls_resolved, s.calls_unresolved,
            s.calls_resolved_via_assignment, s.calls_resolved_via_import,
            s.type_refs_resolved, cache_hits,
            s.lsp_definition_time, s.lsp_containing_time,
            s.callee_name_time, s.extraction_calls_time, s.extraction_typerefs_time,
        )

    def resolve_single_file(
        self,
        file_path: str,
        symbol_map: dict[tuple[str, int], str],
        class_symbol_map: dict[tuple[str, int], str] | None = None,
    ) -> None:
        if not hasattr(self, "_stats"):
            self._stats = _ResolveStats()

        if self._class_lines_per_file is not None:
            class_lines_per_file = self._class_lines_per_file
        else:
            class_lines_per_file = _build_class_lines_per_file(class_symbol_map or {})

        if self._parsed_cache and file_path in self._parsed_cache:
            pf = self._parsed_cache[file_path]
            source = pf.source
            tree = pf.tree
        else:
            try:
                source = Path(file_path).read_text(encoding="utf-8", errors="ignore")
            except OSError:
                log.warning("Could not read %s", file_path)
                return
            tree = self._parse_source(file_path, source)
            if tree is None:
                return

        self._resolve_file(file_path, source, tree, symbol_map, class_lines_per_file.get(file_path, []))

    def _resolve_file(
        self,
        file_path: str,
        source: str,
        tree: Tree,
        symbol_map: dict[tuple[str, int], str],
        class_lines: list[tuple[int, str]] | None = None,
    ) -> None:
        root = self._ls.repository_root_path
        rel_path = os.path.relpath(file_path, root)
        stats = getattr(self, "_stats", None)

        t0 = time.monotonic()
        call_sites = self._call_extractor.extract(file_path, tree, symbol_map)
        t1 = time.monotonic()
        type_refs = self._type_ref_extractor.extract(file_path, tree, symbol_map, class_lines or []) if self._type_ref_extractor else []
        t2 = time.monotonic()
        if stats:
            stats.extraction_calls_time += t1 - t0
            stats.extraction_typerefs_time += t2 - t1

        if not call_sites and not type_refs:
            return

        log.debug(
            "Resolving %s: %d call sites, %d type refs",
            rel_path, len(call_sites), len(type_refs),
        )
        file_start = time.monotonic()

        try:
            with self._ls.open_file(rel_path):
                for caller_full_name, callee_simple, call_line_1, call_col_0 in call_sites:
                    self._resolve_call(
                        caller_full_name, rel_path, call_line_1 - 1, call_col_0,
                        callee_simple, symbol_map=symbol_map,
                        call_line_1=call_line_1, call_col_0=call_col_0,
                    )
                for ref in type_refs:
                    self._resolve_type_ref(ref, rel_path)
        except Exception:
            log.warning("LSP open_file failed for %s, skipping", rel_path)

        self._flush_pending()

        file_elapsed = time.monotonic() - file_start
        if file_elapsed > 2.0:
            log.info(
                "Slow file: %s took %.1fs (%d call sites, %d type refs)",
                rel_path, file_elapsed, len(call_sites), len(type_refs),
            )

    def _resolve_call(
        self, caller_full_name: str, rel_path: str, line_0: int, col_0: int,
        callee_simple_name: str | None = None,
        symbol_map: dict[tuple[str, int], str] | None = None,
        call_line_1: int | None = None,
        call_col_0: int | None = None,
    ) -> None:
        stats = getattr(self, "_stats", None)

        t0 = time.monotonic()
        try:
            definitions = self._ls.request_definition(rel_path, line_0, col_0)
        except Exception:
            if stats:
                stats.lsp_definition_time += time.monotonic() - t0
                stats.calls_unresolved += 1
            return
        if stats:
            stats.lsp_definition_time += time.monotonic() - t0

        if not definitions:
            caller_abs = os.path.join(self._ls.repository_root_path, rel_path)
            if self._try_import_fallback(
                caller_full_name, callee_simple_name or "",
                caller_abs, call_line_1, call_col_0,
            ):
                return
            self._unresolved_sites.append(
                f"Unresolved (no definitions): {caller_full_name} -> {callee_simple_name} at {rel_path}:{line_0 + 1}"
            )
            if stats:
                stats.calls_unresolved += 1
            return

        # Direct symbol_map lookup by definition location.
        # Handles interface method signatures (single-line declarations) which
        # request_containing_symbol cannot find because it excludes one-liner symbols.
        if symbol_map:
            for defn in definitions:
                abs_path = defn.get("absolutePath")
                def_line = defn.get("range", {}).get("start", {}).get("line")
                if abs_path is not None and def_line is not None:
                    callee_full_name = symbol_map.get((abs_path, def_line))
                    if callee_full_name:
                        t_name = time.monotonic()
                        callee_full_name = self._resolve_callee_name(callee_full_name)
                        if stats:
                            stats.callee_name_time += time.monotonic() - t_name
                        if callee_full_name and callee_full_name != caller_full_name:
                            self._upsert_call(caller_full_name, callee_full_name, call_line_1, call_col_0)
                            if stats:
                                stats.calls_resolved += 1
                            return
                    elif self._assignment_position_map:
                        # Definition landed on a non-method position; check if it's a
                        # stored-reference assignment (only self._field = call() positions
                        # populate the map, so no additional pattern guard is needed)
                        ref = self._assignment_position_map.get((abs_path, def_line))
                        if ref:
                            log.debug(
                                "Assignment fallback: %s -> %s at %s:%d, source at %s:%d",
                                caller_full_name, callee_simple_name, abs_path, def_line,
                                ref.source_file, ref.source_line,
                            )
                            src_rel = os.path.relpath(ref.source_file, self._ls.repository_root_path)
                            try:
                                src_defs = self._ls.request_definition(src_rel, ref.source_line, ref.source_col)
                            except Exception:
                                src_defs = None
                            if src_defs:
                                for src_defn in src_defs:
                                    src_abs = src_defn.get("absolutePath")
                                    src_line = src_defn.get("range", {}).get("start", {}).get("line")
                                    if src_abs is not None and src_line is not None:
                                        resolved_name = symbol_map.get((src_abs, src_line))
                                        if resolved_name:
                                            t_name = time.monotonic()
                                            resolved_name = self._resolve_callee_name(resolved_name)
                                            if stats:
                                                stats.callee_name_time += time.monotonic() - t_name
                                            if resolved_name and resolved_name != caller_full_name:
                                                self._upsert_call(caller_full_name, resolved_name, call_line_1, call_col_0)
                                                if stats:
                                                    stats.calls_resolved += 1
                                                    stats.calls_resolved_via_assignment += 1
                                                return
                            # Assignment fallback failed
                            self._unresolved_sites.append(
                                f"Unresolved (assignment fallback failed): {caller_full_name} -> {callee_simple_name} at {rel_path}:{line_0 + 1}"
                            )
                            if stats:
                                stats.calls_unresolved += 1
                            return

        # Import-based fallback: use tree-sitter import data when LSP
        # returned a same-file location (import line) that symbol_map couldn't match.
        caller_abs = os.path.join(self._ls.repository_root_path, rel_path)
        if self._try_import_fallback(
            caller_full_name, callee_simple_name or "",
            caller_abs, call_line_1, call_col_0,
        ):
            return

        # Name-based fallback: when LSP definitions land outside indexed sources
        # (e.g. library jars), try resolving by simple name if unambiguous.
        if callee_simple_name and self._name_to_full_names:
            candidates = self._name_to_full_names.get(callee_simple_name, [])
            if len(candidates) == 1 and candidates[0] != caller_full_name:
                self._upsert_call(caller_full_name, candidates[0], call_line_1, call_col_0)
                if stats:
                    stats.calls_resolved += 1
                    stats.calls_resolved_via_import += 1
                return

        # Fallback: resolve via containing symbol (may fail for single-line declarations)
        t_cs = time.monotonic()
        try:
            definition = definitions[0]
            def_path = definition["relativePath"]
            def_line = definition["range"]["start"]["line"]
            def_col = definition["range"]["start"]["character"]
            symbol = self._ls.request_containing_symbol(def_path, def_line, def_col, strict=False)
        except Exception:
            if stats:
                stats.lsp_containing_time += time.monotonic() - t_cs
                stats.calls_unresolved += 1
            return
        if stats:
            stats.lsp_containing_time += time.monotonic() - t_cs

        if symbol is None:
            self._unresolved_sites.append(
                f"Unresolved (no containing symbol): {caller_full_name} -> {callee_simple_name} at {rel_path}:{line_0 + 1}"
            )
            if stats:
                stats.calls_unresolved += 1
            return
        # Roslyn sometimes returns the containing class rather than the method itself.
        # When that happens, find the matching method among the class's children.
        if symbol.get("kind") not in _METHOD_KINDS:
            if not callee_simple_name:
                if stats:
                    stats.calls_unresolved += 1
                return
            method_children = [
                c for c in symbol.get("children", [])
                if c.get("kind") in _METHOD_KINDS and c.get("name") == callee_simple_name
            ]
            if len(method_children) != 1:
                self._unresolved_sites.append(
                    f"Unresolved (class not method): {caller_full_name} -> {callee_simple_name} at {rel_path}:{line_0 + 1}"
                )
                if stats:
                    stats.calls_unresolved += 1
                return
            symbol = method_children[0]
        callee_full_name = build_full_name(symbol)
        t_name = time.monotonic()
        callee_full_name = self._resolve_callee_name(callee_full_name)
        if stats:
            stats.callee_name_time += time.monotonic() - t_name
        if callee_full_name and callee_full_name != caller_full_name:
            self._upsert_call(caller_full_name, callee_full_name, call_line_1, call_col_0)
            if stats:
                stats.calls_resolved += 1
        else:
            if stats:
                stats.calls_unresolved += 1

    def _upsert_call(
        self, caller_full_name: str, callee_full_name: str,
        line: int | None, col: int | None,
    ) -> None:
        """Accumulate a CALLS edge for batch writing."""
        row = {"caller": caller_full_name, "callee": callee_full_name, "line": line, "col": col}
        if caller_full_name in self._module_full_names:
            self._pending_module_calls.append(row)
        else:
            self._pending_calls.append(row)

    def _flush_pending(self) -> None:
        """Batch-write all accumulated CALLS and REFERENCES edges."""
        if self._pending_calls:
            batch_upsert_calls(self._conn, self._pending_calls)
            self._pending_calls = []
        if self._pending_module_calls:
            batch_upsert_module_calls(self._conn, self._pending_module_calls)
            self._pending_module_calls = []
        if self._pending_refs:
            batch_upsert_references(self._conn, self._pending_refs)
            self._pending_refs = []

    def _resolve_callee_name(self, full_name: str) -> str:
        """
        Resolve the callee full_name to the actual stored value, handling overloaded variants.

        Phase 1 may store methods as "X.M(int)" when overload_idx is set, but
        request_defining_symbol returns "X.M" without it. We do a graph lookup to
        find the unique stored variant (if unambiguous).

        Results are cached to avoid repeated graph queries for the same callee.
        """
        if not full_name:
            return full_name
        cached = self._callee_name_cache.get(full_name)
        if cached is not None:
            return cached
        rows = self._conn.query(
            "MATCH (m:Method) "
            "WHERE m.full_name = $name OR m.full_name STARTS WITH $prefix "
            "RETURN m.full_name LIMIT 2",
            {"name": full_name, "prefix": full_name + "("},
        )
        result = rows[0][0] if len(rows) == 1 else full_name
        self._callee_name_cache[full_name] = result
        return result

    def _try_import_fallback(
        self, caller_full_name: str, callee_simple_name: str,
        caller_abs_path: str,
        call_line_1: int | None, call_col_0: int | None,
    ) -> bool:
        """Attempt to resolve a call using import extraction data.

        Returns True if a CALLS edge was created, False otherwise.
        """
        if not self._import_map or not callee_simple_name:
            return False
        file_imports = self._import_map.get(caller_abs_path)
        if not file_imports:
            return False
        module_path = file_imports.get(callee_simple_name)
        if not module_path:
            return False

        # Construct candidate full_name: module_path.symbol_name
        # This matches the TS full_name convention: "src/animals.Dog"
        candidate = f"{module_path}.{callee_simple_name}"
        rows = self._conn.query(
            "MATCH (m:Method {full_name: $name}) RETURN m.full_name LIMIT 1",
            {"name": candidate},
        )
        if rows:
            callee_full_name = rows[0][0]
        else:
            # Fall back to name_to_full_names for unambiguous match
            candidates = self._name_to_full_names.get(callee_simple_name, [])
            if len(candidates) == 1:
                callee_full_name = candidates[0]
            else:
                return False

        t_name = time.monotonic()
        callee_full_name = self._resolve_callee_name(callee_full_name)
        stats = getattr(self, "_stats", None)
        if stats:
            stats.callee_name_time += time.monotonic() - t_name

        if callee_full_name and callee_full_name != caller_full_name:
            self._upsert_call(caller_full_name, callee_full_name, call_line_1, call_col_0)
            if stats:
                stats.calls_resolved += 1
                stats.calls_resolved_via_import += 1
            return True
        return False

    def _resolve_type_ref(self, ref: TypeRef, rel_path: str) -> None:
        if not ref.owner_full_name:
            return
        stats = getattr(self, "_stats", None)
        target_full_name: str | None = None
        # Try the project's own symbol name map first (cheap dict lookup).
        # Only use it for unambiguous cases (exactly one match).
        if self._name_to_full_names:
            candidates = self._name_to_full_names.get(ref.type_name, [])
            if len(candidates) == 1:
                target_full_name = candidates[0]
        # Fall back to LSP (expensive round-trip) for ambiguous or unknown types.
        if not target_full_name:
            t0 = time.monotonic()
            try:
                symbol = self._ls.request_defining_symbol(rel_path, ref.line, ref.col)
                if symbol and symbol.get("kind") in _TYPE_KINDS:
                    target_full_name = build_full_name(symbol)
            except Exception:
                pass
            if stats:
                stats.lsp_definition_time += time.monotonic() - t0
        if target_full_name:
            self._pending_refs.append({
                "source": ref.owner_full_name,
                "target": target_full_name,
                "kind": ref.ref_kind,
            })
            if stats:
                stats.type_refs_resolved += 1

    def _parse_source(self, file_path: str, source: str) -> Tree | None:
        """Fallback: parse source when no cached tree is available."""
        if not hasattr(self, "_fallback_parser"):
            self._fallback_parser = None
            if self._file_extensions:
                ext = next(iter(self._file_extensions), "")
                if ext == ".py":
                    import tree_sitter_python
                    from tree_sitter import Language, Parser
                    self._fallback_parser = Parser(Language(tree_sitter_python.language()))
                elif ext in {".ts", ".tsx", ".js", ".jsx"}:
                    import tree_sitter_typescript
                    from tree_sitter import Language, Parser
                    self._fallback_parser = Parser(Language(tree_sitter_typescript.language_typescript()))
                elif ext == ".java":
                    import tree_sitter_java
                    from tree_sitter import Language, Parser
                    self._fallback_parser = Parser(Language(tree_sitter_java.language()))
                elif ext == ".cs":
                    import tree_sitter_c_sharp
                    from tree_sitter import Language, Parser
                    self._fallback_parser = Parser(Language(tree_sitter_c_sharp.language()))
        if self._fallback_parser:
            return self._fallback_parser.parse(bytes(source, "utf-8"))
        return None

    def _iter_files(self, root_path: str):
        for ext in self._file_extensions:
            pattern = f"*{ext}"
            for path in Path(root_path).rglob(pattern):
                if not any(p in {".git", "bin", "obj", "__pycache__", ".venv", "node_modules"} for p in path.parts):
                    yield str(path)
