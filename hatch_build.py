"""Custom Hatch build hook to conditionally include SPA static files.

The SPA build output (index.html, assets/, etc.) lives under
src/synapps/web/static/ but is gitignored.  On a fresh CI checkout the
files don't exist, so a static force-include in pyproject.toml would
break editable installs.  This hook adds the force-include entries only
when the files are actually present on disk (i.e. a real wheel build
after the SPA has been compiled).
"""

from __future__ import annotations

import os
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

_STATIC_DIR = Path("src/synapps/web/static")

# Files/dirs to force-include when present (source -> wheel destination)
_SPA_ASSETS: dict[str, str] = {
    "src/synapps/web/static/index.html": "synapps/web/static/index.html",
    "src/synapps/web/static/synapps-logo.svg": "synapps/web/static/synapps-logo.svg",
    "src/synapps/web/static/assets": "synapps/web/static/assets",
}


class CustomBuildHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict) -> None:  # noqa: ARG002
        for src, dest in _SPA_ASSETS.items():
            if os.path.exists(src):
                build_data["force_include"][src] = dest
