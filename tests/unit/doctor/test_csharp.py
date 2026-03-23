from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from synapse.doctor.checks.dotnet import DotNetCheck


def test_dotnet_pass_when_list_runtimes_has_netcore_app() -> None:
    with patch("synapse.doctor.checks.dotnet.shutil") as mock_shutil, \
         patch("synapse.doctor.checks.dotnet.subprocess") as mock_sub:
        mock_shutil.which.return_value = "/usr/local/bin/dotnet"
        mock_sub.run.return_value.returncode = 0
        mock_sub.run.return_value.stdout = "Microsoft.NETCore.App 10.0.2 [/usr/local/share/dotnet/shared/Microsoft.NETCore.App/10.0.2]\n"
        mock_sub.TimeoutExpired = subprocess.TimeoutExpired
        result = DotNetCheck().run()
    assert result.status == "pass"
    assert "/usr/local/bin/dotnet" in result.detail


def test_dotnet_fail_when_not_on_path() -> None:
    with patch("synapse.doctor.checks.dotnet.shutil") as mock_shutil:
        mock_shutil.which.return_value = None
        result = DotNetCheck().run()
    assert result.status == "fail"
    assert result.fix is not None
    assert "dotnet.microsoft.com" in result.fix


def test_dotnet_fail_when_no_netcore_runtime() -> None:
    with patch("synapse.doctor.checks.dotnet.shutil") as mock_shutil, \
         patch("synapse.doctor.checks.dotnet.subprocess") as mock_sub:
        mock_shutil.which.return_value = "/usr/local/bin/dotnet"
        mock_sub.run.return_value.returncode = 0
        mock_sub.run.return_value.stdout = ""
        mock_sub.TimeoutExpired = subprocess.TimeoutExpired
        result = DotNetCheck().run()
    assert result.status == "fail"
    assert result.fix is not None


def test_dotnet_fail_when_list_runtimes_exits_nonzero() -> None:
    with patch("synapse.doctor.checks.dotnet.shutil") as mock_shutil, \
         patch("synapse.doctor.checks.dotnet.subprocess") as mock_sub:
        mock_shutil.which.return_value = "/usr/local/bin/dotnet"
        mock_sub.run.return_value.returncode = 1
        mock_sub.run.return_value.stdout = ""
        mock_sub.TimeoutExpired = subprocess.TimeoutExpired
        result = DotNetCheck().run()
    assert result.status == "fail"


def test_dotnet_fail_when_timeout() -> None:
    with patch("synapse.doctor.checks.dotnet.shutil") as mock_shutil, \
         patch("synapse.doctor.checks.dotnet.subprocess") as mock_sub:
        mock_shutil.which.return_value = "/usr/local/bin/dotnet"
        mock_sub.TimeoutExpired = subprocess.TimeoutExpired
        mock_sub.run.side_effect = subprocess.TimeoutExpired("dotnet", 10)
        result = DotNetCheck().run()
    assert result.status == "fail"


def test_dotnet_group_is_csharp() -> None:
    assert DotNetCheck().group == "csharp"
