from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from synapps.lsp.interface import IndexSymbol, LSPAdapter, LSPResolverBackend, SymbolKind
from synapps.lsp.util import symbol_suffix

log = logging.getLogger(__name__)

# Maps LSP SymbolKind integers to Synapps SymbolKind.
# Per D-23: Java-specific kind mapping for Eclipse JDT LS.
_LSP_KIND_MAP: dict[int, SymbolKind] = {
    3: SymbolKind.NAMESPACE,   # package (LSP SymbolKind.Namespace)
    4: SymbolKind.NAMESPACE,   # package (LSP SymbolKind.Package — JDT LS reports kind 4)
    5: SymbolKind.CLASS,       # class
    6: SymbolKind.METHOD,      # method
    7: SymbolKind.PROPERTY,    # property
    8: SymbolKind.FIELD,       # field
    9: SymbolKind.METHOD,      # constructor (promoted to "constructor" kind in Guard 7)
    10: SymbolKind.ENUM,       # enum -> :Class with kind='enum' (mapped to CLASS label in indexer)
    11: SymbolKind.INTERFACE,  # interface
    12: SymbolKind.METHOD,     # function (shouldn't occur but handle gracefully)
    14: SymbolKind.FIELD,      # constant (static final fields)
}

# Directories excluded from workspace file discovery (per D-03).
_EXCLUDE_DIRS = frozenset({
    ".git", "target", "build", ".gradle", ".idea", "bin", ".settings", ".mvn",
})

_JAVA_PACKAGE_PREFIXES = ("com.", "org.", "io.", "net.", "java.", "javax.", "dev.", "me.", "app.")


_JAVA_SOURCE_DIR_MARKERS = ("main.", "test.", "src.")


def _clean_java_full_name(full_name: str) -> str:
    """Strip directory-path prefix from a Java full_name if present.

    Detects patterns like '....core.src.main.java.com.graphhopper.Foo'
    and returns 'com.graphhopper.Foo'.

    Special case (JI-03): 'java.' can appear as a directory segment (from
    src/main/java/) before a non-standard package prefix like 'order.' that is
    NOT in the known-prefix list. When 'java.' is preceded by a source-dir
    marker (main., test., src.), it is a path segment, not the java.* standard
    library prefix; in that case we strip everything up to and including 'java.'
    and return the remainder as the real package name.

    Algorithm:
    1. Collect all (idx, prefix) candidates where a known package prefix starts.
    2. Pick the rightmost non-'java.' candidate — it wins over any 'java.' match.
    3. If only 'java.' candidates remain, check whether 'java.' is preceded by a
       source-dir marker (main./test./src.). If so, it is a directory segment —
       return the text after 'java.' (the actual package root). Otherwise treat
       'java.' as the genuine standard-library prefix.
    """
    candidates: list[tuple[int, str]] = []
    for prefix in _JAVA_PACKAGE_PREFIXES:
        idx = full_name.find(prefix)
        if idx > 0:
            candidates.append((idx, prefix))

    if not candidates:
        return full_name

    non_java = [(idx, p) for idx, p in candidates if p != "java."]
    java_cands = [(idx, p) for idx, p in candidates if p == "java."]

    # Prefer the rightmost non-java. match (e.g. com., org., io., net., dev.)
    if non_java:
        best_idx = max(idx for idx, _ in non_java)
        return full_name[best_idx:]

    # Only java. candidates remain.
    for java_idx, _ in java_cands:
        # Check if the text immediately before 'java.' is a source-dir marker,
        # which would mean 'java.' is the Maven/Gradle source directory, not a package.
        preceding = full_name[:java_idx]
        is_dir_segment = any(preceding.endswith(marker) for marker in _JAVA_SOURCE_DIR_MARKERS)
        if is_dir_segment:
            # Strip the 'java.' directory segment and return the real package/class name
            return full_name[java_idx + len("java."):]
        # Not preceded by source-dir marker: 'java.' is the genuine package prefix
        return full_name[java_idx:]

    return full_name


