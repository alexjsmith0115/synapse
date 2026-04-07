from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from synapps.util.java import check_java_version, get_java_major_version, parse_java_version


# ---------------------------------------------------------------------------
# parse_java_version
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "output, expected",
    [
        # Modern format (JDK 9+)
        ('openjdk version "17.0.1" 2021-10-19\n', 17),
        ('openjdk version "21.0.2" 2024-01-16 LTS\n', 21),
        ('openjdk version "25.0.2" 2026-01-20 LTS\n', 25),
        ('java version "11.0.2" 2019-01-15 LTS\n', 11),
        # Legacy format (JDK 8 and earlier)
        ('java version "1.8.0_362"\n', 8),
        ('openjdk version "1.7.0_352"\n', 7),
        # Single-digit major only
        ('openjdk version "17"\n', 17),
        # No match
        ("something unexpected", None),
        ("", None),
    ],
)
def test_parse_java_version(output: str, expected: int | None) -> None:
    assert parse_java_version(output) == expected


# ---------------------------------------------------------------------------
# get_java_major_version
# ---------------------------------------------------------------------------


def test_get_java_major_version_returns_version() -> None:
    with patch("synapps.util.java.shutil") as mock_shutil, \
         patch("synapps.util.java.subprocess") as mock_sub:
        mock_shutil.which.return_value = "/usr/bin/java"
        mock_sub.run.return_value = MagicMock(
            stderr='openjdk version "17.0.1" 2021-10-19\n',
            stdout="",
        )
        mock_sub.TimeoutExpired = subprocess.TimeoutExpired
        assert get_java_major_version() == 17


def test_get_java_major_version_returns_none_when_not_installed() -> None:
    with patch("synapps.util.java.shutil") as mock_shutil:
        mock_shutil.which.return_value = None
        assert get_java_major_version() is None


def test_get_java_major_version_returns_none_on_timeout() -> None:
    with patch("synapps.util.java.shutil") as mock_shutil, \
         patch("synapps.util.java.subprocess") as mock_sub:
        mock_shutil.which.return_value = "/usr/bin/java"
        mock_sub.run.side_effect = subprocess.TimeoutExpired(cmd="java", timeout=10)
        mock_sub.TimeoutExpired = subprocess.TimeoutExpired
        assert get_java_major_version() is None


# ---------------------------------------------------------------------------
# check_java_version
# ---------------------------------------------------------------------------


def test_check_java_version_ok() -> None:
    with patch("synapps.util.java.shutil") as mock_shutil, \
         patch("synapps.util.java.subprocess") as mock_sub:
        mock_shutil.which.return_value = "/usr/bin/java"
        mock_sub.run.return_value = MagicMock(
            stderr='openjdk version "21.0.2" 2024-01-16 LTS\n',
            stdout="",
        )
        mock_sub.TimeoutExpired = subprocess.TimeoutExpired
        ok, version, message = check_java_version(minimum=17)
    assert ok is True
    assert version == 21
    assert "21" in message


def test_check_java_version_too_old() -> None:
    with patch("synapps.util.java.shutil") as mock_shutil, \
         patch("synapps.util.java.subprocess") as mock_sub:
        mock_shutil.which.return_value = "/usr/bin/java"
        mock_sub.run.return_value = MagicMock(
            stderr='java version "1.8.0_362"\n',
            stdout="",
        )
        mock_sub.TimeoutExpired = subprocess.TimeoutExpired
        ok, version, message = check_java_version(minimum=17)
    assert ok is False
    assert version == 8
    assert "8" in message
    assert "17" in message


def test_check_java_version_not_installed() -> None:
    with patch("synapps.util.java.shutil") as mock_shutil:
        mock_shutil.which.return_value = None
        ok, version, message = check_java_version(minimum=17)
    assert ok is False
    assert version is None
    assert "not installed" in message.lower() or "not on PATH" in message


def test_check_java_version_unparseable() -> None:
    with patch("synapps.util.java.shutil") as mock_shutil, \
         patch("synapps.util.java.subprocess") as mock_sub:
        mock_shutil.which.return_value = "/usr/bin/java"
        mock_sub.run.return_value = MagicMock(
            stderr="garbage output",
            stdout="",
        )
        mock_sub.TimeoutExpired = subprocess.TimeoutExpired
        ok, version, message = check_java_version(minimum=17)
    assert ok is False
    assert version is None
    assert "Could not determine" in message
