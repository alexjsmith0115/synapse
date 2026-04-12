"""
E2E test fixtures for browser-level tests using pytest-playwright.

Requires a live Memgraph instance on localhost:7687.
Run with: pytest tests/e2e/ -v -m e2e
"""
from __future__ import annotations

import pathlib
import threading
import time

import pytest
import requests
import uvicorn

from synapps.graph.connection import GraphConnection
from synapps.graph.schema import ensure_schema
from synapps.service import SynappsService
from synapps.web.app import create_app

_FIXTURE_PATH = str(
    (pathlib.Path(__file__).parent.parent / "fixtures" / "SynappsTest").resolve()
)

_E2E_PORT = 7480
_E2E_HOST = "127.0.0.1"


def _delete_project(conn: GraphConnection, path: str) -> None:
    conn.execute(
        "MATCH (r:Repository {path: $path})-[:CONTAINS*]->(n) DETACH DELETE n",
        {"path": path},
    )
    conn.execute(
        "MATCH (r:Repository {path: $path}) DELETE r",
        {"path": path},
    )


@pytest.fixture(scope="session")
def service():
    conn = GraphConnection.create(database="memgraph")
    ensure_schema(conn)
    _delete_project(conn, _FIXTURE_PATH)

    svc = SynappsService(conn=conn)
    svc.index_project(_FIXTURE_PATH, "csharp")

    yield svc

    _delete_project(conn, _FIXTURE_PATH)


@pytest.fixture(scope="session")
def live_server(service: SynappsService):
    """Start uvicorn in a daemon thread; bind to loopback only (T-26-01)."""
    static_dir = pathlib.Path("src/synapps/web/static")
    app = create_app(service, static_dir=static_dir)

    config = uvicorn.Config(app, host=_E2E_HOST, port=_E2E_PORT, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    yield f"http://{_E2E_HOST}:{_E2E_PORT}"

    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="session")
def wait_for_server(live_server: str) -> str:
    """Poll /api/health until the server is ready, then return the base URL."""
    url = f"{live_server}/api/health"
    for _ in range(30):
        try:
            resp = requests.get(url, timeout=1)
            if resp.status_code == 200:
                return live_server
        except requests.RequestException:
            pass
        time.sleep(0.5)
    raise RuntimeError(f"E2E server did not become ready within 15s at {url}")


@pytest.fixture
def app_page(wait_for_server: str, page):
    """Navigate to the app and wait for the sidebar to render."""
    page.goto(wait_for_server)
    page.wait_for_selector("[data-testid='sidebar']", timeout=10000)
    return page
