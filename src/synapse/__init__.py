from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__: str = version("synapse-mcp")
except PackageNotFoundError:
    __version__ = "dev"
