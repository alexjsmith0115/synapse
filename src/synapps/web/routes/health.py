from __future__ import annotations

from fastapi import APIRouter

from synapps.service import SynappsService


def router(service: SynappsService) -> APIRouter:
    r = APIRouter(tags=["Health"])

    @r.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    return r
