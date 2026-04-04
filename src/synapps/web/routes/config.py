from __future__ import annotations

from fastapi import APIRouter

from synapps.service import SynappsService


def router(service: SynappsService) -> APIRouter:
    r = APIRouter(tags=["Config"])

    @r.get("/config")
    def get_config() -> dict:
        roots = service._get_project_roots()
        return {"project_root": roots[0] if roots else ""}

    return r
