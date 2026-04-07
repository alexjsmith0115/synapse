from __future__ import annotations

import logging
import os
from collections.abc import Callable
from pathlib import Path

from synapps.graph.connection import GraphConnection
from synapps.graph.lookups import get_method_symbol_map
from synapps.graph.nodes import get_last_indexed_commit, set_last_indexed_commit
from synapps.indexer.git import is_git_repo, rev_parse_head, compute_git_diff
from synapps.indexer.indexer import Indexer
from synapps.indexer.method_implements_indexer import MethodImplementsIndexer
from synapps.indexer.sync import git_sync_project as _git_sync_project, sync_project as _sync_project, SyncResult
from synapps.indexer.overrides_indexer import OverridesIndexer
from synapps.indexer.symbol_resolver import SymbolResolver
from synapps.lsp.interface import LSPAdapter
from synapps.plugin import LanguagePlugin, LanguageRegistry, default_registry
from synapps.watcher.watcher import FileWatcher

log = logging.getLogger(__name__)


class IndexingService:
    def __init__(
        self,
        conn: GraphConnection,
        registry: LanguageRegistry | None = None,
    ) -> None:
        self._conn = conn
        self._registry = registry or default_registry()
        self._watchers: dict[str, FileWatcher] = {}

    def index_project(
        self,
        path: str,
        language: str = "csharp",
        on_progress: Callable[[str], None] | None = None,
        plugin_files: list[tuple[LanguagePlugin, list[str]]] | None = None,
    ) -> None:
        from solidlsp.ls import _resolve_true_case
        path = _resolve_true_case(path)
        if plugin_files is None:
            plugin_files = self._registry.detect_with_files(path)
        if not plugin_files:
            raise ValueError(f"No language plugin found for project at {path!r}")
        all_http_results: list = []
        for plugin, files in plugin_files:
            if on_progress:
                on_progress(f"Starting language server for {plugin.name}...")
            lsp = plugin.create_lsp_adapter(path)
            indexer = Indexer(self._conn, lsp, plugin=plugin)
            indexer.index_project(path, plugin.name, on_progress=on_progress, files=files)
            all_http_results.extend(indexer._http_extraction_results)

        # HTTP endpoint matching — runs once after all languages are indexed
        # so frontend client calls can be matched to backend server endpoints
        if all_http_results:
            import time
            t_http = time.monotonic()
            from synapps.indexer.http_phase import HttpPhase
            http_phase = HttpPhase(self._conn, path)
            http_phase.run(all_http_results)
            http_phase.cleanup_orphans()
            log.info("HTTP endpoint matching: %.1fs", time.monotonic() - t_http)

        # TESTS edge derivation -- runs after all languages indexed + HTTP phase
        # so all CALLS edges exist for test->prod derivation (D-04)
        import time
        t_tests = time.monotonic()
        from synapps.indexer.tests_phase import TestsPhase
        tests_phase = TestsPhase(self._conn, path)
        tests_phase.run()
        log.info("TESTS edge derivation: %.1fs", time.monotonic() - t_tests)

    def index_calls(self, path: str) -> None:
        """Run the relationship resolution pass on an already-structurally-indexed project."""
        from solidlsp.ls import _resolve_true_case
        path = _resolve_true_case(path)
        plugins = self._registry.detect(path)
        if not plugins:
            raise ValueError(f"No language plugin found for project at {path!r}")
        symbol_map = get_method_symbol_map(self._conn)
        for plugin in plugins:
            lsp = plugin.create_lsp_adapter(path)
            call_ext = plugin.create_call_extractor()
            type_ref_ext = plugin.create_type_ref_extractor()

            module_full_names: set[str] = set()
            if plugin.name in ("python", "typescript"):
                module_map: dict[str, str] = {}
                rows = self._conn.query(
                    "MATCH (n:Class {kind: 'module'}) RETURN n.full_name, n.file_path"
                )
                for full_name, file_path in rows:
                    if full_name and file_path:
                        module_full_names.add(full_name)
                        module_map[file_path] = full_name
                if call_ext is not None and hasattr(call_ext, "_module_name_resolver"):
                    call_ext._module_name_resolver = lambda fp, _m=module_map: _m.get(fp)

            resolver = SymbolResolver(
                self._conn, lsp.language_server,
                call_extractor=call_ext,
                type_ref_extractor=type_ref_ext,
                file_extensions=plugin.file_extensions,
                module_full_names=module_full_names,
            )
            resolver.resolve(path, symbol_map)

            if plugin.name in ("python", "typescript", "java") and hasattr(resolver, "_unresolved_sites"):
                for site_msg in resolver._unresolved_sites:
                    log.debug(site_msg)

            if plugin.name in ("python", "typescript", "java") and call_ext is not None:
                calls_count_rows = self._conn.query(
                    "MATCH ()-[r:CALLS]->() WHERE r.call_sites IS NOT NULL RETURN count(r)"
                )
                resolved = calls_count_rows[0][0] if calls_count_rows else 0
                total = getattr(call_ext, "_sites_seen", 0)
                if total > 0:
                    pct = resolved / total * 100
                    unresolved = total - resolved
                    log.info(
                        "Call resolution: %d/%d resolved (%.1f%%), %d unresolved",
                        resolved, total, pct, unresolved,
                    )
                    if resolved == 0:
                        log.warning(
                            "Call resolution produced zero CALLS edges (%d sites attempted) — "
                            "check that LSP is running and fixture uses typed code",
                            total,
                        )

            if plugin.name in ("python", "typescript", "java"):
                OverridesIndexer(self._conn).index()

            lsp.shutdown()

    def sync_project(
        self,
        path: str,
        plugin_files: list[tuple[LanguagePlugin, list[str]]] | None = None,
    ) -> SyncResult:
        """Sync the graph with the current filesystem state.

        Detects stale, new, and deleted files and re-indexes only what changed.
        Requires the project to have been fully indexed at least once.
        """
        from solidlsp.ls import _resolve_true_case
        path = _resolve_true_case(path)
        if plugin_files is None:
            plugin_files = self._registry.detect_with_files(path)
        if not plugin_files:
            raise ValueError(f"No language plugin found for project at {path!r}")

        total = SyncResult(updated=0, deleted=0, unchanged=0)
        for plugin, files in plugin_files:
            lsp = plugin.create_lsp_adapter(path)
            try:
                indexer = Indexer(self._conn, lsp, plugin=plugin)
                if files:
                    workspace_files = files
                else:
                    workspace_files = lsp.get_workspace_files(path)
                disk_files = {}
                for fp in workspace_files:
                    try:
                        disk_files[fp] = os.path.getmtime(fp)
                    except OSError:
                        pass
                result = _sync_project(
                    conn=self._conn,
                    indexer=indexer,
                    root_path=path,
                    disk_files=disk_files,
                    language=plugin.name,
                )
                total.updated += result.updated
                total.deleted += result.deleted
                total.unchanged += result.unchanged
            finally:
                lsp.shutdown()

        # Post-sync HTTP re-matching
        self._run_http_rematch(path)
        self._run_tests_phase(path)

        return total

    def smart_index(
        self,
        path: str,
        language: str = "csharp",
        on_progress: Callable[[str], None] | None = None,
        allowed_languages: list[str] | None = None,
    ) -> str:
        """Unified index entry point (D-04).

        1. No graph data -> full index
        2. Git project -> git-based sync
        3. No git -> mtime-based sync
        """
        from solidlsp.ls import _resolve_true_case
        path = _resolve_true_case(path.rstrip("/"))

        plugin_files = self._registry.detect_with_files(path)
        if allowed_languages is not None:
            plugin_files = [(p, f) for p, f in plugin_files if p.name in allowed_languages]

        stored_sha = get_last_indexed_commit(self._conn, path)
        repo_rows = self._conn.query(
            "MATCH (r:Repository {path: $path}) RETURN r.path",
            {"path": path},
        )
        if not repo_rows:
            if on_progress:
                on_progress("No existing index -- running full index...")
            self.index_project(path, language, on_progress=on_progress, plugin_files=plugin_files)
            if is_git_repo(path):
                sha = rev_parse_head(path)
                if sha:
                    set_last_indexed_commit(self._conn, path, sha)
            return "full-index"

        if is_git_repo(path):
            if on_progress:
                on_progress("Git project detected -- running git sync...")
            if not plugin_files:
                raise ValueError(f"No language plugin found for project at {path!r}")

            effective_sha = stored_sha or self._git_empty_tree_sha()
            diff = compute_git_diff(path, effective_sha)
            all_changed = diff.to_reindex | diff.to_delete | {new for _, new in diff.renames}

            total = SyncResult(updated=0, deleted=0, unchanged=0)
            for plugin, _files in plugin_files:
                has_changes = any(
                    os.path.splitext(p)[1].lower() in plugin.file_extensions
                    for p in all_changed
                )
                if not has_changes:
                    log.info("Skipping %s — no changes detected", plugin.name)
                    continue

                lsp = plugin.create_lsp_adapter(path)
                try:
                    indexer = Indexer(self._conn, lsp, plugin=plugin)
                    result = _git_sync_project(
                        conn=self._conn,
                        indexer=indexer,
                        root_path=path,
                        stored_sha=effective_sha,
                        file_extensions=lsp.file_extensions,
                    )
                    total.updated += result.updated
                    total.deleted += result.deleted
                finally:
                    lsp.shutdown()

            # Post-sync HTTP re-matching
            self._run_http_rematch(path)
            self._run_tests_phase(path)

            return "git-sync"

        if on_progress:
            on_progress("Non-git project -- running mtime sync...")
        self.sync_project(path, plugin_files=plugin_files)
        return "mtime-sync"

    def _run_http_rematch(self, path: str) -> None:
        """Post-sync HTTP endpoint re-matching.

        Rebuilds HTTP data from the graph (for unchanged files) and re-runs
        matching. Clears existing HTTP edges first to avoid call_sites
        duplication from re-MERGE over existing edges.
        """
        from synapps.indexer.http_phase import HttpPhase
        from synapps.indexer.http.interface import HttpExtractionResult
        http_phase = HttpPhase(self._conn, path)
        existing_defs, existing_calls = http_phase.rebuild_from_graph()
        # Clear all HTTP edges before re-matching to avoid call_sites duplication
        self._conn.execute(
            "MATCH (r:Repository {path: $repo})-[:CONTAINS]->(ep:Endpoint)<-[rel]-(m:Method) "
            "WHERE type(rel) IN ['SERVES', 'HTTP_CALLS'] "
            "DELETE rel",
            {"repo": path},
        )
        http_phase.run([HttpExtractionResult(endpoint_defs=existing_defs, client_calls=existing_calls)])
        http_phase.cleanup_orphans()

    def _run_tests_phase(self, path: str) -> None:
        """Post-sync TESTS edge re-derivation.

        Unlike HttpPhase, TestsPhase is fully derivable from the live graph --
        no rebuild_from_graph() needed since CALLS edges are already present.
        """
        from synapps.indexer.tests_phase import TestsPhase
        tests_phase = TestsPhase(self._conn, path)
        tests_phase.run()

    @staticmethod
    def _git_empty_tree_sha() -> str:
        """The git empty tree SHA -- diffing against this gives all files as added."""
        return "4b825dc642cb6eb9a060e54bf899d69f82cf7180"

    def index_method_implements(self) -> None:
        """Write method-level IMPLEMENTS edges for all indexed class-level IMPLEMENTS relationships."""
        MethodImplementsIndexer(self._conn).index()

    def delete_project(self, path: str) -> None:
        self._conn.execute(
            "MATCH (r:Repository {path: $path})-[:CONTAINS*]->(n) DETACH DELETE n",
            {"path": path},
        )
        self._conn.execute("MATCH (r:Repository {path: $path}) DETACH DELETE r", {"path": path})

    def watch_project(
        self,
        path: str,
        lsp_adapter: LSPAdapter | None = None,
        on_file_event: Callable[[str, str], None] | None = None,
    ) -> None:
        if path in self._watchers:
            return

        if lsp_adapter is not None:
            plugins_and_lsps: list[tuple[LanguagePlugin | None, LSPAdapter]] = [
                (None, lsp_adapter),
            ]
        else:
            plugins = self._registry.detect(path)
            if not plugins:
                raise ValueError(f"No language plugin found for project at {path!r}")
            plugins_and_lsps = [
                (p, p.create_lsp_adapter(path)) for p in plugins
            ]

        # Build extension->indexer map and index each language
        ext_to_indexer: dict[str, Indexer] = {}
        all_extensions: set[str] = set()
        for plugin, lsp in plugins_and_lsps:
            indexer = Indexer(self._conn, lsp, plugin=plugin)
            lang_name = plugin.name if plugin else "csharp"
            indexer.index_project(path, lang_name, keep_lsp_running=True)
            exts = plugin.file_extensions if plugin else frozenset({".cs"})
            for ext in exts:
                ext_to_indexer[ext] = indexer
            all_extensions |= exts

        def on_change(file_path: str) -> None:
            ext = Path(file_path).suffix.lower()
            indexer = ext_to_indexer.get(ext)
            if indexer:
                try:
                    log.info("Re-indexing changed file: %s", file_path)
                    if on_file_event:
                        on_file_event("changed", file_path)
                    indexer.reindex_file(file_path, path)
                except Exception:
                    log.warning("Watcher: failed to re-index %s, skipping", file_path, exc_info=True)

        def on_delete(file_path: str) -> None:
            ext = Path(file_path).suffix.lower()
            indexer = ext_to_indexer.get(ext)
            if indexer:
                try:
                    log.info("Removing deleted file: %s", file_path)
                    if on_file_event:
                        on_file_event("deleted", file_path)
                    indexer.delete_file(file_path)
                except Exception:
                    log.warning("Watcher: failed to delete %s, skipping", file_path, exc_info=True)

        watcher = FileWatcher(
            root_path=path, on_change=on_change, on_delete=on_delete,
            watched_extensions=frozenset(all_extensions),
        )
        watcher.start()
        self._watchers[path] = watcher

    def unwatch_project(self, path: str) -> None:
        watcher = self._watchers.pop(path, None)
        if watcher:
            watcher.stop()
        # Update stored SHA so auto-sync doesn't re-sync what the watcher already handled
        if is_git_repo(path):
            sha = rev_parse_head(path)
            if sha:
                set_last_indexed_commit(self._conn, path, sha)
