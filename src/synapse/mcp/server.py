from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP

from synapse.graph.connection import GraphConnection
from synapse.graph.schema import ensure_schema
from synapse.mcp.tools import register_tools
from synapse.service import SynapseService

log = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    conn = GraphConnection.create()
    ensure_schema(conn)
    service = SynapseService(conn)

    mcp = FastMCP("synapse")
    register_tools(mcp, service)
    mcp.run()
