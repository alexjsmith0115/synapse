from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

log = logging.getLogger(__name__)

_WATCHED_EXTENSIONS = {".cs"}


class FileWatcher:
    """Watches a directory for C# file changes and calls back on modify/delete."""

    def __init__(
        self,
        root_path: str,
        on_change: Callable[[str], None],
        on_delete: Callable[[str], None],
        debounce_seconds: float = 0.5,
    ) -> None:
        self._root_path = root_path
        self._on_change = on_change
        self._on_delete = on_delete
        self._debounce_seconds = debounce_seconds
        self._observer = Observer()
        self._debounce_timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def start(self) -> None:
        handler = _ChangeHandler(self._on_change, self._on_delete, self._debounce_seconds, self._debounce_timers, self._lock)
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
    ) -> None:
        self._on_change = on_change
        self._on_delete = on_delete
        self._debounce_seconds = debounce_seconds
        self._timers = timers
        self._lock = lock

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory and Path(event.src_path).suffix in _WATCHED_EXTENSIONS:
            self._debounce(event.src_path, self._on_change)

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory and Path(event.src_path).suffix in _WATCHED_EXTENSIONS:
            self._debounce(event.src_path, self._on_change)

    def on_deleted(self, event: FileSystemEvent) -> None:
        if not event.is_directory and Path(event.src_path).suffix in _WATCHED_EXTENSIONS:
            self._debounce(event.src_path, self._on_delete)

    def _debounce(self, path: str, callback: Callable[[str], None]) -> None:
        with self._lock:
            if path in self._timers:
                self._timers[path].cancel()
            timer = threading.Timer(self._debounce_seconds, callback, args=[path])
            self._timers[path] = timer
            timer.start()