def _detect_java_source_root(file_path: str, root_path: str) -> str:
    """Detect the Java source root by looking for a 'java' directory in the file's path.

    Covers conventional layouts: src/main/java, src/test/java, src/java.
    Falls back to src/main or src/test if no 'java' dir found,
    then to root_path as last resort.
    """
    parts = Path(file_path).parts
    # Walk backwards looking for a directory named "java" that is under the root
    for i in range(len(parts) - 1, -1, -1):
        if parts[i] == "java":
            candidate = str(Path(*parts[: i + 1]))
            if candidate.startswith(root_path):
                return candidate
    # Fallback: look for src/main or src/test
    for marker in ("main", "test"):
        for i in range(len(parts) - 1, -1, -1):
            if parts[i] == marker and i > 0 and parts[i - 1] == "src":
                candidate = str(Path(*parts[: i + 1]))
                if candidate.startswith(root_path):
                    return candidate
    return root_path


def _symbol_suffix_no_namespace(raw: dict) -> str:
    """Like symbol_suffix but skips NAMESPACE parents (kind=3).

    For Java, the package namespace is derived from the file path,
    so we exclude it from the symbol chain to avoid duplication.
    """
    name = raw.get("name", "")
    parent = raw.get("parent")
    if parent:
        if parent.get("kind") == 3:
            # Skip namespace parent, continue to its parent
            grandparent = parent.get("parent")
            if grandparent:
                return f"{_symbol_suffix_no_namespace(grandparent)}.{name}"
            return name
        return f"{_symbol_suffix_no_namespace(parent)}.{name}"
    return name


def _build_java_full_name(raw: dict, file_path: str, source_root: str) -> str:
    """Build a package-qualified full name from file path + symbol parent chain.

    Derives the package prefix from the file path relative to the source root,
    then appends the symbol chain (excluding namespace parents) for nested symbols.
    """
    rel = os.path.relpath(file_path, source_root)
    # Convert path to dotted package + class: com/synappstest/Animal.java -> com.synappstest.Animal
    path_prefix = rel.replace(os.sep, ".").removesuffix(".java")

    # Get the symbol chain excluding namespace parents
    suffix = _symbol_suffix_no_namespace(raw)

    # The path_prefix already contains the top-level class name (from the filename).
    # The suffix contains the full symbol chain from raw (class.method or just class).
    # We need to figure out the "inner" part (below the top-level class).
    #
    # Strategy: the top-level class name is the last component of path_prefix.
    # If suffix == top-level class name, return just path_prefix.
    # If suffix starts with "TopClass.", return path_prefix + rest.
    top_class = path_prefix.rsplit(".", 1)[-1] if "." in path_prefix else path_prefix

    if suffix == top_class:
        base = path_prefix
    elif suffix.startswith(f"{top_class}."):
        inner = suffix[len(top_class) + 1:]
        base = f"{path_prefix}.{inner}"
    else:
        # Symbol name doesn't match filename class (e.g. inner class or standalone)
        # Use the full suffix appended to the package (path_prefix minus the filename class)
        if "." in path_prefix:
            package = path_prefix.rsplit(".", 1)[0]
            base = f"{package}.{suffix}"
        else:
            base = suffix

    # Handle overload_idx (parameter signature for overloaded methods)
    if "overload_idx" in raw:
        detail = raw.get("detail", "") or ""
        if "(" in detail:
            return _clean_java_full_name(f"{base}{detail[detail.index('('):]}")
    return _clean_java_full_name(base)


