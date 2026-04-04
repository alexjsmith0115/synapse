from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from synapps.service import SynappsService

log = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent / "static"


def create_app(service: SynappsService) -> FastAPI:
    app = FastAPI(title="Synapps Web UI", docs_url=None, redoc_url=None)

    # Import and register route modules — /api prefix
    from synapps.web.routes import search, navigate, analysis, query as query_routes
    app.include_router(search.router(service), prefix="/api")
    app.include_router(navigate.router(service), prefix="/api")
    app.include_router(analysis.router(service), prefix="/api")
    app.include_router(query_routes.router(service), prefix="/api")

    # SPA static files — MUST be registered AFTER API routes
    # html=True enables index.html fallback for SPA client-side routing
    if _STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="spa")
    else:
        log.warning("Static files directory not found: %s — SPA will not be served", _STATIC_DIR)

    return app
