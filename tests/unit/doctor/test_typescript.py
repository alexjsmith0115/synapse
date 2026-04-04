from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from synapps.doctor.checks.node import NodeCheck
from synapps.doctor.checks.typescript_ls import TypeScriptLSCheck


# --- NodeCheck tests ---


def test_node_pass_when_version_exits_zero() -> None:
    with patch("synapps.doctor.checks.node.shutil") as mock_shutil, \
         patch("synapps.doctor.checks.node.subprocess") as mock_sub:
        mock_shutil.which.return_value = "/usr/local/bin/node"
        mock_sub.run.return_value.returncode = 0
        mock_sub.TimeoutExpired = subprocess.TimeoutExpired
        result = NodeCheck().run()
    assert result.status == "pass"
    assert result.fix is None
    assert "/usr/local/bin/node" in result.detail


def test_node_fail_when_not_on_path() -> None:
    with patch("synapps.doctor.checks.node.shutil") as mock_shutil, \
         patch("synapps.doctor.checks.node.subprocess") as mock_sub:
        mock_shutil.which.return_value = None
        mock_sub.TimeoutExpired = subprocess.TimeoutExpired
        result = NodeCheck().run()
    assert result.status == "fail"
    assert result.fix is not None
    assert "nodejs.org" in result.fix


def test_node_fail_when_version_exits_nonzero() -> None:
    with patch("synapps.doctor.checks.node.shutil") as mock_shutil, \
         patch("synapps.doctor.checks.node.subprocess") as mock_sub:
        mock_shutil.which.return_value = "/usr/local/bin/node"
        mock_sub.run.return_value.returncode = 1
        mock_sub.TimeoutExpired = subprocess.TimeoutExpired
        result = NodeCheck().run()
    assert result.status == "fail"


def test_node_fail_when_timeout() -> None:
    with patch("synapps.doctor.checks.node.shutil") as mock_shutil, \
         patch("synapps.doctor.checks.node.subprocess") as mock_sub:
        mock_shutil.which.return_value = "/usr/local/bin/node"
        mock_sub.run.side_effect = subprocess.TimeoutExpired("node", 10)
        mock_sub.TimeoutExpired = subprocess.TimeoutExpired
        result = NodeCheck().run()
    assert result.status == "fail"


def test_node_group_is_typescript() -> None:
    assert NodeCheck().group == "typescript"


# --- TypeScriptLSCheck tests (npm check) ---


def test_npm_pass_when_on_path() -> None:
    with patch("synapps.doctor.checks.typescript_ls.shutil") as mock_shutil:
        mock_shutil.which.side_effect = lambda name: {
            "node": "/usr/local/bin/node",
            "npm": "/usr/local/bin/npm",
        }.get(name)
        result = TypeScriptLSCheck().run()
    assert result.status == "pass"
    assert "/usr/local/bin/npm" in result.detail
    assert "auto-installed" in result.detail


def test_npm_fail_when_not_on_path() -> None:
    with patch("synapps.doctor.checks.typescript_ls.shutil") as mock_shutil:
        mock_shutil.which.side_effect = lambda name: {
            "node": "/usr/local/bin/node",
            "npm": None,
        }.get(name)
        result = TypeScriptLSCheck().run()
    assert result.status == "fail"
    assert result.fix is not None


def test_npm_warn_when_node_absent() -> None:
    with patch("synapps.doctor.checks.typescript_ls.shutil") as mock_shutil:
        mock_shutil.which.side_effect = lambda name: None
        result = TypeScriptLSCheck().run()
    assert result.status == "warn"
    assert result.fix is None


def test_npm_group_is_typescript() -> None:
    assert TypeScriptLSCheck().group == "typescript"
