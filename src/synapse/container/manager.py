"""Connection management for Memgraph -- shared instance (default) or per-project dedicated."""
from __future__ import annotations

import json
import socket
import time
from pathlib import Path

import docker
import docker.errors

from synapse.config import is_dedicated_instance, load_global_config
from synapse.graph.connection import GraphConnection

_MEMGRAPH_IMAGE = "memgraph/memgraph"
_BOLT_CONTAINER_PORT = 7687
_CONFIG_DIR = ".synapse"
_CONFIG_FILE = "config.json"


class ConnectionManager:
    """Resolves a GraphConnection via a three-step decision tree.

    1. Project opt-out: dedicated_instance in project config -> per-project container
    2. External instance: external_host in global config -> direct connection
    3. Shared instance (default): auto-provisioned synapse-shared container
    """

    def __init__(self, project_path: str, docker_client=None) -> None:
        self._project_path = Path(project_path).resolve()
        self._dedicated = is_dedicated_instance(str(self._project_path))
        self._global_config = load_global_config()
        self._docker_client_override = docker_client
        self._docker: docker.DockerClient | None = None

    def _get_docker(self) -> docker.DockerClient:
        """Lazy Docker client init -- skipped entirely for external mode."""
        if self._docker is None:
            try:
                self._docker = self._docker_client_override or docker.from_env()
            except docker.errors.DockerException as exc:
                raise RuntimeError(
                    "Docker daemon not running. Start Docker Desktop and retry."
                ) from exc
        return self._docker

    # --- Public API ---

    def get_connection(self) -> GraphConnection:
        """Resolve and return a GraphConnection based on config."""
        if self._dedicated:
            return self._get_dedicated_connection()
        if self._global_config.get("external_host"):
            return self._get_external_connection()
        return self._get_shared_connection()

    def stop(self) -> None:
        """Stop the container. No-op for shared mode."""
        if not self._dedicated:
            return
        config = self._load_project_config()
        if config is None:
            return
        try:
            container = self._get_docker().containers.get(config["container_name"])
            container.stop()
        except docker.errors.NotFound:
            pass

    def remove(self) -> None:
        """Remove container and config. For shared mode, only removes project config."""
        if self._dedicated:
            config = self._load_project_config()
            if config is None:
                return
            try:
                container = self._get_docker().containers.get(config["container_name"])
                container.remove(force=True)
            except docker.errors.NotFound:
                pass
        config_path = self._config_path()
        if config_path.exists():
            config_path.unlink()

    # --- Shared instance ---

    def _get_shared_connection(self) -> GraphConnection:
        name = self._global_config["shared_container_name"]
        port = self._global_config["shared_port"]
        self._ensure_container(name, port)
        self._wait_for_bolt(port)
        return GraphConnection.create(port=port)

    # --- Dedicated instance ---

    def _get_dedicated_connection(self) -> GraphConnection:
        config = self._load_or_create_project_config()
        self._ensure_container(config["container_name"], config["port"])
        self._wait_for_bolt(config["port"])
        return GraphConnection.create(port=config["port"])

    # --- External instance ---

    def _get_external_connection(self) -> GraphConnection:
        host = self._global_config["external_host"]
        port = self._global_config["external_port"]
        return GraphConnection.create(host=host, port=port)

    # --- Container lifecycle ---

    def _ensure_container(self, name: str, port: int) -> None:
        try:
            container = self._get_docker().containers.get(name)
            if container.status == "running":
                return
            container.start()
        except docker.errors.NotFound:
            try:
                self._get_docker().containers.run(
                    _MEMGRAPH_IMAGE,
                    name=name,
                    ports={f"{_BOLT_CONTAINER_PORT}/tcp": port},
                    detach=True,
                )
            except docker.errors.APIError:
                # Race condition: another process created the container first
                container = self._get_docker().containers.get(name)
                if container.status != "running":
                    container.start()

    @staticmethod
    def _wait_for_bolt(port: int, timeout: float = 30.0) -> None:
        _BOLT_MAGIC = b"\x60\x60\xb0\x17"
        _BOLT_VERSIONS = (
            b"\x00\x00\x04\x04"
            b"\x00\x00\x03\x04"
            b"\x00\x00\x00\x04"
            b"\x00\x00\x00\x03"
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

    # --- Project config (dedicated mode only) ---

    def _config_path(self) -> Path:
        return self._project_path / _CONFIG_DIR / _CONFIG_FILE

    def _load_project_config(self) -> dict | None:
        p = self._config_path()
        if p.exists():
            return json.loads(p.read_text())
        return None

    def _save_project_config(self, config: dict) -> None:
        p = self._config_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(config, indent=2))

    @staticmethod
    def _find_free_port() -> int:
        with socket.socket() as s:
            s.bind(("", 0))
            return s.getsockname()[1]

    def _load_or_create_project_config(self) -> dict:
        config = self._load_project_config()
        if config is not None and "container_name" in config:
            return config
        port = self._find_free_port()
        config = config or {}
        config.update({
            "container_name": f"synapse-{self._project_path.name}",
            "port": port,
            "last_indexed": None,
        })
        self._save_project_config(config)
        return config
