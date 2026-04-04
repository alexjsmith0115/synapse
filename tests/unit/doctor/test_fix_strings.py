from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import docker.errors
import pytest

from synapps.doctor.checks.docker_daemon import DockerDaemonCheck
from synapps.doctor.checks.memgraph_bolt import MemgraphBoltCheck
from synapps.doctor.checks.dotnet import DotNetCheck
from synapps.doctor.checks.node import NodeCheck
from synapps.doctor.checks.typescript_ls import TypeScriptLSCheck
from synapps.doctor.checks.python3 import PythonCheck
from synapps.doctor.checks.java import JavaCheck
from synapps.doctor.checks.jdtls import JdtlsCheck
from synapps.doctor.checks.csharp_ls import CSharpLSCheck
from synapps.doctor.checks.pylsp import PylspCheck


# --- DockerDaemonCheck ---


@pytest.mark.parametrize("system,expected_substr", [
    ("Darwin", "open -a Docker"),
    ("Linux", "sudo systemctl start docker"),
])
def test_docker_daemon_fix_platform_aware(system: str, expected_substr: str) -> None:
    with patch("synapps.doctor.checks.docker_daemon.docker") as mock_docker:
        mock_docker.errors.DockerException = docker.errors.DockerException
        mock_docker.from_env.return_value.ping.side_effect = docker.errors.DockerException("no daemon")
        with patch("synapps.doctor.checks.docker_daemon.platform") as mock_plat:
            mock_plat.system.return_value = system
            result = DockerDaemonCheck().run()
    assert result.fix is not None
    assert expected_substr in result.fix


# --- MemgraphBoltCheck ---


def test_memgraph_fix_contains_docker_ps() -> None:
    with patch("synapps.doctor.checks.memgraph_bolt.docker") as mock_docker, \
         patch("synapps.doctor.checks.memgraph_bolt.socket") as mock_socket:
        mock_docker.errors.DockerException = docker.errors.DockerException
        mock_docker.from_env.return_value.ping.return_value = None
        mock_socket.create_connection.side_effect = OSError("refused")
        result = MemgraphBoltCheck().run()
    assert result.fix is not None
    assert "docker ps" in result.fix


def test_memgraph_fix_contains_docker_compose_up() -> None:
    with patch("synapps.doctor.checks.memgraph_bolt.docker") as mock_docker, \
         patch("synapps.doctor.checks.memgraph_bolt.socket") as mock_socket:
        mock_docker.errors.DockerException = docker.errors.DockerException
        mock_docker.from_env.return_value.ping.return_value = None
        mock_socket.create_connection.side_effect = OSError("refused")
        result = MemgraphBoltCheck().run()
    assert result.fix is not None
    assert "docker compose up -d" in result.fix


# --- DotNetCheck ---


@pytest.mark.parametrize("system,expected_substr", [
    ("Darwin", "brew install dotnet"),
    ("Linux", "sudo apt-get install dotnet-sdk"),
])
def test_dotnet_fix_platform_aware(system: str, expected_substr: str) -> None:
    with patch("synapps.doctor.checks.dotnet.shutil") as mock_shutil, \
         patch("synapps.doctor.checks.dotnet.platform") as mock_plat:
        mock_shutil.which.return_value = None
        mock_plat.system.return_value = system
        result = DotNetCheck().run()
    assert result.fix is not None
    assert expected_substr in result.fix


# --- NodeCheck ---


@pytest.mark.parametrize("system,expected_substr", [
    ("Darwin", "brew install node"),
    ("Linux", "sudo apt-get install nodejs"),
])
def test_node_fix_platform_aware(system: str, expected_substr: str) -> None:
    with patch("synapps.doctor.checks.node.shutil") as mock_shutil, \
         patch("synapps.doctor.checks.node.platform") as mock_plat:
        mock_shutil.which.return_value = None
        mock_plat.system.return_value = system
        result = NodeCheck().run()
    assert result.fix is not None
    assert expected_substr in result.fix


