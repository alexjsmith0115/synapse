from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from synapps.util.file_system import ProjectFileFilter

log = logging.getLogger(__name__)


class FileWatcher:
    """Watches a directory for source file changes and calls back on modify/delete."""

    def __init__(
        self,
        root_path: str,
        on_change: Callable[[str], None],
        on_delete: Callable[[str], None],
        debounce_seconds: float = 0.5,
        watched_extensions: frozenset[str] | None = None,
    ) -> None:
        self._root_path = root_path
        self._on_change = on_change
        self._on_delete = on_delete
        self._debounce_seconds = debounce_seconds
        self._watched_extensions = watched_extensions or frozenset({".cs"})
        self._observer = Observer()
        self._debounce_timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()
        self._file_filter = ProjectFileFilter(root_path)

    def start(self) -> None:
        handler = _ChangeHandler(
            self._on_change, self._on_delete, self._debounce_seconds,
            self._debounce_timers, self._lock, self._watched_extensions,
            self._file_filter,
        )
        self._observer.schedule(handler, self._root_path, recursive=True)
        self._observer.start()

    def stop(self) -> None:
        self._observer.stop()
        self._observer.join()
        with self._lock:
            for timer in self._debounce_timers.values():
                timer.cancel()

    def is_running(self) -> bool:
        return self._observer.is_alive()


class _ChangeHandler(FileSystemEventHandler):
    def __init__(
        self,
        on_change: Callable[[str], None],
        on_delete: Callable[[str], None],
        debounce_seconds: float,
        timers: dict[str, threading.Timer],
        lock: threading.Lock,
        watched_extensions: frozenset[str],
        file_filter: ProjectFileFilter,
    ) -> None:
        self._on_change = on_change
        self._on_delete = on_delete
        self._debounce_seconds = debounce_seconds
        self._timers = timers
        self._lock = lock
        self._watched_extensions = watched_extensions
        self._file_filter = file_filter

    def _should_handle(self, event: FileSystemEvent) -> bool:
        if event.is_directory:
            return False
        if Path(event.src_path).suffix not in self._watched_extensions:
            return False
        if self._file_filter.is_file_ignored(event.src_path):
            return False
        return True

    def on_modified(self, event: FileSystemEvent) -> None:
        if self._should_handle(event):
            self._debounce(event.src_path, self._on_change)

    def on_created(self, event: FileSystemEvent) -> None:
        if self._should_handle(event):
            self._debounce(event.src_path, self._on_change)

    def on_deleted(self, event: FileSystemEvent) -> None:
        if self._should_handle(event):
            self._debounce(event.src_path, self._on_delete)

    def _debounce(self, path: str, callback: Callable[[str], None]) -> None:
        def _fire() -> None:
            callback(path)
            with self._lock:
                # Only clean up if this timer is still the active one for this path
                if self._timers.get(path) is timer:
                    del self._timers[path]

        with self._lock:
            if path in self._timers:
                self._timers[path].cancel()
            timer = threading.Timer(self._debounce_seconds, _fire)
            self._timers[path] = timer
            timer.start()
