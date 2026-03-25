"""Per-project Docker container management for Memgraph isolation."""
from __future__ import annotations

import json
import socket
import time
from pathlib import Path

import docker
import docker.errors

from synapse.graph.connection import GraphConnection

_MEMGRAPH_IMAGE = "memgraph/memgraph"
_BOLT_CONTAINER_PORT = 7687
_CONFIG_DIR = ".synapse"
_CONFIG_FILE = "config.json"


class ContainerManager:
    """Manages a per-project Memgraph Docker container and its configuration.

    Each project gets a deterministic container name derived from its absolute
    path, with a dynamically allocated host port persisted in .synapse/config.json.
    """

    def __init__(self, project_path: str, docker_client=None) -> None:
        self._project_path = Path(project_path).resolve()
        try:
            self._docker = docker_client or docker.from_env()
        except docker.errors.DockerException as exc:
            raise RuntimeError(
                "Docker daemon not running. Start Docker Desktop and retry."
            ) from exc

    def _container_name(self) -> str:
        return f"synapse-{self._project_path.name}"

    def _config_path(self) -> Path:
        return self._project_path / _CONFIG_DIR / _CONFIG_FILE

    def _load_config(self) -> dict | None:
        p = self._config_path()
        if p.exists():
            return json.loads(p.read_text())
        return None

    def _save_config(self, config: dict) -> None:
        p = self._config_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(config, indent=2))

    @staticmethod
    def _find_free_port() -> int:
        with socket.socket() as s:
            s.bind(("", 0))
            return s.getsockname()[1]

    def _load_or_create_config(self) -> dict:
        config = self._load_config()
        if config is not None:
            return config
        config = {
            "container_name": self._container_name(),
            "port": self._find_free_port(),
            "last_indexed": None,
        }
        self._save_config(config)
        return config

    def _ensure_container(self, config: dict) -> None:
        name = config["container_name"]
        port = config["port"]
        try:
            container = self._docker.containers.get(name)
            if container.status == "running":
                return
            container.start()
        except docker.errors.NotFound:
            self._docker.containers.run(
                _MEMGRAPH_IMAGE,
                name=name,
                ports={f"{_BOLT_CONTAINER_PORT}/tcp": port},
                detach=True,
            )

    @staticmethod
    def _wait_for_bolt(port: int, timeout: float = 30.0) -> None:
        # Bolt v1 handshake preamble: magic + 4 version proposals
        _BOLT_MAGIC = b"\x60\x60\xb0\x17"
        _BOLT_VERSIONS = (
            b"\x00\x00\x04\x04"  # Bolt 4.4
            b"\x00\x00\x03\x04"  # Bolt 4.3
            b"\x00\x00\x00\x04"  # Bolt 4.0
            b"\x00\x00\x00\x03"  # Bolt 3.0
        )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("localhost", port), timeout=2.0) as s:
                    s.sendall(_BOLT_MAGIC + _BOLT_VERSIONS)
                    resp = s.recv(4)
                    if len(resp) == 4:
                        return
            except OSError:
                pass
            time.sleep(0.3)
        raise TimeoutError(
            f"Memgraph on port {port} did not become ready within {timeout}s"
        )

    def get_connection(self) -> GraphConnection:
        """Ensure container is running and return a GraphConnection to its Bolt port."""
        config = self._load_or_create_config()
        self._ensure_container(config)
        self._wait_for_bolt(config["port"])
        return GraphConnection.create(port=config["port"])

    def stop(self) -> None:
        """Stop this project's container (does not remove it)."""
        config = self._load_config()
        if config is None:
            return
        try:
            container = self._docker.containers.get(config["container_name"])
            container.stop()
        except docker.errors.NotFound:
            pass

    def remove(self) -> None:
        """Stop and remove this project's container and delete config."""
        config = self._load_config()
        if config is None:
            return
        try:
            container = self._docker.containers.get(config["container_name"])
            container.remove(force=True)
        except docker.errors.NotFound:
            pass
        config_path = self._config_path()
        if config_path.exists():
            config_path.unlink()
