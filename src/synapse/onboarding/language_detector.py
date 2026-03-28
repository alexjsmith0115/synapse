from __future__ import annotations

from synapse.plugin import default_registry

_MIN_FILE_COUNT = 3


def detect_languages(root_path: str) -> list[tuple[str, int]]:
    """Return [(language_name, file_count)] sorted by file_count descending.

    Languages with fewer than _MIN_FILE_COUNT files are excluded to avoid
    false positives from stray config files.
    """
    registry = default_registry()
    detected = registry.detect_with_files(root_path)
    results = [
        (plugin.name, len(files))
        for plugin, files in detected
        if len(files) >= _MIN_FILE_COUNT
    ]
    results.sort(key=lambda x: x[1], reverse=True)
    return results
