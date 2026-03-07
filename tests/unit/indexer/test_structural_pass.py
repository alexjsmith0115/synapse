from unittest.mock import MagicMock, call
from synapse.indexer.indexer import Indexer
from synapse.lsp.interface import IndexSymbol, SymbolKind


def _make_symbol(name: str, kind: SymbolKind, file_path: str = "/proj/Foo.cs") -> IndexSymbol:
    return IndexSymbol(
        name=name,
        full_name=f"MyNs.{name}",
        kind=kind,
        file_path=file_path,
        line=10,
    )


def test_index_project_upserts_file_node() -> None:
    conn = MagicMock()
    lsp = MagicMock()
    lsp.get_workspace_files.return_value = ["/proj/Foo.cs"]
    lsp.get_document_symbols.return_value = []

    indexer = Indexer(conn, lsp)
    indexer.index_project("/proj", "csharp")

    calls = [str(c) for c in conn.execute.call_args_list]
    assert any("File" in c for c in calls)


def test_index_project_upserts_class_symbol() -> None:
    conn = MagicMock()
    lsp = MagicMock()
    lsp.get_workspace_files.return_value = ["/proj/Foo.cs"]
    lsp.get_document_symbols.return_value = [
        _make_symbol("MyClass", SymbolKind.CLASS),
    ]
    lsp.find_method_calls.return_value = []
    lsp.find_overridden_method.return_value = None

    indexer = Indexer(conn, lsp)
    indexer.index_project("/proj", "csharp")

    calls = [str(c) for c in conn.execute.call_args_list]
    assert any("MyClass" in c for c in calls)


def test_index_project_shuts_down_lsp() -> None:
    conn = MagicMock()
    lsp = MagicMock()
    lsp.get_workspace_files.return_value = []

    indexer = Indexer(conn, lsp)
    indexer.index_project("/proj", "csharp")

    lsp.shutdown.assert_called_once()


def test_index_project_does_not_shut_down_lsp_in_watch_mode() -> None:
    conn = MagicMock()
    lsp = MagicMock()
    lsp.get_workspace_files.return_value = []

    indexer = Indexer(conn, lsp)
    indexer.index_project("/proj", "csharp", keep_lsp_running=True)

    lsp.shutdown.assert_not_called()
