from __future__ import annotations

import pytest

from synapps.lsp.csharp import _LSP_KIND_MAP as CSHARP_KIND_MAP
from synapps.lsp.java import _LSP_KIND_MAP as JAVA_KIND_MAP
from synapps.lsp.python import _LSP_KIND_MAP as PYTHON_KIND_MAP
from synapps.lsp.typescript import _LSP_KIND_MAP as TS_KIND_MAP
from synapps.lsp.interface import SymbolKind

_ALL_KIND_MAPS = [
    (CSHARP_KIND_MAP, "csharp"),
    (JAVA_KIND_MAP, "java"),
    (PYTHON_KIND_MAP, "python"),
    (TS_KIND_MAP, "typescript"),
]


@pytest.mark.parametrize("kind_map,language", _ALL_KIND_MAPS)
def test_lsp_kind_9_maps_to_method(kind_map: dict, language: str) -> None:
    """VALID-03: LSP kind 9 (Constructor) must map to SymbolKind.METHOD so constructors appear in symbol_map and receive CALLS edges via ReferencesResolver."""
    assert kind_map[9] == SymbolKind.METHOD, (
        f"{language}: expected LSP kind 9 (Constructor) -> SymbolKind.METHOD, "
        f"got {kind_map.get(9)!r}"
    )


@pytest.mark.parametrize("kind_map,language", _ALL_KIND_MAPS)
def test_constructor_kind_9_present_in_all_adapters(kind_map: dict, language: str) -> None:
    """VALID-03: LSP kind 9 must be an explicit key in every adapter's kind map (guards against accidental removal)."""
    assert 9 in kind_map, (
        f"{language}: LSP kind 9 (Constructor) is missing from _LSP_KIND_MAP — "
        "constructors will be silently dropped during symbol indexing"
    )
