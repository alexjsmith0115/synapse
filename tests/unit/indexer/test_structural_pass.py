from unittest.mock import MagicMock, call, patch
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


def test_index_project_runs_call_indexer_after_structural_pass() -> None:
    conn = MagicMock()
    lsp = MagicMock()
    lsp.get_workspace_files.return_value = ["/proj/Foo.cs"]
    lsp.get_document_symbols.return_value = []

    mock_call_indexer_cls = MagicMock()
    mock_call_indexer_instance = MagicMock()
    mock_call_indexer_cls.return_value = mock_call_indexer_instance

    with patch("synapse.indexer.indexer.CallIndexer", mock_call_indexer_cls):
        indexer = Indexer(conn, lsp)
        indexer.index_project("/proj", "csharp")

    args, _ = mock_call_indexer_instance.index_calls.call_args
    assert args[0] == "/proj"


def _make_nested_symbol(
    parent_full_name: str, name: str, kind: SymbolKind, file_path: str = "/proj/Foo.cs"
) -> IndexSymbol:
    return IndexSymbol(
        name=name,
        full_name=f"{parent_full_name}.{name}",
        kind=kind,
        file_path=file_path,
        line=10,
        parent_full_name=parent_full_name,
    )


def test_nested_symbol_gets_contains_from_parent_not_file() -> None:
    conn = MagicMock()
    lsp = MagicMock()
    lsp.get_workspace_files.return_value = ["/proj/Foo.cs"]
    lsp.get_document_symbols.return_value = [
        _make_symbol("MyClass", SymbolKind.CLASS),
        _make_nested_symbol("MyNs.MyClass", "DoWork", SymbolKind.METHOD),
    ]

    indexer = Indexer(conn, lsp)
    indexer.index_project("/proj", "csharp")

    calls = [str(c) for c in conn.execute.call_args_list]
    assert any("MyNs.MyClass" in c and "MyNs.MyClass.DoWork" in c and "CONTAINS" in c for c in calls)


def test_top_level_symbol_gets_contains_from_file() -> None:
    conn = MagicMock()
    lsp = MagicMock()
    lsp.get_workspace_files.return_value = ["/proj/Foo.cs"]
    lsp.get_document_symbols.return_value = [
        _make_symbol("MyClass", SymbolKind.CLASS),
    ]

    indexer = Indexer(conn, lsp)
    indexer.index_project("/proj", "csharp")

    calls = [str(c) for c in conn.execute.call_args_list]
    assert any("/proj/Foo.cs" in c and "MyNs.MyClass" in c and "CONTAINS" in c for c in calls)


def test_directory_chain_creates_dir_contains_dir() -> None:
    conn = MagicMock()
    lsp = MagicMock()
    lsp.get_workspace_files.return_value = ["/proj/src/Foo.cs"]
    lsp.get_document_symbols.return_value = []

    indexer = Indexer(conn, lsp)
    indexer.index_project("/proj", "csharp")

    calls = [str(c) for c in conn.execute.call_args_list]
    assert any("/proj" in c and "/proj/src" in c and "CONTAINS" in c for c in calls)


def test_interface_symbol_creates_interface_node() -> None:
    conn = MagicMock()
    lsp = MagicMock()
    lsp.get_workspace_files.return_value = ["/proj/Foo.cs"]
    lsp.get_document_symbols.return_value = [
        _make_symbol("IMyService", SymbolKind.INTERFACE),
    ]

    indexer = Indexer(conn, lsp)
    indexer.index_project("/proj", "csharp")

    calls = [str(c) for c in conn.execute.call_args_list]
    assert any(":Interface" in c and "IMyService" in c for c in calls)
