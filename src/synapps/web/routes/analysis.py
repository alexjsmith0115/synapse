from __future__ import annotations

from fastapi import APIRouter, HTTPException

from synapps.service import SynappsService
from synapps.web.serialization import serialize_result


def router(service: SynappsService) -> APIRouter:
    r = APIRouter(tags=["Analysis"])

    @r.get("/get_architecture")
    def get_architecture(path: str, limit: int = 10) -> dict:
        try:
            result = service.get_architecture_overview(limit=limit)
            return serialize_result(result)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @r.get("/find_dead_code")
    def find_dead_code(
        path: str,
        exclude_pattern: str = "",
        limit: int = 15,
        offset: int = 0,
    ) -> dict:
        try:
            result = service.find_dead_code(exclude_pattern=exclude_pattern, limit=limit, offset=offset)
            return serialize_result(result)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @r.get("/find_untested")
    def find_untested(
        path: str,
        exclude_pattern: str = "",
        limit: int = 15,
        offset: int = 0,
    ) -> dict:
        try:
            result = service.find_untested(exclude_pattern=exclude_pattern, limit=limit, offset=offset)
            return serialize_result(result)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    return r
