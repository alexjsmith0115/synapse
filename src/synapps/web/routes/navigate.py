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
        limit: int = 0,
    ) -> str | list | dict:
        try:
            resolved = service._resolve(full_name)
            symbol_kind = service.get_symbol_kind(resolved)
            result = service.find_usages(full_name, exclude_test_callers, limit=limit, structured=True)
            return {"usages": serialize_result(result), "queried_kind": symbol_kind}
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
            resolved = service._resolve(full_name, preference="concrete")
            symbol_kind = service.get_symbol_kind(resolved)
            if depth is not None:
                result = service.get_call_depth(full_name, depth)
            else:
                result = service.find_callees(full_name, include_interface_dispatch, limit=limit)
            raw = serialize_result(result)
            if isinstance(raw, list):
                return {"callees": raw, "queried_kind": symbol_kind}
            # depth tree response — already a dict, add kind
            if isinstance(raw, dict):
                raw["queried_kind"] = symbol_kind
            return raw
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @r.get("/get_hierarchy")
    def get_hierarchy(full_name: str) -> dict:
        try:
            result = service.get_hierarchy(full_name)
            return serialize_result(result)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @r.get("/get_context_for")
    def get_context_for(
        full_name: str,
        scope: str | None = None,
    ) -> str | dict:
        try:
            if scope == "impact":
                result = service.analyze_change_impact(full_name, structured=True)
            else:
                result = service.get_context_for(full_name, scope=scope, max_lines=-1, structured=True)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        if result is None:
            raise HTTPException(status_code=404, detail=f"Symbol '{full_name}' not found.")
        return result

    @r.get("/expand_node")
    def expand_node(full_name: str) -> dict:
        try:
            result = service.find_neighborhood(full_name)
            return serialize_result(result)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    return r
