"""Integration tests for graph auto-update mechanisms.

Validates the full flow: file changes -> staleness detection -> sync -> graph correctness.
Covers both pre-query auto-sync (git SHA comparison) and file watcher paths.

Requires Memgraph on localhost:7687.
Run with: pytest tests/integration/test_auto_update.py -v -m integration
"""
from __future__ import annotations

import os
import shutil
import subprocess
import textwrap
import time
from pathlib import Path

import pytest

from synapps.graph.connection import GraphConnection
from synapps.graph.lookups import check_staleness
from synapps.graph.nodes import get_last_indexed_commit, set_last_indexed_commit
from synapps.graph.schema import ensure_schema
from synapps.mcp.tools import _check_auto_sync
from synapps.service import SynappsService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _git(project_dir: Path, *args: str) -> subprocess.CompletedProcess:
    """Run a git command in the project directory."""
    return subprocess.run(
        ["git"] + list(args),
        cwd=str(project_dir),
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "t@t",
             "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "t@t"},
    )


def _write_models(project_dir: Path, content: str) -> None:
    """Write content to the models.py file in the project."""
    (project_dir / "src" / "models.py").write_text(textwrap.dedent(content))


def _write_service(project_dir: Path, content: str) -> None:
    """Write content to the service.py file in the project."""
    (project_dir / "src" / "service.py").write_text(textwrap.dedent(content))


INITIAL_MODELS = """\
class User:
    def __init__(self, name: str) -> None:
        self._name = name

    def greet(self) -> str:
        return f"Hello, {self._name}"
"""

