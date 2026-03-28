from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _make_plugin(name: str) -> MagicMock:
    plugin = MagicMock()
    plugin.name = name
    return plugin


class TestDetectLanguages:
    def test_detect_languages_returns_sorted_by_count(self) -> None:
        python_plugin = _make_plugin("python")
        ts_plugin = _make_plugin("typescript")
        mock_registry = MagicMock()
        mock_registry.detect_with_files.return_value = [
            (python_plugin, ["a.py"] * 10),
            (ts_plugin, ["b.ts"] * 5),
        ]

        with patch(
            "synapse.onboarding.language_detector.default_registry",
            return_value=mock_registry,
        ):
            from synapse.onboarding.language_detector import detect_languages

            result = detect_languages("/fake/path")

        assert result == [("python", 10), ("typescript", 5)]

    def test_detect_languages_filters_below_threshold(self) -> None:
        python_plugin = _make_plugin("python")
        mock_registry = MagicMock()
        mock_registry.detect_with_files.return_value = [
            (python_plugin, ["a.py", "b.py"]),  # only 2 files — below threshold of 3
        ]

        with patch(
            "synapse.onboarding.language_detector.default_registry",
            return_value=mock_registry,
        ):
            from synapse.onboarding.language_detector import detect_languages

            result = detect_languages("/fake/path")

        assert result == []

    def test_detect_languages_empty_project(self) -> None:
        mock_registry = MagicMock()
        mock_registry.detect_with_files.return_value = []

        with patch(
            "synapse.onboarding.language_detector.default_registry",
            return_value=mock_registry,
        ):
            from synapse.onboarding.language_detector import detect_languages

            result = detect_languages("/fake/path")

        assert result == []

    def test_detect_languages_mixed_above_and_below(self) -> None:
        python_plugin = _make_plugin("python")
        java_plugin = _make_plugin("java")
        mock_registry = MagicMock()
        mock_registry.detect_with_files.return_value = [
            (python_plugin, ["a.py"] * 10),
            (java_plugin, ["Main.java"]),  # only 1 file — below threshold
        ]

        with patch(
            "synapse.onboarding.language_detector.default_registry",
            return_value=mock_registry,
        ):
            from synapse.onboarding.language_detector import detect_languages

            result = detect_languages("/fake/path")

        assert result == [("python", 10)]
