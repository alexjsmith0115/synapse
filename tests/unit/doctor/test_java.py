from __future__ import annotations

from unittest.mock import patch

import pytest

from synapps.doctor.checks.java import JavaCheck
from synapps.doctor.checks.jdtls import JdtlsCheck


# ---------------------------------------------------------------------------
# JavaCheck tests (LANG-07)
# ---------------------------------------------------------------------------


def test_java_pass_when_version_sufficient() -> None:
    with patch("synapps.doctor.checks.java.check_java_version") as mock_check:
        mock_check.return_value = (True, 21, "Java 21 detected (meets JDK 17+ requirement)")
        result = JavaCheck().run()
    assert result.status == "pass"
    assert result.fix is None
    assert "21" in result.detail


def test_java_fail_when_not_on_path() -> None:
    with patch("synapps.doctor.checks.java.check_java_version") as mock_check:
        mock_check.return_value = (
            False, None,
            "Java is not installed or is not on PATH.\nPlease install JDK 17+",
        )
        result = JavaCheck().run()
    assert result.status == "fail"
    assert result.fix is not None
    assert "not installed" in result.detail.lower() or "not on PATH" in result.detail


def test_java_fail_when_version_too_old() -> None:
    with patch("synapps.doctor.checks.java.check_java_version") as mock_check:
        mock_check.return_value = (
            False, 8,
            "Java 8 was detected but JDK 17+ is required.\nPlease install JDK 17+",
        )
        result = JavaCheck().run()
    assert result.status == "fail"
    assert result.fix is not None
    assert "8" in result.detail


def test_java_fail_when_version_unknown() -> None:
    with patch("synapps.doctor.checks.java.check_java_version") as mock_check:
        mock_check.return_value = (
            False, None,
            "Could not determine the installed Java version.\nPlease install JDK 17+",
        )
        result = JavaCheck().run()
    assert result.status == "fail"
    assert result.fix is not None


def test_java_group_is_java() -> None:
    assert JavaCheck().group == "java"


# ---------------------------------------------------------------------------
# JdtlsCheck tests (LANG-08)
# ---------------------------------------------------------------------------


def test_jdtls_pass_when_launcher_jar_exists() -> None:
    with patch("synapps.doctor.checks.jdtls.shutil") as mock_shutil, \
         patch("synapps.doctor.checks.jdtls.glob") as mock_glob:
        mock_shutil.which.return_value = "/usr/bin/java"
        mock_glob.glob.return_value = [
            "/home/user/.solidlsp/language_servers/static/EclipseJDTLS/jdtls/plugins/org.eclipse.equinox.launcher_1.7.100.jar"
        ]
        result = JdtlsCheck().run()
    assert result.status == "pass"
    assert result.fix is None
    assert "org.eclipse.equinox.launcher" in result.detail


def test_jdtls_fail_when_launcher_jar_missing() -> None:
    with patch("synapps.doctor.checks.jdtls.shutil") as mock_shutil, \
         patch("synapps.doctor.checks.jdtls.glob") as mock_glob:
        mock_shutil.which.return_value = "/usr/bin/java"
        mock_glob.glob.return_value = []
        result = JdtlsCheck().run()
    assert result.status == "fail"
    assert result.fix is not None
    assert "eclipse-jdtls" in result.fix or "github.com/eclipse" in result.fix


def test_jdtls_warn_when_java_absent() -> None:
    with patch("synapps.doctor.checks.jdtls.shutil") as mock_shutil:
        mock_shutil.which.return_value = None
        result = JdtlsCheck().run()
    assert result.status == "warn"
    assert result.fix is None


def test_jdtls_group_is_java() -> None:
    assert JdtlsCheck().group == "java"
