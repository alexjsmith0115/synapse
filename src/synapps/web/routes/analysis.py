from __future__ import annotations

from fastapi import APIRouter

from synapps.service import SynappsService


def router(service: SynappsService) -> APIRouter:
    api_router = APIRouter()
    return api_router
