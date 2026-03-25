"""Unit tests for ConnectionManager with mocked Docker client."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


_MODULE = "synapse.container.manager"


def _make_manager(tmp_path, mock_docker=None, dedicated=False, global_config=None):
    """Helper to create a ConnectionManager with controlled config."""
    from synapse.container.manager import ConnectionManager

    gc = global_config or {
        "shared_container_name": "synapse-shared",
        "shared_port": 7687,
        "external_host": None,
        "external_port": None,
    }
    with patch(f"{_MODULE}.is_dedicated_instance", return_value=dedicated), \
         patch(f"{_MODULE}.load_global_config", return_value=gc):
        return ConnectionManager(str(tmp_path), docker_client=mock_docker)


# --- Shared mode ---


def test_shared_mode_creates_shared_container(tmp_path):
    """No config -> creates synapse-shared container."""
    import docker.errors

    mock_docker = MagicMock()
    mock_docker.containers.get.side_effect = docker.errors.NotFound("nope")
    mgr = _make_manager(tmp_path, mock_docker=mock_docker)

    with patch(f"{_MODULE}.GraphConnection") as mock_gc, \
         patch.object(mgr, "_wait_for_bolt"):
        mock_gc.create.return_value = MagicMock()
        mgr.get_connection()

    mock_docker.containers.run.assert_called_once()
    call_kwargs = mock_docker.containers.run.call_args
    assert call_kwargs[1]["name"] == "synapse-shared"
    assert call_kwargs[1]["ports"] == {"7687/tcp": 7687}


def test_shared_mode_reuses_running_container(tmp_path):
    """Shared container running -> reuse, no start/run."""
    mock_docker = MagicMock()
    mock_container = MagicMock()
    mock_container.status = "running"
    mock_docker.containers.get.return_value = mock_container
    mgr = _make_manager(tmp_path, mock_docker=mock_docker)

    with patch(f"{_MODULE}.GraphConnection") as mock_gc, \
         patch.object(mgr, "_wait_for_bolt"):
        mock_gc.create.return_value = MagicMock()
        mgr.get_connection()

    mock_docker.containers.run.assert_not_called()
    mock_container.start.assert_not_called()


def test_shared_mode_custom_port(tmp_path):
    """Global config custom port -> uses it."""
    mock_docker = MagicMock()
    mock_container = MagicMock()
    mock_container.status = "running"
    mock_docker.containers.get.return_value = mock_container

    gc = {
        "shared_container_name": "synapse-shared",
        "shared_port": 9999,
        "external_host": None,
        "external_port": None,
    }
    mgr = _make_manager(tmp_path, mock_docker=mock_docker, global_config=gc)

    with patch(f"{_MODULE}.GraphConnection") as mock_gc, \
         patch.object(mgr, "_wait_for_bolt"):
        mock_gc.create.return_value = MagicMock()
        mgr.get_connection()

    mock_gc.create.assert_called_once_with(port=9999)


# --- Dedicated mode ---


def test_dedicated_mode_creates_project_container(tmp_path):
    """dedicated_instance:true -> per-project container named synapse-{dirname}."""
    import docker.errors

    mock_docker = MagicMock()
    mock_docker.containers.get.side_effect = docker.errors.NotFound("nope")
    mgr = _make_manager(tmp_path, mock_docker=mock_docker, dedicated=True)

    with patch(f"{_MODULE}.GraphConnection") as mock_gc, \
         patch.object(mgr, "_wait_for_bolt"):
        mock_gc.create.return_value = MagicMock()
        mgr.get_connection()

    mock_docker.containers.run.assert_called_once()
    call_kwargs = mock_docker.containers.run.call_args
    assert call_kwargs[1]["name"] == f"synapse-{tmp_path.name}"


def test_dedicated_mode_persists_config(tmp_path):
    """Dedicated mode writes container_name/port to project config."""
    import docker.errors

    mock_docker = MagicMock()
    mock_docker.containers.get.side_effect = docker.errors.NotFound("nope")
    mgr = _make_manager(tmp_path, mock_docker=mock_docker, dedicated=True)

    with patch(f"{_MODULE}.GraphConnection") as mock_gc, \
         patch.object(mgr, "_wait_for_bolt"):
        mock_gc.create.return_value = MagicMock()
        mgr.get_connection()

    config_path = tmp_path / ".synapse" / "config.json"
    assert config_path.exists()
    config = json.loads(config_path.read_text())
    assert config["container_name"] == f"synapse-{tmp_path.name}"
    assert "port" in config
    assert isinstance(config["port"], int)


# --- External mode ---


def test_external_mode_connects_directly(tmp_path):
    """external_host set -> GraphConnection.create(host=..., port=...), no Docker."""
    gc = {
        "shared_container_name": "synapse-shared",
        "shared_port": 7687,
        "external_host": "db.example.com",
        "external_port": 7688,
    }
    mgr = _make_manager(tmp_path, mock_docker=None, global_config=gc)

    with patch(f"{_MODULE}.GraphConnection") as mock_gc:
        mock_gc.create.return_value = MagicMock()
        conn = mgr.get_connection()

    mock_gc.create.assert_called_once_with(host="db.example.com", port=7688)


def test_dedicated_overrides_external(tmp_path):
    """dedicated_instance takes priority over external_host."""
    import docker.errors

    mock_docker = MagicMock()
    mock_docker.containers.get.side_effect = docker.errors.NotFound("nope")

    gc = {
        "shared_container_name": "synapse-shared",
        "shared_port": 7687,
        "external_host": "db.example.com",
        "external_port": 7688,
    }
    mgr = _make_manager(tmp_path, mock_docker=mock_docker, dedicated=True, global_config=gc)

    with patch(f"{_MODULE}.GraphConnection") as mock_gc, \
         patch.object(mgr, "_wait_for_bolt"):
        mock_gc.create.return_value = MagicMock()
        mgr.get_connection()

    # Should have used Docker (dedicated), not the external host
    mock_docker.containers.run.assert_called_once()
    call_kwargs = mock_docker.containers.run.call_args
    assert call_kwargs[1]["name"] == f"synapse-{tmp_path.name}"


# --- Race condition ---


def test_shared_mode_handles_name_conflict(tmp_path):
    """Docker run conflict -> retry get -> succeeds."""
    import docker.errors

    mock_docker = MagicMock()
    mock_container = MagicMock()
    mock_container.status = "running"

    # First get -> NotFound, run -> APIError (race), second get -> found
    mock_docker.containers.get.side_effect = [
        docker.errors.NotFound("nope"),
        mock_container,
    ]
    mock_docker.containers.run.side_effect = docker.errors.APIError("conflict")

    mgr = _make_manager(tmp_path, mock_docker=mock_docker)

    with patch(f"{_MODULE}.GraphConnection") as mock_gc, \
         patch.object(mgr, "_wait_for_bolt"):
        mock_gc.create.return_value = MagicMock()
        mgr.get_connection()

    mock_docker.containers.run.assert_called_once()


# --- stop / remove ---


def test_stop_noop_for_shared_mode(tmp_path):
    """stop() shared -> zero Docker interaction."""
    mock_docker = MagicMock()
    mgr = _make_manager(tmp_path, mock_docker=mock_docker)
    mgr.stop()
    mock_docker.containers.get.assert_not_called()


def test_stop_stops_dedicated_container(tmp_path):
    """stop() dedicated -> container.stop()."""
    mock_docker = MagicMock()
    mock_container = MagicMock()
    mock_docker.containers.get.return_value = mock_container

    # Create project config so stop() can find the container name
    config_dir = tmp_path / ".synapse"
    config_dir.mkdir()
    config = {"container_name": "synapse-test", "port": 55555, "last_indexed": None}
    (config_dir / "config.json").write_text(json.dumps(config))

    mgr = _make_manager(tmp_path, mock_docker=mock_docker, dedicated=True)
    mgr.stop()
    mock_container.stop.assert_called_once()


def test_remove_dedicated_removes_container_and_config(tmp_path):
    """remove() dedicated -> container.remove(force=True) + config deleted."""
    mock_docker = MagicMock()
    mock_container = MagicMock()
    mock_docker.containers.get.return_value = mock_container

    config_dir = tmp_path / ".synapse"
    config_dir.mkdir()
    config_path = config_dir / "config.json"
    config = {"container_name": "synapse-test", "port": 55555, "last_indexed": None}
    config_path.write_text(json.dumps(config))

    mgr = _make_manager(tmp_path, mock_docker=mock_docker, dedicated=True)
    mgr.remove()

    mock_container.remove.assert_called_once_with(force=True)
    assert not config_path.exists()


def test_remove_shared_only_deletes_config(tmp_path):
    """remove() shared -> config deleted, no Docker."""
    mock_docker = MagicMock()

    config_dir = tmp_path / ".synapse"
    config_dir.mkdir()
    config_path = config_dir / "config.json"
    config_path.write_text(json.dumps({"some": "config"}))

    mgr = _make_manager(tmp_path, mock_docker=mock_docker)
    mgr.remove()

    mock_docker.containers.get.assert_not_called()
    assert not config_path.exists()


# --- Docker daemon error ---


def test_docker_not_running_raises_on_get_connection(tmp_path):
    """Docker error raised lazily on get_connection(), not __init__."""
    import docker.errors

    from synapse.container.manager import ConnectionManager

    with patch(f"{_MODULE}.is_dedicated_instance", return_value=False), \
         patch(f"{_MODULE}.load_global_config", return_value={
             "shared_container_name": "synapse-shared",
             "shared_port": 7687,
             "external_host": None,
             "external_port": None,
         }), \
         patch(f"{_MODULE}.docker.from_env", side_effect=docker.errors.DockerException("nope")):
        # __init__ should NOT raise
        mgr = ConnectionManager(str(tmp_path))
        # get_connection() SHOULD raise
        with pytest.raises(RuntimeError, match="Docker"):
            mgr.get_connection()


def test_external_mode_no_docker_needed(tmp_path):
    """External mode works even when docker.from_env raises."""
    import docker.errors

    gc = {
        "shared_container_name": "synapse-shared",
        "shared_port": 7687,
        "external_host": "db.example.com",
        "external_port": 7688,
    }

    from synapse.container.manager import ConnectionManager

    with patch(f"{_MODULE}.is_dedicated_instance", return_value=False), \
         patch(f"{_MODULE}.load_global_config", return_value=gc), \
         patch(f"{_MODULE}.docker.from_env", side_effect=docker.errors.DockerException("nope")), \
         patch(f"{_MODULE}.GraphConnection") as mock_gc:
        mock_gc.create.return_value = MagicMock()
        mgr = ConnectionManager(str(tmp_path))
        conn = mgr.get_connection()

    mock_gc.create.assert_called_once_with(host="db.example.com", port=7688)


# --- Bolt readiness ---


def test_wait_for_bolt_success():
    """Bolt readiness check succeeds on valid 4-byte response."""
    from synapse.container.manager import ConnectionManager

    mock_sock = MagicMock()
    mock_sock.recv.return_value = b"\x00\x00\x04\x04"
    with patch(f"{_MODULE}.socket.create_connection") as mock_conn:
        mock_conn.return_value.__enter__ = MagicMock(return_value=mock_sock)
        mock_conn.return_value.__exit__ = MagicMock(return_value=False)
        ConnectionManager._wait_for_bolt(12345, timeout=5.0)
    mock_conn.assert_called()
    mock_sock.sendall.assert_called_once()


def test_wait_for_bolt_timeout():
    """Bolt readiness check times out on persistent connection failures."""
    from synapse.container.manager import ConnectionManager

    with patch(f"{_MODULE}.socket.create_connection", side_effect=OSError("refused")):
        with pytest.raises(TimeoutError):
            ConnectionManager._wait_for_bolt(12345, timeout=0.5)
