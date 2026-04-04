from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from synapps.service import SynappsService
from synapps.web.serialization import serialize_result


class CypherRequest(BaseModel):
    cypher: str


def router(service: SynappsService) -> APIRouter:
    r = APIRouter(tags=["Query"])

    @r.post("/execute_query")
    def execute_query(body: CypherRequest) -> list:
        try:
            result = service.execute_query(body.cypher)
            return serialize_result(result)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @r.get("/find_http_endpoints")
    def find_http_endpoints(
        route: str | None = None,
        http_method: str | None = None,
        language: str | None = None,
        limit: int = 50,
    ) -> list | dict:
        try:
            result = service.find_http_endpoints(route, http_method, language, limit=limit)
            return serialize_result(result)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    return r
