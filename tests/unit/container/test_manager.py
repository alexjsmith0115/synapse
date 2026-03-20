"""Unit tests for ContainerManager with mocked Docker client."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


@pytest.fixture()
def mock_docker():
    """Return a MagicMock Docker client."""
    return MagicMock()


@pytest.fixture()
def manager(tmp_path, mock_docker):
    """Return a ContainerManager with a mocked Docker client."""
    from synapse.container.manager import ContainerManager
    return ContainerManager(str(tmp_path), docker_client=mock_docker)


# --- Container naming ---

def test_container_name_uses_directory_name(tmp_path, mock_docker):
    from synapse.container.manager import ContainerManager
    m = ContainerManager(str(tmp_path), docker_client=mock_docker)
    expected = f"synapse-{tmp_path.name}"
    assert m._container_name() == expected


def test_container_name_different_paths(mock_docker, tmp_path):
    from synapse.container.manager import ContainerManager
    p1 = tmp_path / "project_a"
    p2 = tmp_path / "project_b"
    p1.mkdir()
    p2.mkdir()
    m1 = ContainerManager(str(p1), docker_client=mock_docker)
    m2 = ContainerManager(str(p2), docker_client=mock_docker)
    assert m1._container_name() == "synapse-project_a"
    assert m2._container_name() == "synapse-project_b"
    assert m1._container_name() != m2._container_name()


# --- Container lifecycle ---

def test_creates_container(manager, mock_docker, tmp_path):
    import docker.errors
    mock_docker.containers.get.side_effect = docker.errors.NotFound("nope")

    with patch("synapse.container.manager.GraphConnection") as mock_gc, \
         patch.object(manager, "_wait_for_bolt"):
        mock_gc.create.return_value = MagicMock()
        manager.get_connection()

    mock_docker.containers.run.assert_called_once()
    call_kwargs = mock_docker.containers.run.call_args
    assert call_kwargs[0][0] == "memgraph/memgraph"  # image
    assert call_kwargs[1]["detach"] is True
    assert "name" in call_kwargs[1]
    assert "ports" in call_kwargs[1]


def test_reuses_running_container(manager, mock_docker, tmp_path):
    mock_container = MagicMock()
    mock_container.status = "running"
    mock_docker.containers.get.return_value = mock_container

    with patch("synapse.container.manager.GraphConnection") as mock_gc, \
         patch.object(manager, "_wait_for_bolt"):
        mock_gc.create.return_value = MagicMock()
        manager.get_connection()

    mock_docker.containers.run.assert_not_called()
    mock_container.start.assert_not_called()


def test_restarts_exited_container(manager, mock_docker, tmp_path):
    mock_container = MagicMock()
    mock_container.status = "exited"
    mock_docker.containers.get.return_value = mock_container

    with patch("synapse.container.manager.GraphConnection") as mock_gc, \
         patch.object(manager, "_wait_for_bolt"):
        mock_gc.create.return_value = MagicMock()
        manager.get_connection()

    mock_container.start.assert_called_once()
    mock_docker.containers.run.assert_not_called()


# --- Config persistence ---

def test_config_created_on_first_use(manager, mock_docker, tmp_path):
    import docker.errors
    mock_docker.containers.get.side_effect = docker.errors.NotFound("nope")

    with patch("synapse.container.manager.GraphConnection") as mock_gc, \
         patch.object(manager, "_wait_for_bolt"):
        mock_gc.create.return_value = MagicMock()
        manager.get_connection()

    config_path = tmp_path / ".synapse" / "config.json"
    assert config_path.exists()
    config = json.loads(config_path.read_text())
    assert "project_path" in config
    assert "container_name" in config
    assert "port" in config
    assert "last_indexed" in config
    assert config["last_indexed"] is None


def test_config_reused(manager, mock_docker, tmp_path):
    # Pre-create config with specific port
    config_dir = tmp_path / ".synapse"
    config_dir.mkdir()
    config = {
        "project_path": str(tmp_path),
        "container_name": "synapse-test",
        "port": 55555,
        "last_indexed": None,
    }
    (config_dir / "config.json").write_text(json.dumps(config))

    mock_container = MagicMock()
    mock_container.status = "running"
    mock_docker.containers.get.return_value = mock_container

    with patch("synapse.container.manager.GraphConnection") as mock_gc, \
         patch.object(manager, "_wait_for_bolt"), \
         patch("synapse.container.manager.ContainerManager._find_free_port", return_value=99999) as mock_port:
        mock_gc.create.return_value = MagicMock()
        manager.get_connection()
        mock_port.assert_not_called()

    # Verify the container was fetched with the config's container_name
    mock_docker.containers.get.assert_called_with("synapse-test")


# --- Readiness polling ---

def test_wait_for_bolt_success(manager):
    mock_sock = MagicMock()
    mock_sock.recv.return_value = b"\x00\x00\x04\x04"  # 4-byte Bolt version response
    with patch("synapse.container.manager.socket.create_connection") as mock_conn:
        mock_conn.return_value.__enter__ = MagicMock(return_value=mock_sock)
        mock_conn.return_value.__exit__ = MagicMock(return_value=False)
        manager._wait_for_bolt(12345, timeout=5.0)
    mock_conn.assert_called()
    mock_sock.sendall.assert_called_once()


def test_wait_for_bolt_timeout(manager):
    with patch("synapse.container.manager.socket.create_connection", side_effect=OSError("refused")):
        with pytest.raises(TimeoutError):
            manager._wait_for_bolt(12345, timeout=0.5)


# --- Docker daemon error ---

def test_docker_not_running_raises(tmp_path):
    import docker.errors
    with patch("synapse.container.manager.docker.from_env", side_effect=docker.errors.DockerException("nope")):
        from synapse.container.manager import ContainerManager
        with pytest.raises(RuntimeError, match="Docker"):
            ContainerManager(str(tmp_path))


# --- get_connection return type ---

def test_get_connection_returns_graph_connection(manager, mock_docker, tmp_path):
    mock_container = MagicMock()
    mock_container.status = "running"
    mock_docker.containers.get.return_value = mock_container

    with patch("synapse.container.manager.GraphConnection") as mock_gc, \
         patch.object(manager, "_wait_for_bolt"):
        sentinel = MagicMock()
        mock_gc.create.return_value = sentinel
        result = manager.get_connection()

    assert result is sentinel


# --- stop / remove ---

def test_stop_stops_container(manager, mock_docker, tmp_path):
    # Create config so stop() can find the container name
    config_dir = tmp_path / ".synapse"
    config_dir.mkdir()
    config = {
        "project_path": str(tmp_path),
        "container_name": "synapse-test",
        "port": 55555,
        "last_indexed": None,
    }
    (config_dir / "config.json").write_text(json.dumps(config))

    mock_container = MagicMock()
    mock_docker.containers.get.return_value = mock_container
    manager.stop()
    mock_container.stop.assert_called_once()


def test_stop_ignores_not_found(manager, mock_docker, tmp_path):
    import docker.errors
    config_dir = tmp_path / ".synapse"
    config_dir.mkdir()
    config = {
        "project_path": str(tmp_path),
        "container_name": "synapse-test",
        "port": 55555,
        "last_indexed": None,
    }
    (config_dir / "config.json").write_text(json.dumps(config))

    mock_docker.containers.get.side_effect = docker.errors.NotFound("gone")
    # Should not raise
    manager.stop()


def test_remove_removes_container(manager, mock_docker, tmp_path):
    config_dir = tmp_path / ".synapse"
    config_dir.mkdir()
    config = {
        "project_path": str(tmp_path),
        "container_name": "synapse-test",
        "port": 55555,
        "last_indexed": None,
    }
    config_path = config_dir / "config.json"
    config_path.write_text(json.dumps(config))

    mock_container = MagicMock()
    mock_docker.containers.get.return_value = mock_container
    manager.remove()

    mock_container.remove.assert_called_once_with(force=True)
    assert not config_path.exists()
