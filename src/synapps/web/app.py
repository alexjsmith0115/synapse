from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from synapps.service import SynappsService

log = logging.getLogger(__name__)

_PACKAGE_STATIC_DIR = Path(__file__).parent / "static"


def _resolve_static_dir(static_dir: Path | None) -> Path | None:
    """Find the SPA static directory, checking explicit override, package dir, and CWD."""
    candidates = [d for d in [static_dir, _PACKAGE_STATIC_DIR, Path.cwd() / "src" / "synapps" / "web" / "static"] if d]
    for d in candidates:
        if d.is_dir() and (d / "index.html").exists():
            return d
    return None


def create_app(service: SynappsService, *, static_dir: Path | None = None) -> FastAPI:
    app = FastAPI(title="Synapps Web UI", docs_url=None, redoc_url=None)

    # Import and register route modules — /api prefix
    from synapps.web.routes import search, navigate, analysis, query as query_routes, config
    app.include_router(search.router(service), prefix="/api")
    app.include_router(navigate.router(service), prefix="/api")
    app.include_router(analysis.router(service), prefix="/api")
    app.include_router(query_routes.router(service), prefix="/api")
    app.include_router(config.router(service), prefix="/api")

    # SPA static files — MUST be registered AFTER API routes
    # html=True enables index.html fallback for SPA client-side routing
    resolved = _resolve_static_dir(static_dir)
    if resolved:
        app.mount("/", StaticFiles(directory=resolved, html=True), name="spa")
    else:
        log.warning("Static files directory not found — SPA will not be served. Run scripts/build_spa.sh first.")

    return app