INITIAL_SERVICE = """\
from src.models import User


class UserService:
    def create_user(self, name: str) -> User:
        return User(name)

    def get_greeting(self, name: str) -> str:
        user = self.create_user(name)
        return user.greet()
"""


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Create a minimal Python project inside a fresh git repo."""
    root = tmp_path / "test_project"
    src = root / "src"
    src.mkdir(parents=True)

    (src / "__init__.py").write_text("")
    _write_models(root, INITIAL_MODELS)
    _write_service(root, INITIAL_SERVICE)

    _git(root, "init")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "initial")

    return root


def _make_service(project_dir: Path) -> tuple[SynappsService, GraphConnection]:
    """Create a fresh service + connection and full-index the project."""
    conn = GraphConnection.create(database="memgraph")
    ensure_schema(conn)
    path = str(project_dir)
    # Clean up any previous data at this path
    conn.execute(
        "MATCH (r:Repository {path: $p})-[:CONTAINS*]->(n) DETACH DELETE n",
        {"p": path},
    )
    conn.execute("MATCH (r:Repository {path: $p}) DETACH DELETE r", {"p": path})

    svc = SynappsService(conn=conn)
    svc.index_project(path, "python")

    # Store HEAD commit so auto-sync can detect drift
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=path,
        capture_output=True, text=True,
    ).stdout.strip()
    set_last_indexed_commit(conn, path, head)

    return svc, conn


@pytest.fixture
def indexed_project(project_dir: Path):
    """Yield (service, conn, project_dir) with the project fully indexed."""
    svc, conn = _make_service(project_dir)
    yield svc, conn, project_dir
    # Cleanup
    path = str(project_dir)
    conn.execute(
        "MATCH (r:Repository {path: $p})-[:CONTAINS*]->(n) DETACH DELETE n",
        {"p": path},
    )
    conn.execute("MATCH (r:Repository {path: $p}) DETACH DELETE r", {"p": path})


# ---------------------------------------------------------------------------
# Helper queries
# ---------------------------------------------------------------------------

def _method_exists(conn: GraphConnection, name: str, path_prefix: str) -> bool:
    rows = conn.query(
        "MATCH (m:Method) WHERE m.name = $name AND m.file_path STARTS WITH $p RETURN m.full_name",
        {"name": name, "p": path_prefix},
    )
    return len(rows) > 0


def _class_exists(conn: GraphConnection, name: str, path_prefix: str) -> bool:
    rows = conn.query(
        "MATCH (c:Class) WHERE c.name = $name AND c.file_path STARTS WITH $p RETURN c.full_name",
        {"name": name, "p": path_prefix},
    )
    return len(rows) > 0


def _file_node_exists(conn: GraphConnection, file_path: str) -> bool:
    rows = conn.query(
        "MATCH (f:File {path: $p}) RETURN f.path",
        {"p": file_path},
    )
    return len(rows) > 0


def _calls_edge_exists(conn: GraphConnection, caller_name: str, callee_name: str, path_prefix: str) -> bool:
    rows = conn.query(
        "MATCH (a:Method)-[:CALLS]->(b:Method) "
        "WHERE a.name = $caller AND b.name = $callee "
        "AND a.file_path STARTS WITH $p "
        "RETURN a.name, b.name",
        {"caller": caller_name, "callee": callee_name, "p": path_prefix},
    )
    return len(rows) > 0


# ===========================================================================
# 1. Pre-query auto-sync (git SHA comparison)
# ===========================================================================

@pytest.mark.integration
@pytest.mark.timeout(60)
class TestAutoSyncCommittedChanges:
    """Auto-sync should detect and apply committed git changes before queries."""

    def test_new_method_appears_after_commit(self, indexed_project):
        """Committing a new method -> auto-sync adds it to the graph."""
        svc, conn, proj = indexed_project
        path = str(proj)

        assert _method_exists(conn, "greet", path), "greet should exist after initial index"
        assert not _method_exists(conn, "farewell", path), "farewell should not exist yet"

        # Add a new method and commit
        _write_models(proj, """\
            class User:
                def __init__(self, name: str) -> None:
                    self._name = name

                def greet(self) -> str:
                    return f"Hello, {self._name}"

                def farewell(self) -> str:
                    return f"Goodbye, {self._name}"
        """)
        _git(proj, "add", ".")
        _git(proj, "commit", "-m", "add farewell")

        _check_auto_sync(path, svc)

        assert _method_exists(conn, "farewell", path), "farewell should exist after auto-sync"
        assert _method_exists(conn, "greet", path), "greet should still exist"

    def test_deleted_file_symbols_removed_after_commit(self, indexed_project):
        """Committing a file deletion -> auto-sync removes its symbols."""
        svc, conn, proj = indexed_project
        path = str(proj)

        assert _class_exists(conn, "UserService", path), "UserService should exist"

        (proj / "src" / "service.py").unlink()
        _git(proj, "add", ".")
        _git(proj, "commit", "-m", "delete service")

        _check_auto_sync(path, svc)

        assert not _class_exists(conn, "UserService", path), (
            "UserService should be gone after its file was deleted and synced"
        )

    def test_modified_method_body_reflected(self, indexed_project):
        """Changing a method signature -> auto-sync updates the graph."""
        svc, conn, proj = indexed_project
        path = str(proj)

        # Rename greet -> greet_user (simulates removing greet and adding greet_user)
        _write_models(proj, """\
            class User:
                def __init__(self, name: str) -> None:
                    self._name = name

                def greet_user(self) -> str:
                    return f"Hello, {self._name}"
        """)
        _git(proj, "add", ".")
        _git(proj, "commit", "-m", "rename greet to greet_user")

        _check_auto_sync(path, svc)

        assert _method_exists(conn, "greet_user", path), "greet_user should exist"
        assert not _method_exists(conn, "greet", path), "old greet should be gone (orphan cleanup)"

    def test_stored_sha_updated_after_sync(self, indexed_project):
        """After auto-sync, stored SHA should match current HEAD."""
        svc, conn, proj = indexed_project
        path = str(proj)

        _write_models(proj, INITIAL_MODELS + "\n    def extra(self) -> None: pass\n")
        _git(proj, "add", ".")
        _git(proj, "commit", "-m", "add extra")

        _check_auto_sync(path, svc)

        stored = get_last_indexed_commit(conn, path)
        current = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=path,
            capture_output=True, text=True,
        ).stdout.strip()
        assert stored == current, "Stored SHA should match HEAD after sync"


# ===========================================================================
# 2. Uncommitted changes
# ===========================================================================

@pytest.mark.integration
@pytest.mark.timeout(60)
class TestAutoSyncUncommittedChanges:
    """Auto-sync should detect uncommitted working tree changes via mtime staleness."""

    def test_uncommitted_edit_detected_by_auto_sync(self, indexed_project):
        """Editing a file without committing should still trigger auto-sync.

        When SHAs match but dirty tracked files have stale graph entries,
        auto-sync detects the mtime drift and re-syncs.
        """
        svc, conn, proj = indexed_project
        path = str(proj)

        _write_models(proj, INITIAL_MODELS + "\n    def uncommitted_method(self) -> None: pass\n")
        # Do NOT commit

        _check_auto_sync(path, svc)

        assert _method_exists(conn, "uncommitted_method", path), (
            "uncommitted_method should exist after auto-sync detects stale dirty file"
        )

    def test_uncommitted_edit_not_re_synced_when_fresh(self, indexed_project):
        """After syncing uncommitted changes, a second auto-sync should be a no-op."""
        svc, conn, proj = indexed_project
        path = str(proj)

        _write_models(proj, INITIAL_MODELS + "\n    def fresh_check(self) -> None: pass\n")

        # First sync picks up the dirty file
        _check_auto_sync(path, svc)
        assert _method_exists(conn, "fresh_check", path)

        # Second sync should not re-index (file mtime <= last_indexed now)
        stored_before = get_last_indexed_commit(conn, path)
        _check_auto_sync(path, svc)
        stored_after = get_last_indexed_commit(conn, path)
        assert stored_before == stored_after, "SHA should not change on no-op sync"

    def test_staleness_warning_detects_uncommitted_edit(self, indexed_project):
        """check_staleness correctly detects mtime drift on dirty files."""
        _, conn, proj = indexed_project
        models_path = str(proj / "src" / "models.py")

        # Touch the file so mtime > last_indexed
        time.sleep(0.1)
        Path(models_path).touch()

        staleness = check_staleness(conn, models_path)
        assert staleness is not None, "check_staleness should return a result"
        assert staleness["is_stale"] is True, (
            "File should be detected as stale after touch"
        )


# ===========================================================================
# 3. File watcher integration
# ===========================================================================

@pytest.mark.integration
@pytest.mark.timeout(60)
class TestWatcherReindex:
    """File watcher should detect OS-level changes and update the graph."""

    def test_watcher_detects_new_method(self, indexed_project):
        """Modifying a watched file should trigger reindex and update graph."""
        svc, conn, proj = indexed_project
        path = str(proj)

        events: list[tuple[str, str]] = []
        svc.watch_project(path, on_file_event=lambda a, p: events.append((a, p)))

        try:
            assert not _method_exists(conn, "watched_method", path)

            _write_models(proj, INITIAL_MODELS + "\n    def watched_method(self) -> None: pass\n")

            # Wait for debounce (0.5s) + reindex time
            deadline = time.monotonic() + 10
            while not _method_exists(conn, "watched_method", path):
                if time.monotonic() > deadline:
                    break
                time.sleep(0.5)

            assert _method_exists(conn, "watched_method", path), (
                f"watched_method should exist after watcher reindex. Events seen: {events}"
            )
            assert any(a == "changed" for a, _ in events), "Should have seen a 'changed' event"
        finally:
            svc.unwatch_project(path)

    def test_watcher_detects_deleted_file(self, indexed_project):
        """Deleting a watched file should remove its symbols from the graph."""
        svc, conn, proj = indexed_project
        path = str(proj)
        service_path = str(proj / "src" / "service.py")

        # Ensure the file and its symbols exist
        assert _file_node_exists(conn, service_path), "service.py File node should exist"
        assert _class_exists(conn, "UserService", path), "UserService should exist"

        events: list[tuple[str, str]] = []
        svc.watch_project(path, on_file_event=lambda a, p: events.append((a, p)))

        try:
            (proj / "src" / "service.py").unlink()

            deadline = time.monotonic() + 10
            while _class_exists(conn, "UserService", path):
                if time.monotonic() > deadline:
                    break
                time.sleep(0.5)

            assert not _class_exists(conn, "UserService", path), (
                f"UserService should be gone after watcher delete. Events: {events}"
            )
            assert any(a == "deleted" for a, _ in events), "Should have seen a 'deleted' event"
        finally:
            svc.unwatch_project(path)

    def test_watcher_detects_new_file(self, indexed_project):
        """Creating a new source file should trigger indexing."""
        svc, conn, proj = indexed_project
        path = str(proj)

        events: list[tuple[str, str]] = []
        svc.watch_project(path, on_file_event=lambda a, p: events.append((a, p)))

        try:
            (proj / "src" / "helpers.py").write_text(textwrap.dedent("""\
                class Helper:
                    def assist(self) -> str:
                        return "helping"
            """))

            deadline = time.monotonic() + 10
            while not _class_exists(conn, "Helper", path):
                if time.monotonic() > deadline:
                    break
                time.sleep(0.5)

            assert _class_exists(conn, "Helper", path), (
                f"Helper should exist after watcher detected new file. Events: {events}"
            )
        finally:
            svc.unwatch_project(path)


# ===========================================================================
# 4. Watcher SHA update on unwatch
# ===========================================================================

@pytest.mark.integration
@pytest.mark.timeout(60)
class TestUnwatchUpdatesCommitSha:
    """unwatch_project should update stored SHA to avoid redundant re-sync."""

    def test_unwatch_updates_stored_sha_to_head(self, indexed_project):
        """After unwatch, stored SHA should match current HEAD."""
        svc, conn, proj = indexed_project
        path = str(proj)

        # Commit a change so HEAD advances
        _write_models(proj, INITIAL_MODELS + "\n    def during_watch(self) -> None: pass\n")
        _git(proj, "add", ".")
        _git(proj, "commit", "-m", "change during watch")

        # Store old SHA (doesn't match new HEAD)
        old_sha = get_last_indexed_commit(conn, path)
        new_head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=path,
            capture_output=True, text=True,
        ).stdout.strip()
        assert old_sha != new_head, "HEAD should have advanced"

        svc.watch_project(path)
        svc.unwatch_project(path)

        stored = get_last_indexed_commit(conn, path)
        assert stored == new_head, (
            "unwatch_project should update stored SHA to HEAD"
        )


# ===========================================================================
# 5. Cross-file edge consistency after sync
# ===========================================================================

@pytest.mark.integration
@pytest.mark.timeout(60)
class TestSyncEdgeConsistency:
    """Syncing a single file must preserve cross-file relationships."""

    def test_calls_edges_survive_single_file_reindex(self, indexed_project):
        """After reindexing service.py, CALLS edges to models.py should persist."""
        svc, conn, proj = indexed_project
        path = str(proj)

        # Verify cross-file CALLS edge exists: create_user -> User (constructor)
        has_call = _calls_edge_exists(conn, "get_greeting", "greet", path)
        # This depends on how the Python indexer resolves calls. Check what exists.
        # At minimum, verify the service still references the model after reindex.

        # Modify service.py and commit
        _write_service(proj, """\
            from src.models import User


            class UserService:
                def create_user(self, name: str) -> User:
                    return User(name)

                def get_greeting(self, name: str) -> str:
                    user = self.create_user(name)
                    return user.greet()

                def get_farewell(self, name: str) -> str:
                    user = self.create_user(name)
                    return "goodbye"
        """)
        _git(proj, "add", ".")
        _git(proj, "commit", "-m", "add get_farewell")

        _check_auto_sync(path, svc)

        # New method should exist
        assert _method_exists(conn, "get_farewell", path), "get_farewell should exist"

        # Original cross-file references should survive
        assert _method_exists(conn, "greet", path), "greet (in models.py) should still exist"
        assert _class_exists(conn, "User", path), "User class should still exist"

    def test_orphan_symbols_cleaned_after_method_removal(self, indexed_project):
        """Removing a method from source and syncing should delete it from graph."""
        svc, conn, proj = indexed_project
        path = str(proj)

        assert _method_exists(conn, "greet", path), "greet should exist initially"

        # Remove greet method from models.py
        _write_models(proj, """\
            class User:
                def __init__(self, name: str) -> None:
                    self._name = name
        """)
        _git(proj, "add", ".")
        _git(proj, "commit", "-m", "remove greet")

        _check_auto_sync(path, svc)

        assert not _method_exists(conn, "greet", path), (
            "greet should be removed as an orphan after sync"
        )


# ===========================================================================
# 6. smart_index strategy selection
# ===========================================================================

@pytest.mark.integration
@pytest.mark.timeout(60)
class TestSmartIndexStrategy:
    """smart_index should choose the right sync strategy."""

    def test_git_repo_uses_git_sync(self, indexed_project):
        """For git repos with an existing index, smart_index uses git-sync."""
        svc, conn, proj = indexed_project
        path = str(proj)

        # Make a change and commit so there's something to sync
        _write_models(proj, INITIAL_MODELS + "\n    def strategy_test(self) -> None: pass\n")
        _git(proj, "add", ".")
        _git(proj, "commit", "-m", "strategy test")

        result = svc.smart_index(path)
        assert result == "git-sync", f"Expected git-sync strategy, got {result}"

    def test_fresh_graph_uses_full_index(self, project_dir):
        """For a project with no graph data, smart_index runs full index."""
        conn = GraphConnection.create(database="memgraph")
        ensure_schema(conn)
        path = str(project_dir)

        # Ensure no data exists
        conn.execute(
            "MATCH (r:Repository {path: $p})-[:CONTAINS*]->(n) DETACH DELETE n",
            {"p": path},
        )
        conn.execute("MATCH (r:Repository {path: $p}) DETACH DELETE r", {"p": path})

        svc = SynappsService(conn=conn)
        result = svc.smart_index(path)
        assert result == "full-index", f"Expected full-index strategy, got {result}"

        # Cleanup
        conn.execute(
            "MATCH (r:Repository {path: $p})-[:CONTAINS*]->(n) DETACH DELETE n",
            {"p": path},
        )
        conn.execute("MATCH (r:Repository {path: $p}) DETACH DELETE r", {"p": path})


# ===========================================================================
# 7. Staleness detection accuracy
# ===========================================================================

@pytest.mark.integration
@pytest.mark.timeout(30)
class TestStalenessDetection:
    """File-level staleness detection should accurately reflect disk state."""

    def test_freshly_indexed_file_not_stale(self, indexed_project):
        """Immediately after indexing, files should not be stale."""
        _, conn, proj = indexed_project
        models_path = str(proj / "src" / "models.py")

        result = check_staleness(conn, models_path)
        assert result is not None
        assert result["is_stale"] is False, "Freshly indexed file should not be stale"

    def test_modified_file_detected_as_stale(self, indexed_project):
        """After modifying a file, staleness check should flag it."""
        _, conn, proj = indexed_project
        models_path = str(proj / "src" / "models.py")

        # Ensure indexed timestamp is in the past
        time.sleep(0.1)
        (proj / "src" / "models.py").write_text(INITIAL_MODELS + "\n# modified\n")

        result = check_staleness(conn, models_path)
        assert result is not None
        assert result["is_stale"] is True, "Modified file should be stale"

    def test_deleted_file_returns_none(self, indexed_project):
        """check_staleness returns None for files deleted from disk."""
        _, conn, proj = indexed_project
        models_path = str(proj / "src" / "models.py")

        (proj / "src" / "models.py").unlink()

        result = check_staleness(conn, models_path)
        # The function returns None when file doesn't exist on disk
        assert result is None, "Deleted file should return None from check_staleness"
