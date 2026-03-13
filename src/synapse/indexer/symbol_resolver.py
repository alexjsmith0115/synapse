from __future__ import annotations

import logging
import os
from pathlib import Path

from synapse.graph.connection import GraphConnection
from synapse.graph.edges import upsert_calls, upsert_references
from synapse.indexer.call_extractor import TreeSitterCallExtractor
from synapse.indexer.type_ref_extractor import TreeSitterTypeRefExtractor, TypeRef
from synapse.lsp.util import build_full_name

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


class SymbolResolver:
    """
    Walks .cs files once, runs call extraction and type reference extraction,
    then resolves both via LSP and writes CALLS and REFERENCES edges.
    """

    def __init__(
        self,
        conn: GraphConnection,
        ls: object,
        call_extractor: TreeSitterCallExtractor | None = None,
        type_ref_extractor: TreeSitterTypeRefExtractor | None = None,
        name_to_full_names: dict[str, list[str]] | None = None,
    ) -> None:
        self._conn = conn
        self._ls = ls
        self._call_extractor = call_extractor or TreeSitterCallExtractor()
        self._type_ref_extractor = type_ref_extractor or TreeSitterTypeRefExtractor()
        self._name_to_full_names = name_to_full_names or {}

    def resolve(
        self,
        root_path: str,
        symbol_map: dict[tuple[str, int], str],
        class_symbol_map: dict[tuple[str, int], str] | None = None,
    ) -> None:
        class_lines_per_file = _build_class_lines_per_file(class_symbol_map or {})
        for file_path in self._iter_cs_files(root_path):
            try:
                source = Path(file_path).read_text(encoding="utf-8", errors="ignore")
            except OSError:
                log.warning("Could not read %s", file_path)
                continue
            self._resolve_file(file_path, source, symbol_map, class_lines_per_file.get(file_path, []))

    def resolve_single_file(
        self,
        file_path: str,
        symbol_map: dict[tuple[str, int], str],
        class_symbol_map: dict[tuple[str, int], str] | None = None,
    ) -> None:
        try:
            source = Path(file_path).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            log.warning("Could not read %s", file_path)
            return
        class_lines_per_file = _build_class_lines_per_file(class_symbol_map or {})
        self._resolve_file(file_path, source, symbol_map, class_lines_per_file.get(file_path, []))

    def _resolve_file(
        self,
        file_path: str,
        source: str,
        symbol_map: dict[tuple[str, int], str],
        class_lines: list[tuple[int, str]] | None = None,
    ) -> None:
        root = self._ls.repository_root_path
        rel_path = os.path.relpath(file_path, root)

        call_sites = self._call_extractor.extract(file_path, source, symbol_map)
        type_refs = self._type_ref_extractor.extract(file_path, source, symbol_map, class_lines or [])

        if not call_sites and not type_refs:
            return

        try:
            with self._ls.open_file(rel_path):
                for caller_full_name, callee_simple, call_line_1, call_col_0 in call_sites:
                    self._resolve_call(caller_full_name, rel_path, call_line_1 - 1, call_col_0, callee_simple, symbol_map=symbol_map)
                for ref in type_refs:
                    self._resolve_type_ref(ref, rel_path)
        except Exception:
            log.warning("LSP open_file failed for %s, skipping", rel_path)

    def _resolve_call(
        self, caller_full_name: str, rel_path: str, line_0: int, col_0: int,
        callee_simple_name: str | None = None,
        symbol_map: dict[tuple[str, int], str] | None = None,
    ) -> None:
        try:
            definitions = self._ls.request_definition(rel_path, line_0, col_0)
        except Exception:
            return
        if not definitions:
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
                        callee_full_name = self._resolve_callee_name(callee_full_name)
                        if callee_full_name and callee_full_name != caller_full_name:
                            upsert_calls(self._conn, caller_full_name, callee_full_name)
                            return

        # Fallback: resolve via containing symbol (may fail for single-line declarations)
        try:
            definition = definitions[0]
            def_path = definition["relativePath"]
            def_line = definition["range"]["start"]["line"]
            def_col = definition["range"]["start"]["character"]
            symbol = self._ls.request_containing_symbol(def_path, def_line, def_col, strict=False)
        except Exception:
            return
        if symbol is None:
            return
        # Roslyn sometimes returns the containing class rather than the method itself.
        # When that happens, find the matching method among the class's children.
        if symbol.get("kind") not in _METHOD_KINDS:
            if not callee_simple_name:
                return
            method_children = [
                c for c in symbol.get("children", [])
                if c.get("kind") in _METHOD_KINDS and c.get("name") == callee_simple_name
            ]
            if len(method_children) != 1:
                return
            symbol = method_children[0]
        callee_full_name = build_full_name(symbol)
        callee_full_name = self._resolve_callee_name(callee_full_name)
        if callee_full_name and callee_full_name != caller_full_name:
            upsert_calls(self._conn, caller_full_name, callee_full_name)

    def _resolve_callee_name(self, full_name: str) -> str:
        """
        Resolve the callee full_name to the actual stored value, handling overloaded variants.

        Phase 1 may store methods as "X.M(int)" when overload_idx is set, but
        request_defining_symbol returns "X.M" without it. We do a graph lookup to
        find the unique stored variant (if unambiguous).
        """
        if not full_name:
            return full_name
        rows = self._conn.query(
            "MATCH (m:Method) "
            "WHERE m.full_name = $name OR m.full_name STARTS WITH $prefix "
            "RETURN m.full_name LIMIT 2",
            {"name": full_name, "prefix": full_name + "("},
        )
        if len(rows) == 1:
            return rows[0][0]
        return full_name

    def _resolve_type_ref(self, ref: TypeRef, rel_path: str) -> None:
        if not ref.owner_full_name:
            return
        target_full_name: str | None = None
        try:
            symbol = self._ls.request_defining_symbol(rel_path, ref.line, ref.col)
            if symbol and symbol.get("kind") in _TYPE_KINDS:
                target_full_name = build_full_name(symbol)
        except Exception:
            pass
        # LSP does not resolve all type reference positions (e.g. field types);
        # fall back to the project's own symbol name map for unambiguous cases.
        if not target_full_name and self._name_to_full_names:
            candidates = self._name_to_full_names.get(ref.type_name, [])
            if len(candidates) == 1:
                target_full_name = candidates[0]
        if target_full_name:
            upsert_references(self._conn, ref.owner_full_name, target_full_name, ref.ref_kind)

    @staticmethod
    def _iter_cs_files(root_path: str):
        for path in Path(root_path).rglob("*.cs"):
            if not any(p in {".git", "bin", "obj"} for p in path.parts):
                yield str(path)
