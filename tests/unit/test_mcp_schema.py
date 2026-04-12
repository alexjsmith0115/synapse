from __future__ import annotations

import asyncio
import re

from mcp.server.fastmcp import FastMCP
from unittest.mock import create_autospec

from synapps.service import SynappsService
from synapps.mcp.tools import register_tools

_FORBIDDEN_PARAM_NAMES: frozenset[str] = frozenset(
    {
        "symbol",
        "symbol_name",
        "symbolName",
        "filepath",
        "file",
        "line_number",
        "lineNumber",
        "max",
        "count",
        "size",
    }
)


def _make_mcp() -> FastMCP:
    mcp = FastMCP("test")
    register_tools(mcp, create_autospec(SynappsService))
    return mcp


def test_all_tools_have_descriptions() -> None:
    tools = asyncio.run(_make_mcp().list_tools())
    violations = [t.name for t in tools if not (t.description and t.description.strip())]
    assert not violations, f"Tools missing descriptions: {violations}"


def test_all_tools_have_valid_input_schemas() -> None:
    tools = asyncio.run(_make_mcp().list_tools())
    violations = [
        t.name
        for t in tools
        if t.inputSchema is None or t.inputSchema.get("type") != "object"
    ]
    assert not violations, f"Tools with invalid inputSchema: {violations}"


def test_expected_tool_count() -> None:
    tools = asyncio.run(_make_mcp().list_tools())
    assert len(tools) == 21, f"Expected 21 tools, got {len(tools)}: {[t.name for t in tools]}"


def test_no_forbidden_param_names() -> None:
    tools = asyncio.run(_make_mcp().list_tools())
    violations = [
        f"{t.name}.{param}"
        for t in tools
        for param in t.inputSchema.get("properties", {})
        if param in _FORBIDDEN_PARAM_NAMES
    ]
    assert not violations, f"Tools using forbidden parameter names: {violations}"


def test_all_tools_use_snake_case_params() -> None:
    tools = asyncio.run(_make_mcp().list_tools())
    violations = [
        f"{t.name}.{param}"
        for t in tools
        for param in t.inputSchema.get("properties", {})
        if not re.fullmatch(r"[a-z][a-z0-9_]*", param)
    ]
    assert not violations, f"Tools with non-snake_case parameter names: {violations}"
