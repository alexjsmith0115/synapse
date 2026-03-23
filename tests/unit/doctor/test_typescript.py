from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from synapse.doctor.checks.node import NodeCheck
from synapse.doctor.checks.typescript_ls import TypeScriptLSCheck


# --- NodeCheck tests ---


def test_node_pass_when_version_exits_zero() -> None:
    with patch("synapse.doctor.checks.node.shutil") as mock_shutil, \
         patch("synapse.doctor.checks.node.subprocess") as mock_sub:
        mock_shutil.which.return_value = "/usr/local/bin/node"
        mock_sub.run.return_value.returncode = 0
        mock_sub.TimeoutExpired = subprocess.TimeoutExpired
        result = NodeCheck().run()
    assert result.status == "pass"
    assert "/usr/local/bin/node" in result.detail


def test_node_fail_when_not_on_path() -> None:
    with patch("synapse.doctor.checks.node.shutil") as mock_shutil, \
         patch("synapse.doctor.checks.node.subprocess") as mock_sub:
        mock_shutil.which.return_value = None
        mock_sub.TimeoutExpired = subprocess.TimeoutExpired
        result = NodeCheck().run()
    assert result.status == "fail"
    assert result.fix is not None
    assert "nodejs.org" in result.fix


def test_node_fail_when_version_exits_nonzero() -> None:
    with patch("synapse.doctor.checks.node.shutil") as mock_shutil, \
         patch("synapse.doctor.checks.node.subprocess") as mock_sub:
        mock_shutil.which.return_value = "/usr/local/bin/node"
        mock_sub.run.return_value.returncode = 1
        mock_sub.TimeoutExpired = subprocess.TimeoutExpired
        result = NodeCheck().run()
    assert result.status == "fail"


def test_node_fail_when_timeout() -> None:
    with patch("synapse.doctor.checks.node.shutil") as mock_shutil, \
         patch("synapse.doctor.checks.node.subprocess") as mock_sub:
        mock_shutil.which.return_value = "/usr/local/bin/node"
        mock_sub.run.side_effect = subprocess.TimeoutExpired("node", 10)
        mock_sub.TimeoutExpired = subprocess.TimeoutExpired
        result = NodeCheck().run()
    assert result.status == "fail"


def test_node_group_is_typescript() -> None:
    assert NodeCheck().group == "typescript"


def test_node_pass_fix_is_none() -> None:
    with patch("synapse.doctor.checks.node.shutil") as mock_shutil, \
         patch("synapse.doctor.checks.node.subprocess") as mock_sub:
        mock_shutil.which.return_value = "/usr/local/bin/node"
        mock_sub.run.return_value.returncode = 0
        mock_sub.TimeoutExpired = subprocess.TimeoutExpired
        result = NodeCheck().run()
    assert result.fix is None


# --- TypeScriptLSCheck tests ---


def test_typescript_ls_pass_when_version_exits_zero() -> None:
    with patch("synapse.doctor.checks.typescript_ls.shutil") as mock_shutil, \
         patch("synapse.doctor.checks.typescript_ls.subprocess") as mock_sub:
        mock_shutil.which.side_effect = lambda name: {
            "node": "/usr/local/bin/node",
            "typescript-language-server": "/usr/local/bin/typescript-language-server",
        }.get(name)
        mock_sub.run.return_value.returncode = 0
        mock_sub.TimeoutExpired = subprocess.TimeoutExpired
        result = TypeScriptLSCheck().run()
    assert result.status == "pass"
    assert "/usr/local/bin/typescript-language-server" in result.detail


def test_typescript_ls_fail_when_not_on_path() -> None:
    with patch("synapse.doctor.checks.typescript_ls.shutil") as mock_shutil, \
         patch("synapse.doctor.checks.typescript_ls.subprocess") as mock_sub:
        mock_shutil.which.side_effect = lambda name: {
            "node": "/usr/local/bin/node",
            "typescript-language-server": None,
        }.get(name)
        mock_sub.TimeoutExpired = subprocess.TimeoutExpired
        result = TypeScriptLSCheck().run()
    assert result.status == "fail"
    assert result.fix is not None
    assert "npm install" in result.fix


def test_typescript_ls_warn_when_node_absent() -> None:
    with patch("synapse.doctor.checks.typescript_ls.shutil") as mock_shutil, \
         patch("synapse.doctor.checks.typescript_ls.subprocess") as mock_sub:
        mock_shutil.which.side_effect = lambda name: {
            "node": None,
        }.get(name)
        mock_sub.TimeoutExpired = subprocess.TimeoutExpired
        result = TypeScriptLSCheck().run()
    assert result.status == "warn"
    assert result.fix is None


def test_typescript_ls_fail_when_version_exits_nonzero() -> None:
    with patch("synapse.doctor.checks.typescript_ls.shutil") as mock_shutil, \
         patch("synapse.doctor.checks.typescript_ls.subprocess") as mock_sub:
        mock_shutil.which.side_effect = lambda name: {
            "node": "/usr/local/bin/node",
            "typescript-language-server": "/usr/local/bin/typescript-language-server",
        }.get(name)
        mock_sub.run.return_value.returncode = 1
        mock_sub.TimeoutExpired = subprocess.TimeoutExpired
        result = TypeScriptLSCheck().run()
    assert result.status == "fail"


def test_typescript_ls_fail_when_timeout() -> None:
    with patch("synapse.doctor.checks.typescript_ls.shutil") as mock_shutil, \
         patch("synapse.doctor.checks.typescript_ls.subprocess") as mock_sub:
        mock_shutil.which.side_effect = lambda name: {
            "node": "/usr/local/bin/node",
            "typescript-language-server": "/usr/local/bin/typescript-language-server",
        }.get(name)
        mock_sub.run.side_effect = subprocess.TimeoutExpired("typescript-language-server", 10)
        mock_sub.TimeoutExpired = subprocess.TimeoutExpired
        result = TypeScriptLSCheck().run()
    assert result.status == "fail"


def test_typescript_ls_group_is_typescript() -> None:
    assert TypeScriptLSCheck().group == "typescript"
