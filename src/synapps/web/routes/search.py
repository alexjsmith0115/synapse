from __future__ import annotations

from fastapi import APIRouter, HTTPException

from synapps.service import SynappsService
from synapps.web.serialization import serialize_result


def router(service: SynappsService) -> APIRouter:
    r = APIRouter(tags=["Search"])

    @r.get("/search_symbols")
    def search_symbols(
        query: str,
        kind: str | None = None,
        namespace: str | None = None,
        file_path: str | None = None,
        language: str | None = None,
        limit: int = 50,
    ) -> list | dict:
        try:
            result = service.search_symbols(query, kind, namespace, file_path, language, limit=limit)
            return serialize_result(result)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    return r
