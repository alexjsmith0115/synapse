"""Tests for SymbolResolver import-based call resolution fallback."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from synapps.indexer.symbol_resolver import SymbolResolver


def _make_resolver(
    import_map: dict[str, dict[str, str]] | None = None,
    name_to_full_names: dict[str, list[str]] | None = None,
) -> SymbolResolver:
    """Create a SymbolResolver with a mock LSP backend and optional import_map."""
    mock_ls = MagicMock()
    mock_ls.repository_root_path = "/project"
    mock_conn = MagicMock()
    # Default: graph lookup returns nothing (no matching Method node)
    mock_conn.query.return_value = []

    resolver = SymbolResolver(
        conn=mock_conn,
        ls=mock_ls,
        import_map=import_map,
        name_to_full_names=name_to_full_names or {},
    )
    resolver._stats = resolver._stats if hasattr(resolver, "_stats") else None
    return resolver


def test_fallback_resolves_when_lsp_returns_empty() -> None:
    """When LSP returns no definitions, fallback uses import_map to create CALLS edge."""
    import_map = {
        "/project/frontend/src/App.tsx": {
            "AppRoutes": "frontend/src/routes/AppRoutes",
        },
    }
    resolver = _make_resolver(import_map=import_map)
    resolver._ls.request_definition.return_value = []  # LSP returns nothing
    # Graph lookup finds the target method
    resolver._conn.query.return_value = [["frontend/src/routes/AppRoutes.AppRoutes"]]

    symbol_map = {
        ("/project/frontend/src/App.tsx", 4): "App.App",
        ("/project/frontend/src/routes/AppRoutes.tsx", 2): "frontend/src/routes/AppRoutes.AppRoutes",
    }

    resolver._resolve_call(
        caller_full_name="App.App",
        rel_path="frontend/src/App.tsx",
        line_0=9,
        col_0=11,
        callee_simple_name="AppRoutes",
        symbol_map=symbol_map,
        call_line_1=10,
        call_col_0=11,
    )

    # Verify a CALLS edge was created
    assert len(resolver._pending_calls) + len(resolver._pending_module_calls) == 1


def test_fallback_resolves_when_lsp_returns_same_file() -> None:
    """When LSP returns import-line in same file, fallback uses import_map."""
    import_map = {
        "/project/frontend/src/App.tsx": {
            "Navigation": "frontend/src/features/auth/Navigation",
        },
    }
    resolver = _make_resolver(import_map=import_map)
    # LSP returns the import line in the same file (App.tsx line 1)
    resolver._ls.request_definition.return_value = [
        {
            "absolutePath": "/project/frontend/src/App.tsx",
            "relativePath": "frontend/src/App.tsx",
            "range": {"start": {"line": 1, "character": 9}, "end": {"line": 1, "character": 19}},
        }
    ]
    # Graph lookup finds the target
    resolver._conn.query.return_value = [["frontend/src/features/auth/Navigation.Navigation"]]

    symbol_map = {
        ("/project/frontend/src/App.tsx", 4): "App.App",
    }

    resolver._resolve_call(
        caller_full_name="App.App",
        rel_path="frontend/src/App.tsx",
        line_0=9,
        col_0=11,
        callee_simple_name="Navigation",
        symbol_map=symbol_map,
        call_line_1=10,
        call_col_0=11,
    )

    assert len(resolver._pending_calls) + len(resolver._pending_module_calls) == 1


def test_fallback_not_used_when_lsp_succeeds() -> None:
    """When LSP resolves to a cross-file definition, import fallback is skipped."""
    import_map = {
        "/project/src/App.tsx": {
            "Nav": "src/components/Nav",
        },
    }
    resolver = _make_resolver(import_map=import_map)
    # LSP returns the actual definition in another file
    resolver._ls.request_definition.return_value = [
        {
            "absolutePath": "/project/src/components/Nav.tsx",
            "relativePath": "src/components/Nav.tsx",
            "range": {"start": {"line": 2, "character": 0}, "end": {"line": 2, "character": 10}},
        }
    ]

    symbol_map = {
        ("/project/src/App.tsx", 4): "App.App",
        ("/project/src/components/Nav.tsx", 2): "src/components/Nav.Nav",
    }

    resolver._resolve_call(
        caller_full_name="App.App",
        rel_path="src/App.tsx",
        line_0=9,
        col_0=5,
        callee_simple_name="Nav",
        symbol_map=symbol_map,
        call_line_1=10,
        call_col_0=5,
    )

    # Should resolve via LSP path, not fallback
    assert len(resolver._pending_calls) + len(resolver._pending_module_calls) == 1
    # Verify import fallback's specific query was NOT called — import fallback uses
    # MATCH (m:Method {full_name: $name}) ... LIMIT 1, while _resolve_callee_name uses
    # a different query. Check that no call used the import fallback signature.
    import_fallback_calls = [
        c for c in resolver._conn.query.call_args_list
        if "LIMIT 1" in c.args[0] and "full_name: $name" in c.args[0]
    ]
    assert len(import_fallback_calls) == 0, "Import fallback should not have been invoked when LSP succeeds"


def test_fallback_skipped_when_no_import_map() -> None:
    """When import_map is None, the fallback doesn't activate."""
    resolver = _make_resolver(import_map=None)
    resolver._ls.request_definition.return_value = []

    symbol_map = {("/project/src/App.tsx", 4): "App.App"}

    resolver._resolve_call(
        caller_full_name="App.App",
        rel_path="src/App.tsx",
        line_0=9,
        col_0=5,
        callee_simple_name="SomeComponent",
        symbol_map=symbol_map,
        call_line_1=10,
        call_col_0=5,
    )

    assert len(resolver._pending_calls) + len(resolver._pending_module_calls) == 0


def test_fallback_uses_name_to_full_names_when_graph_misses() -> None:
    """When graph query returns empty, fall back to name_to_full_names for unambiguous match."""
    import_map = {
        "/project/src/App.tsx": {
            "Nav": "src/components/Nav",
        },
    }
    resolver = _make_resolver(
        import_map=import_map,
        name_to_full_names={"Nav": ["src/components/Nav.Nav"]},
    )
    resolver._ls.request_definition.return_value = []
    # First query (full_name match): miss
    # Second query (_resolve_callee_name): hit
    resolver._conn.query.side_effect = [[], [["src/components/Nav.Nav"]]]

    symbol_map = {("/project/src/App.tsx", 4): "App.App"}

    resolver._resolve_call(
        caller_full_name="App.App",
        rel_path="src/App.tsx",
        line_0=9,
        col_0=5,
        callee_simple_name="Nav",
        symbol_map=symbol_map,
        call_line_1=10,
        call_col_0=5,
    )

    assert len(resolver._pending_calls) + len(resolver._pending_module_calls) == 1
