from unittest.mock import MagicMock, patch

from synapse.indexer.indexer import Indexer
from synapse.lsp.interface import IndexSymbol, SymbolKind


def _mock_lsp(files: list[str], symbols_by_file: dict[str, list[IndexSymbol]]) -> MagicMock:
    lsp = MagicMock()
    lsp.get_workspace_files.return_value = files
    lsp.get_document_symbols.side_effect = lambda f: symbols_by_file.get(f, [])
    lsp.language_server = MagicMock()
    return lsp


def test_index_project_calls_set_attributes(tmp_path) -> None:
    cs_file = tmp_path / "Test.cs"
    cs_file.write_text("""
[ApiController]
public class TaskController {
    [HttpGet]
    public void Get() { }
}
""")
    file_path = str(cs_file)
    symbols = [
        IndexSymbol(
            name="TaskController", full_name="Ns.TaskController", kind=SymbolKind.CLASS,
            file_path=file_path, line=2, end_line=6, signature="", is_abstract=False, is_static=False,
        ),
        IndexSymbol(
            name="Get", full_name="Ns.TaskController.Get", kind=SymbolKind.METHOD,
            file_path=file_path, line=4, end_line=5, signature="void Get()", is_abstract=False, is_static=False,
        ),
    ]
    lsp = _mock_lsp([file_path], {file_path: symbols})
    conn = MagicMock()

    with patch("synapse.indexer.indexer.SymbolResolver"), \
         patch("synapse.indexer.indexer.MethodImplementsIndexer"):
        indexer = Indexer(conn, lsp)
        indexer.index_project(str(tmp_path), "csharp")

    # Verify set_attributes was called for both attributed symbols
    set_attr_calls = [
        c for c in conn.execute.call_args_list
        if "attributes" in str(c)
    ]
    assert len(set_attr_calls) >= 2, f"Expected at least 2 set_attributes calls, got {len(set_attr_calls)}"


def test_reindex_file_calls_set_attributes(tmp_path) -> None:
    cs_file = tmp_path / "Test.cs"
    cs_file.write_text("""
[Serializable]
public class Foo { }
""")
    file_path = str(cs_file)
    symbols = [
        IndexSymbol(
            name="Foo", full_name="Ns.Foo", kind=SymbolKind.CLASS,
            file_path=file_path, line=2, end_line=3, signature="", is_abstract=False, is_static=False,
        ),
    ]
    lsp = _mock_lsp([file_path], {file_path: symbols})
    conn = MagicMock()

    with patch("synapse.indexer.indexer.SymbolResolver"), \
         patch("synapse.indexer.indexer.MethodImplementsIndexer"):
        indexer = Indexer(conn, lsp)
        indexer.reindex_file(file_path, str(tmp_path))

    set_attr_calls = [
        c for c in conn.execute.call_args_list
        if "attributes" in str(c)
    ]
    assert len(set_attr_calls) >= 1, f"Expected at least 1 set_attributes call, got {len(set_attr_calls)}"
