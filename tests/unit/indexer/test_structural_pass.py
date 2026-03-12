import pytest
from unittest.mock import MagicMock, call, mock_open, patch
from synapse.indexer.indexer import Indexer
from synapse.lsp.interface import IndexSymbol, SymbolKind, LSPAdapter


@pytest.fixture
def mock_conn():
    return MagicMock()


def _make_symbol(name: str, kind: SymbolKind, file_path: str = "/proj/Foo.cs") -> IndexSymbol:
    return IndexSymbol(
        name=name,
        full_name=f"MyNs.{name}",
        kind=kind,
        file_path=file_path,
        line=10,
    )


def test_index_project_links_repository_to_root_directory() -> None:
    conn = MagicMock()
    lsp = MagicMock()
    lsp.get_workspace_files.return_value = ["/proj/Foo.cs"]
    lsp.get_document_symbols.return_value = []

    indexer = Indexer(conn, lsp)
    indexer.index_project("/proj", "csharp")

    calls = [str(c) for c in conn.execute.call_args_list]
    assert any("Repository" in c and "Directory" in c and "CONTAINS" in c for c in calls), (
        "index_project must create a Repository-[CONTAINS]->Directory edge so delete_project can traverse the full graph"
    )


def test_index_project_normalizes_trailing_slash() -> None:
    """Trailing slash on root_path must not break Repository->Directory edge.

    upsert_repository strips the slash before storing, but upsert_repo_contains_dir
    would then query for the un-stripped path and silently create no edge.
    Normalizing at index_project entry avoids the mismatch.
    """
    conn = MagicMock()
    lsp = MagicMock()
    lsp.get_workspace_files.return_value = ["/proj/Foo.cs"]
    lsp.get_document_symbols.return_value = []

    indexer = Indexer(conn, lsp)
    indexer.index_project("/proj/", "csharp")

    # Repository must be stored without trailing slash
    repo_calls = [str(c) for c in conn.execute.call_args_list if "Repository" in str(c)]
    assert all("/proj/" not in c for c in repo_calls), "Repository stored with trailing slash"

    # Repo-to-Dir CONTAINS edge must be created with consistent paths
    contains_calls = [str(c) for c in conn.execute.call_args_list if "CONTAINS" in str(c) and "Repository" in str(c)]
    assert contains_calls, "No Repository-[CONTAINS]->Directory edge created"
    assert all("/proj/" not in c for c in contains_calls), "CONTAINS edge used slash-inconsistent paths"


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


def test_index_project_runs_symbol_resolver_after_structural_pass() -> None:
    conn = MagicMock()
    lsp = MagicMock()
    lsp.get_workspace_files.return_value = ["/proj/Foo.cs"]
    lsp.get_document_symbols.return_value = []

    with patch("synapse.indexer.indexer.SymbolResolver") as MockResolver:
        indexer = Indexer(conn, lsp)
        indexer.index_project("/proj", "csharp")

    args, _ = MockResolver.return_value.resolve.call_args
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


def test_index_project_runs_base_type_extractor() -> None:
    conn = MagicMock()
    lsp = MagicMock()
    lsp.get_workspace_files.return_value = ["/proj/Foo.cs"]
    lsp.get_document_symbols.return_value = []

    mock_extractor_cls = MagicMock()
    mock_extractor_instance = MagicMock()
    mock_extractor_cls.return_value = mock_extractor_instance
    mock_extractor_instance.extract.return_value = []

    with patch("synapse.indexer.indexer.CSharpBaseTypeExtractor", mock_extractor_cls):
        indexer = Indexer(conn, lsp)
        with patch("builtins.open", mock_open(read_data="")):
            indexer.index_project("/proj", "csharp")

    mock_extractor_instance.extract.assert_called()


def test_directory_chain_creates_dir_contains_file() -> None:
    conn = MagicMock()
    lsp = MagicMock()
    lsp.get_workspace_files.return_value = ["/proj/src/Foo.cs"]
    lsp.get_document_symbols.return_value = []

    indexer = Indexer(conn, lsp)
    indexer.index_project("/proj", "csharp")

    calls = [str(c) for c in conn.execute.call_args_list]
    assert any("/proj/src" in c and "/proj/src/Foo.cs" in c and "CONTAINS" in c for c in calls)


def test_index_project_uses_symbol_resolver(mock_conn):
    """Verify that index_project delegates to SymbolResolver instead of CallIndexer."""
    lsp = MagicMock()
    lsp.get_workspace_files.return_value = []

    with patch("synapse.indexer.indexer.SymbolResolver") as MockResolver:
        indexer = Indexer(mock_conn, lsp)
        indexer.index_project("/proj", "csharp")
        MockResolver.assert_called_once()
        MockResolver.return_value.resolve.assert_called_once()


def test_upsert_symbol_passes_end_line(mock_conn):
    """Verify that _upsert_symbol passes end_line from IndexSymbol to the node upsert."""
    lsp = MagicMock(spec=LSPAdapter)
    indexer = Indexer(mock_conn, lsp)
    sym = IndexSymbol(
        name="MyMethod", full_name="Ns.C.MyMethod", kind=SymbolKind.METHOD,
        file_path="/proj/F.cs", line=10, end_line=20, signature="void MyMethod()",
    )
    indexer._upsert_symbol(sym)
    _, params = mock_conn.execute.call_args[0]
    assert params["end_line"] == 20


def test_index_project_calls_method_implements_indexer() -> None:
    """Phase 1.5 must run after structural pass completes."""
    conn = MagicMock()
    lsp = MagicMock()
    lsp.get_workspace_files.return_value = []

    with patch("synapse.indexer.indexer.MethodImplementsIndexer") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        Indexer(conn, lsp).index_project("/proj", "csharp")

    mock_instance.index.assert_called_once()