# --- TypeScriptLSCheck ---


@pytest.mark.parametrize("system,expected_substr", [
    ("Darwin", "brew install node"),
    ("Linux", "sudo apt-get install npm"),
])
def test_typescript_ls_fix_platform_aware(system: str, expected_substr: str) -> None:
    with patch("synapps.doctor.checks.typescript_ls.shutil") as mock_shutil, \
         patch("synapps.doctor.checks.typescript_ls.platform") as mock_plat:
        mock_shutil.which.side_effect = lambda name: "/usr/local/bin/node" if name == "node" else None
        mock_plat.system.return_value = system
        result = TypeScriptLSCheck().run()
    assert result.fix is not None
    assert expected_substr in result.fix


# --- PythonCheck ---


@pytest.mark.parametrize("system,expected_substr", [
    ("Darwin", "brew install python3"),
    ("Linux", "sudo apt-get install python3"),
])
def test_python_fix_platform_aware(system: str, expected_substr: str) -> None:
    with patch("synapps.doctor.checks.python3.shutil") as mock_shutil, \
         patch("synapps.doctor.checks.python3.platform") as mock_plat:
        mock_shutil.which.return_value = None
        mock_plat.system.return_value = system
        result = PythonCheck().run()
    assert result.fix is not None
    assert expected_substr in result.fix


# --- JavaCheck ---


@pytest.mark.parametrize("system,expected_substr", [
    ("Darwin", "brew install --cask temurin"),
    ("Linux", "sudo apt-get install default-jdk"),
])
def test_java_fix_platform_aware(system: str, expected_substr: str) -> None:
    with patch("synapps.doctor.checks.java.shutil") as mock_shutil, \
         patch("synapps.doctor.checks.java.platform") as mock_plat:
        mock_shutil.which.return_value = None
        mock_plat.system.return_value = system
        result = JavaCheck().run()
    assert result.fix is not None
    assert expected_substr in result.fix


# --- JdtlsCheck ---


@pytest.mark.parametrize("system,expected_substr", [
    ("Darwin", "brew install jdtls"),
    ("Linux", "https://github.com/eclipse-jdtls/eclipse.jdt.ls"),
])
def test_jdtls_fix_platform_aware(system: str, expected_substr: str) -> None:
    with patch("synapps.doctor.checks.jdtls.shutil") as mock_shutil, \
         patch("synapps.doctor.checks.jdtls.glob") as mock_glob, \
         patch("synapps.doctor.checks.jdtls.platform") as mock_plat:
        mock_shutil.which.return_value = "/usr/bin/java"
        mock_glob.glob.return_value = []
        mock_plat.system.return_value = system
        result = JdtlsCheck().run()
    assert result.fix is not None
    assert expected_substr in result.fix


# --- CSharpLSCheck (unchanged — verify fix still works) ---


def test_csharp_ls_fix_contains_synapps_index() -> None:
    with patch("synapps.doctor.checks.csharp_ls.subprocess") as mock_sub, \
         patch("synapps.doctor.checks.csharp_ls.glob") as mock_glob:
        mock_sub.run.return_value.returncode = 0
        mock_sub.TimeoutExpired = subprocess.TimeoutExpired
        mock_glob.glob.return_value = []
        result = CSharpLSCheck().run()
    assert result.fix is not None
    assert "synapps index" in result.fix


# --- PylspCheck (unchanged — verify fix still works) ---


def test_pylsp_fix_contains_pyright() -> None:
    with patch("synapps.doctor.checks.pylsp.subprocess") as mock_sub:
        mock_sub.run.return_value = MagicMock(returncode=1, stdout="", stderr="ModuleNotFoundError")
        mock_sub.TimeoutExpired = subprocess.TimeoutExpired
        result = PylspCheck().run()
    assert result.fix is not None
    assert "pyright" in result.fix
