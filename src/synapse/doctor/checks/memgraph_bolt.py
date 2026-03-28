from __future__ import annotations

import logging
import socket

import docker
import docker.errors

from synapse.config import load_global_config
from synapse.doctor.base import CheckResult

log = logging.getLogger(__name__)

_BOLT_MAGIC = b"\x60\x60\xb0\x17"
_BOLT_VERSIONS = (
    b"\x00\x00\x04\x04"
    b"\x00\x00\x03\x04"
    b"\x00\x00\x00\x04"
    b"\x00\x00\x00\x03"
)


class MemgraphBoltCheck:
    group = "core"

    def run(self) -> CheckResult:
        try:
            docker.from_env().ping()
        except docker.errors.DockerException:
            return CheckResult(
                name="Memgraph",
                status="warn",
                detail="Docker not available — cannot check Memgraph",
                fix=None,
                group=self.group,
            )

        config = load_global_config()
        host = config.get("external_host") or "localhost"
        port = config.get("external_port") or config["shared_port"]

        try:
            with socket.create_connection((host, port), timeout=2.0) as s:
                s.sendall(_BOLT_MAGIC + _BOLT_VERSIONS)
                resp = s.recv(4)
                if len(resp) == 4:
                    return CheckResult(
                        name="Memgraph",
                        status="pass",
                        detail=f"Memgraph Bolt reachable at {host}:{port}",
                        fix=None,
                        group=self.group,
                    )
        except OSError:
            pass

        return CheckResult(
            name="Memgraph",
            status="fail",
            detail=f"Memgraph not reachable at {host}:{port}",
            fix="Check container: docker ps | grep synapse\nStart Memgraph: docker compose up -d",
            group=self.group,
        )
