from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from synapse.doctor.checks.python3 import PythonCheck
from synapse.doctor.checks.pylsp import PylspCheck


def test_python_pass_when_version_exits_zero() -> None:
    with patch("synapse.doctor.checks.python3.shutil") as mock_shutil:
        with patch("synapse.doctor.checks.python3.subprocess") as mock_sub:
            mock_shutil.which.return_value = "/usr/bin/python3"
            mock_sub.run.return_value = MagicMock(returncode=0)
            mock_sub.TimeoutExpired = subprocess.TimeoutExpired
            result = PythonCheck().run()
    assert result.status == "pass"
    assert "/usr/bin/python3" in result.detail


def test_python_fail_when_not_on_path() -> None:
    with patch("synapse.doctor.checks.python3.shutil") as mock_shutil:
        mock_shutil.which.return_value = None
        result = PythonCheck().run()
    assert result.status == "fail"
    assert result.fix is not None
    assert "python.org" in result.fix


def test_python_fail_when_version_exits_nonzero() -> None:
    with patch("synapse.doctor.checks.python3.shutil") as mock_shutil:
        with patch("synapse.doctor.checks.python3.subprocess") as mock_sub:
            mock_shutil.which.return_value = "/usr/bin/python3"
            mock_sub.run.return_value = MagicMock(returncode=1)
            mock_sub.TimeoutExpired = subprocess.TimeoutExpired
            result = PythonCheck().run()
    assert result.status == "fail"


def test_python_fail_when_timeout() -> None:
    with patch("synapse.doctor.checks.python3.shutil") as mock_shutil:
        with patch("synapse.doctor.checks.python3.subprocess") as mock_sub:
            mock_shutil.which.return_value = "/usr/bin/python3"
            mock_sub.run.side_effect = subprocess.TimeoutExpired(cmd="python3", timeout=10)
            mock_sub.TimeoutExpired = subprocess.TimeoutExpired
            result = PythonCheck().run()
    assert result.status == "fail"


def test_python_group_is_python() -> None:
    assert PythonCheck().group == "python"


def test_python_pass_fix_is_none() -> None:
    with patch("synapse.doctor.checks.python3.shutil") as mock_shutil:
        with patch("synapse.doctor.checks.python3.subprocess") as mock_sub:
            mock_shutil.which.return_value = "/usr/bin/python3"
            mock_sub.run.return_value = MagicMock(returncode=0)
            mock_sub.TimeoutExpired = subprocess.TimeoutExpired
            result = PythonCheck().run()
    assert result.fix is None


# ---- PylspCheck tests ----


def test_pylsp_pass_when_version_exits_zero() -> None:
    with patch("synapse.doctor.checks.pylsp.shutil") as mock_shutil:
        with patch("synapse.doctor.checks.pylsp.subprocess") as mock_sub:
            mock_shutil.which.side_effect = lambda name: {
                "python3": "/usr/bin/python3",
                "pylsp": "/usr/bin/pylsp",
            }.get(name)
            mock_sub.run.return_value = MagicMock(returncode=0)
            mock_sub.TimeoutExpired = subprocess.TimeoutExpired
            result = PylspCheck().run()
    assert result.status == "pass"
    assert "/usr/bin/pylsp" in result.detail


def test_pylsp_fail_when_not_on_path() -> None:
    with patch("synapse.doctor.checks.pylsp.shutil") as mock_shutil:
        with patch("synapse.doctor.checks.pylsp.subprocess") as mock_sub:
            mock_shutil.which.side_effect = lambda name: {
                "python3": "/usr/bin/python3",
                "pylsp": None,
            }.get(name)
            mock_sub.TimeoutExpired = subprocess.TimeoutExpired
            result = PylspCheck().run()
    assert result.status == "fail"
    assert result.fix is not None
    assert "pip install" in result.fix


def test_pylsp_warn_when_python3_absent() -> None:
    with patch("synapse.doctor.checks.pylsp.shutil") as mock_shutil:
        mock_shutil.which.side_effect = lambda name: None
        result = PylspCheck().run()
    assert result.status == "warn"
    assert result.fix is None


def test_pylsp_fail_when_version_exits_nonzero() -> None:
    with patch("synapse.doctor.checks.pylsp.shutil") as mock_shutil:
        with patch("synapse.doctor.checks.pylsp.subprocess") as mock_sub:
            mock_shutil.which.side_effect = lambda name: {
                "python3": "/usr/bin/python3",
                "pylsp": "/usr/bin/pylsp",
            }.get(name)
            mock_sub.run.return_value = MagicMock(returncode=1)
            mock_sub.TimeoutExpired = subprocess.TimeoutExpired
            result = PylspCheck().run()
    assert result.status == "fail"


def test_pylsp_fail_when_timeout() -> None:
    with patch("synapse.doctor.checks.pylsp.shutil") as mock_shutil:
        with patch("synapse.doctor.checks.pylsp.subprocess") as mock_sub:
            mock_shutil.which.side_effect = lambda name: {
                "python3": "/usr/bin/python3",
                "pylsp": "/usr/bin/pylsp",
            }.get(name)
            mock_sub.run.side_effect = subprocess.TimeoutExpired(cmd="pylsp", timeout=10)
            mock_sub.TimeoutExpired = subprocess.TimeoutExpired
            result = PylspCheck().run()
    assert result.status == "fail"


def test_pylsp_group_is_python() -> None:
    assert PylspCheck().group == "python"
