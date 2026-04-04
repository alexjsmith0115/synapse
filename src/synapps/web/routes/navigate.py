from __future__ import annotations

from fastapi import APIRouter, HTTPException

from synapps.service import SynappsService
from synapps.web.serialization import serialize_result


def router(service: SynappsService) -> APIRouter:
    r = APIRouter(tags=["Navigate"])

    @r.get("/find_usages")
    def find_usages(
        full_name: str,
        exclude_test_callers: bool = True,
        limit: int = 20,
    ) -> str | list | dict:
        try:
            result = service.find_usages(full_name, exclude_test_callers, limit=limit)
            return serialize_result(result)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @r.get("/find_callees")
    def find_callees(
        full_name: str,
        include_interface_dispatch: bool = True,
        limit: int = 50,
        depth: int | None = None,
    ) -> list | dict:
        try:
            if depth is not None:
                result = service.get_call_depth(full_name, depth)
            else:
                result = service.find_callees(full_name, include_interface_dispatch, limit=limit)
            return serialize_result(result)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @r.get("/get_hierarchy")
    def get_hierarchy(full_name: str) -> dict:
        try:
            result = service.get_hierarchy(full_name)
            return serialize_result(result)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    return r
