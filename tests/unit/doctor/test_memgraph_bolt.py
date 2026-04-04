from __future__ import annotations

from unittest.mock import MagicMock, patch

import docker.errors
import pytest

from synapps.doctor.checks.memgraph_bolt import MemgraphBoltCheck


def test_memgraph_warns_when_docker_unavailable() -> None:
    with patch("synapps.doctor.checks.memgraph_bolt.docker") as mock_docker:
        mock_docker.errors.DockerException = docker.errors.DockerException
        mock_docker.from_env.return_value.ping.side_effect = docker.errors.DockerException("no docker")
        result = MemgraphBoltCheck().run()
    assert result.status == "warn"
    assert result.fix is None
    assert "Docker not available" in result.detail


def test_memgraph_fail_when_bolt_handshake_receives_no_bytes() -> None:
    mock_sock = MagicMock()
    mock_sock.recv.return_value = b""
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_sock)
    mock_conn.__exit__ = MagicMock(return_value=False)

    with patch("synapps.doctor.checks.memgraph_bolt.docker") as mock_docker:
        mock_docker.errors.DockerException = docker.errors.DockerException
        mock_docker.from_env.return_value.ping.return_value = None
        with patch("synapps.doctor.checks.memgraph_bolt.socket") as mock_socket:
            mock_socket.create_connection.return_value = mock_conn
            result = MemgraphBoltCheck().run()
    assert result.status == "fail"


def test_memgraph_fail_when_socket_raises_oserror() -> None:
    with patch("synapps.doctor.checks.memgraph_bolt.docker") as mock_docker:
        mock_docker.errors.DockerException = docker.errors.DockerException
        mock_docker.from_env.return_value.ping.return_value = None
        with patch("synapps.doctor.checks.memgraph_bolt.socket") as mock_socket:
            mock_socket.create_connection.side_effect = OSError("connection refused")
            result = MemgraphBoltCheck().run()
    assert result.status == "fail"


def test_memgraph_pass_when_bolt_handshake_receives_4_bytes() -> None:
    mock_sock = MagicMock()
    mock_sock.recv.return_value = b"\x00\x04\x00\x00"
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_sock)
    mock_conn.__exit__ = MagicMock(return_value=False)

    with patch("synapps.doctor.checks.memgraph_bolt.docker") as mock_docker:
        mock_docker.errors.DockerException = docker.errors.DockerException
        mock_docker.from_env.return_value.ping.return_value = None
        with patch("synapps.doctor.checks.memgraph_bolt.socket") as mock_socket:
            mock_socket.create_connection.return_value = mock_conn
            result = MemgraphBoltCheck().run()
    assert result.status == "pass"
    assert result.fix is None


def test_memgraph_warn_has_no_fix() -> None:
    mock_sock = MagicMock()
    mock_sock.recv.return_value = b"\x00\x04\x00\x00"
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_sock)
    mock_conn.__exit__ = MagicMock(return_value=False)

    with patch("synapps.doctor.checks.memgraph_bolt.docker") as mock_docker:
        mock_docker.errors.DockerException = docker.errors.DockerException
        mock_docker.from_env.return_value.ping.return_value = None
        with patch("synapps.doctor.checks.memgraph_bolt.socket") as mock_socket:
            mock_socket.create_connection.return_value = mock_conn
            result = MemgraphBoltCheck().run()
    assert result.fix is None


def test_memgraph_fail_has_fix() -> None:
    with patch("synapps.doctor.checks.memgraph_bolt.docker") as mock_docker:
        mock_docker.errors.DockerException = docker.errors.DockerException
        mock_docker.from_env.return_value.ping.return_value = None
        with patch("synapps.doctor.checks.memgraph_bolt.socket") as mock_socket:
            mock_socket.create_connection.side_effect = OSError("refused")
            result = MemgraphBoltCheck().run()
    assert result.fix is not None
    assert "docker compose" in result.fix


def test_memgraph_group_is_core() -> None:
    with patch("synapps.doctor.checks.memgraph_bolt.docker") as mock_docker:
        mock_docker.errors.DockerException = docker.errors.DockerException
        mock_docker.from_env.return_value.ping.return_value = None
        with patch("synapps.doctor.checks.memgraph_bolt.socket") as mock_socket:
            mock_socket.create_connection.side_effect = OSError("refused")
            result = MemgraphBoltCheck().run()
    assert result.group == "core"


def test_bolt_check_uses_shared_port() -> None:
    """Check connects to shared_port from global config, not hardcoded 7687."""
    with patch("synapps.doctor.checks.memgraph_bolt.load_global_config", return_value={
        "shared_port": 9999,
        "external_host": None,
        "external_port": None,
    }), patch("synapps.doctor.checks.memgraph_bolt.docker") as mock_docker, \
         patch("synapps.doctor.checks.memgraph_bolt.socket") as mock_socket:
        mock_docker.from_env.return_value.ping.return_value = True
        mock_sock = MagicMock()
        mock_sock.recv.return_value = b"\x00\x00\x04\x04"
        mock_socket.create_connection.return_value.__enter__ = MagicMock(return_value=mock_sock)
        mock_socket.create_connection.return_value.__exit__ = MagicMock(return_value=False)

        result = MemgraphBoltCheck().run()

    mock_socket.create_connection.assert_called_once_with(("localhost", 9999), timeout=2.0)
    assert result.status == "pass"


def test_bolt_check_uses_external_host() -> None:
    """When external_host is set, check connects to external host:port."""
    with patch("synapps.doctor.checks.memgraph_bolt.load_global_config", return_value={
        "shared_port": 7687,
        "external_host": "db.example.com",
        "external_port": 7688,
    }), patch("synapps.doctor.checks.memgraph_bolt.docker") as mock_docker, \
         patch("synapps.doctor.checks.memgraph_bolt.socket") as mock_socket:
        mock_docker.from_env.return_value.ping.return_value = True
        mock_sock = MagicMock()
        mock_sock.recv.return_value = b"\x00\x00\x04\x04"
        mock_socket.create_connection.return_value.__enter__ = MagicMock(return_value=mock_sock)
        mock_socket.create_connection.return_value.__exit__ = MagicMock(return_value=False)

        result = MemgraphBoltCheck().run()

    mock_socket.create_connection.assert_called_once_with(("db.example.com", 7688), timeout=2.0)
    assert result.status == "pass"