class JavaLSPAdapter:
    """Wraps an EclipseJDTLS instance to provide the LSPAdapter interface for Java."""

    file_extensions: frozenset[str] = frozenset({".java"})

    def __init__(self, language_server: LSPResolverBackend, root_path: str) -> None:
        self._ls = language_server
        self._root_path = root_path
        self._source_root: str | None = None

    @property
    def language_server(self) -> LSPResolverBackend:
        return self._ls

    @classmethod
    def create(cls, root_path: str) -> JavaLSPAdapter:
        """Start the Eclipse JDT LS and return a ready adapter."""
        from solidlsp.language_servers.eclipse_jdtls import EclipseJDTLS
        from solidlsp.ls_config import Language, LanguageServerConfig
        from solidlsp.settings import SolidLSPSettings

        config = LanguageServerConfig(code_language=Language.JAVA)
        settings = SolidLSPSettings()
        ls = EclipseJDTLS(
            config=config,
            repository_root_path=root_path,
            solidlsp_settings=settings,
        )
        log.info("Starting Eclipse JDT LS for %s", root_path)
        t0 = time.monotonic()
        ls.start()
        log.info("Eclipse JDT LS ready in %.1fs", time.monotonic() - t0)
        return cls(ls, root_path)

    def get_workspace_files(self, root_path: str) -> list[str]:
        from synapps.util.file_system import load_synignore

        t0 = time.monotonic()
        synignore = load_synignore(root_path)
        files: list[str] = []
        for path in Path(root_path).rglob("*.java"):
            if not any(part in _EXCLUDE_DIRS for part in path.parts):
                abs_path = str(path)
                if synignore is not None and synignore.is_file_ignored(abs_path):
                    continue
                files.append(abs_path)
        log.info("Discovered %d Java files in %.1fs", len(files), time.monotonic() - t0)
        return files

    def get_document_symbols(self, file_path: str) -> list[IndexSymbol]:
        try:
            # Detect source root per-file — supports multi-module monorepos where different
            # modules have different source roots (JI-04). Do not cache on self._source_root
            # to avoid stale roots when indexing files from different modules.
            source_root = _detect_java_source_root(file_path, self._root_path)

            t0 = time.monotonic()
            raw = self._ls.request_document_symbols(file_path)
            elapsed = time.monotonic() - t0
            if raw is None:
                return []
            result: list[IndexSymbol] = []
            for root in raw.root_symbols:
                self._traverse(root, file_path, parent_full_name=None, result=result, source_root=source_root)
            if elapsed > 2.0:
                log.info(
                    "Slow document symbols: %s took %.1fs (%d symbols)",
                    file_path, elapsed, len(result),
                )
            return result
        except Exception:
            log.exception("Failed to get symbols for %s", file_path)
            return []

    def _traverse(
        self,
        raw: dict,
        file_path: str,
        parent_full_name: str | None,
        result: list[IndexSymbol],
        source_root: str | None = None,
    ) -> None:
        sym = self._convert(raw, file_path, parent_full_name, source_root=source_root)
        # JC-02: Skip anonymous class expressions — JDT LS names them "new Foo() {...}".
        # These create spurious Class nodes; their internals are not useful for the graph.
        if sym.kind == SymbolKind.CLASS and sym.name.startswith("new "):
            return
        result.append(sym)
        for child in raw.get("children", []):
            self._traverse(child, file_path, parent_full_name=sym.full_name, result=result, source_root=source_root)

    def _convert(self, raw: dict, file_path: str, parent_full_name: str | None, source_root: str | None = None) -> IndexSymbol:
        kind_int = raw.get("kind", 0)
        kind = _LSP_KIND_MAP.get(kind_int)
        if kind is None:
            log.debug(
                "Unmapped LSP SymbolKind %d for symbol %s, defaulting to CLASS",
                kind_int, raw.get("name", "?"),
            )
            kind = SymbolKind.CLASS

        name = raw.get("name", "")
        # Use the provided per-file source_root; fall back to the cached _source_root for
        # backward-compat with callers that set it directly (e.g. tests using _make_adapter).
        effective_source_root = source_root or self._source_root or self._root_path
        full_name = _build_java_full_name(raw, file_path, effective_source_root)

        range_obj = raw.get("location", {}).get("range", {})
        # Use selectionRange.start.line when available — JDT LS sets location.range to include the
        # Javadoc block, but selectionRange points to the declaration keyword (what LSP definition
        # lookups return). The symbol_map and base_type_symbol_map are keyed by (file_path, line)
        # so both must agree.
        sel_range = raw.get("selectionRange", range_obj)
        line = sel_range.get("start", {}).get("line", 0) + 1
        end_line = range_obj.get("end", {}).get("line", 0) + 1
        detail = raw.get("detail", "") or ""

        return IndexSymbol(
            name=name,
            full_name=full_name,
            kind=kind,
            file_path=file_path,
            line=line,
            end_line=end_line,
            signature=detail,
            is_abstract="abstract" in detail.lower(),
            is_static="static" in detail.lower(),
            parent_full_name=parent_full_name,
        )

    def find_method_calls(self, symbol: IndexSymbol) -> list[str]:
        return []

    def find_overridden_method(self, symbol: IndexSymbol) -> str | None:
        return None

    def shutdown(self) -> None:
        self._ls.stop()
