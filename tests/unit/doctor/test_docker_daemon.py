from __future__ import annotations

from unittest.mock import MagicMock, patch

import docker.errors
import pytest

from synapps.doctor.checks.docker_daemon import DockerDaemonCheck


def test_docker_daemon_pass_when_ping_succeeds() -> None:
    with patch("synapps.doctor.checks.docker_daemon.docker") as mock_docker:
        mock_docker.from_env.return_value.ping.return_value = None
        result = DockerDaemonCheck().run()
    assert result.status == "pass"
    assert result.fix is None


def test_docker_daemon_fail_when_ping_raises() -> None:
    with patch("synapps.doctor.checks.docker_daemon.docker") as mock_docker:
        mock_docker.errors.DockerException = docker.errors.DockerException
        mock_docker.from_env.return_value.ping.side_effect = docker.errors.DockerException("daemon not running")
        result = DockerDaemonCheck().run()
    assert result.status == "fail"


def test_docker_daemon_fail_contains_exception_message() -> None:
    with patch("synapps.doctor.checks.docker_daemon.docker") as mock_docker:
        mock_docker.errors.DockerException = docker.errors.DockerException
        mock_docker.from_env.return_value.ping.side_effect = docker.errors.DockerException("daemon not running")
        result = DockerDaemonCheck().run()
    assert "daemon not running" in result.detail


def test_docker_daemon_fix_on_macos() -> None:
    with patch("synapps.doctor.checks.docker_daemon.docker") as mock_docker:
        mock_docker.errors.DockerException = docker.errors.DockerException
        mock_docker.from_env.return_value.ping.side_effect = docker.errors.DockerException("no daemon")
        with patch("synapps.doctor.checks.docker_daemon.platform") as mock_platform:
            mock_platform.system.return_value = "Darwin"
            result = DockerDaemonCheck().run()
    assert result.fix is not None
    assert "mac-install" in result.fix or "docker.com" in result.fix


def test_docker_daemon_fix_on_linux() -> None:
    with patch("synapps.doctor.checks.docker_daemon.docker") as mock_docker:
        mock_docker.errors.DockerException = docker.errors.DockerException
        mock_docker.from_env.return_value.ping.side_effect = docker.errors.DockerException("no daemon")
        with patch("synapps.doctor.checks.docker_daemon.platform") as mock_platform:
            mock_platform.system.return_value = "Linux"
            result = DockerDaemonCheck().run()
    assert result.fix is not None
    assert "apt-get" in result.fix or "docker.io" in result.fix


def test_docker_daemon_group_is_core() -> None:
    with patch("synapps.doctor.checks.docker_daemon.docker") as mock_docker:
        mock_docker.from_env.return_value.ping.return_value = None
        result = DockerDaemonCheck().run()
    assert result.group == "core"
