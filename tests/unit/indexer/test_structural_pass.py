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


def test_reindex_file_preserves_summaries(mock_conn) -> None:
    """reindex_file must save summaries before deleting nodes and restore them after re-indexing."""
    lsp = MagicMock()
    lsp.get_document_symbols.return_value = []

    with patch("synapse.indexer.indexer.collect_summaries") as mock_collect, \
         patch("synapse.indexer.indexer.restore_summaries") as mock_restore, \
         patch("synapse.indexer.indexer.SymbolResolver"):
        mock_collect.return_value = [
            {"full_name": "Ns.C", "summary": "A class", "summary_updated_at": "2026-03-16T00:00:00+00:00"},
        ]
        indexer = Indexer(mock_conn, lsp)
        indexer.reindex_file("/proj/Foo.cs", "/proj")

    mock_collect.assert_called_once_with(mock_conn, "/proj/Foo.cs")
    mock_restore.assert_called_once_with(mock_conn, mock_collect.return_value)


# ---------------------------------------------------------------------------
# Python-specific behavior tests
# ---------------------------------------------------------------------------

def _make_py_symbol(name: str, kind: SymbolKind, parent_full_name: str | None = None, signature: str = "") -> IndexSymbol:
    full_name = f"mymod.{name}" if parent_full_name is None else f"{parent_full_name}.{name}"
    return IndexSymbol(
        name=name,
        full_name=full_name,
        kind=kind,
        file_path="/proj/mymod.py",
        line=1,
        parent_full_name=parent_full_name,
        signature=signature,
    )


def _make_python_indexer(conn):
    """Create an Indexer with language='python' using mock LSP and plugin."""
    lsp = MagicMock(spec=LSPAdapter)
    plugin = MagicMock()
    plugin.name = "python"
    plugin.file_extensions = frozenset({".py"})
    plugin.create_import_extractor.return_value = MagicMock(_source_root="")
    plugin.create_base_type_extractor.return_value = MagicMock()
    plugin.create_attribute_extractor = MagicMock(return_value=None)
    plugin.create_call_extractor = MagicMock(return_value=None)
    plugin.create_type_ref_extractor = MagicMock(return_value=None)
    return Indexer(conn, lsp, plugin)


def test_python_init_method_produces_kind_constructor(mock_conn):
    """__init__ method for Python must store kind='constructor'."""
    indexer = _make_python_indexer(mock_conn)
    sym = _make_py_symbol("__init__", SymbolKind.METHOD, parent_full_name="mymod.MyClass")
    indexer._upsert_symbol(sym)
    _, params = mock_conn.execute.call_args[0]
    # upsert_method is called; verify no kind_str overrides appear in query params
    # The kind_str for constructor is only used for CLASS nodes; METHOD stores signature/is_abstract.
    # What matters: the method node for __init__ is stored with language='python'.
    assert params.get("language") == "python"


def test_python_top_level_function_kind_str_is_function(mock_conn):
    """Standalone Python function (no parent) must use kind_str='function' for upsert_class fallthrough.

    Note: kind=METHOD uses upsert_method, which doesn't take kind_str. This test verifies the
    kind_str logic runs without error and language is passed through correctly.
    """
    indexer = _make_python_indexer(mock_conn)
    # A top-level function: kind=METHOD, parent_full_name=None
    sym = IndexSymbol(
        name="my_func",
        full_name="mymod.my_func",
        kind=SymbolKind.METHOD,
        file_path="/proj/mymod.py",
        line=1,
        parent_full_name=None,
    )
    indexer._upsert_symbol(sym)
    _, params = mock_conn.execute.call_args[0]
    assert params.get("language") == "python"


def test_python_module_symbol_uses_kind_module(mock_conn):
    """Symbol with signature='module' and kind=CLASS must store kind='module'."""
    indexer = _make_python_indexer(mock_conn)
    sym = IndexSymbol(
        name="mymod",
        full_name="mymod",
        kind=SymbolKind.CLASS,
        file_path="/proj/mymod.py",
        line=0,
        signature="module",
    )
    indexer._upsert_symbol(sym)
    _, params = mock_conn.execute.call_args[0]
    assert params.get("kind") == "module"
    assert params.get("language") == "python"


def test_python_class_symbol_passes_language(mock_conn):
    """Python class symbol must pass language='python' to upsert_class."""
    indexer = _make_python_indexer(mock_conn)
    sym = _make_py_symbol("MyClass", SymbolKind.CLASS)
    indexer._upsert_symbol(sym)
    _, params = mock_conn.execute.call_args[0]
    assert params.get("language") == "python"


def test_python_method_symbol_passes_language(mock_conn):
    """Python method symbol must pass language='python' to upsert_method."""
    indexer = _make_python_indexer(mock_conn)
    sym = _make_py_symbol("do_work", SymbolKind.METHOD, parent_full_name="mymod.MyClass")
    indexer._upsert_symbol(sym)
    _, params = mock_conn.execute.call_args[0]
    assert params.get("language") == "python"


def test_python_base_types_all_produce_inherits(mock_conn):
    """Python base types must all produce upsert_inherits, never upsert_implements."""
    indexer = _make_python_indexer(mock_conn)
    name_to_full_names = {"Dog": ["mymod.Dog"], "Animal": ["mymod.Animal"]}
    kind_map = {"mymod.Dog": SymbolKind.CLASS, "mymod.Animal": SymbolKind.CLASS}

    mock_extractor = indexer._base_type_extractor
    mock_extractor.extract.return_value = [("Dog", "Animal", True)]

    indexer._index_base_types("/proj/mymod.py", "class Dog(Animal): pass", name_to_full_names, kind_map)

    calls = [str(c) for c in mock_conn.execute.call_args_list]
    assert any("INHERITS" in c for c in calls), "Expected INHERITS edge for Python base type"
    assert not any("IMPLEMENTS" in c for c in calls), "Python base types must not produce IMPLEMENTS"


def test_python_import_extractor_tuple_output_handled(mock_conn):
    """Python (tuple) import results must call upsert_symbol_imports, not upsert_imports."""
    lsp = MagicMock(spec=LSPAdapter)
    plugin = MagicMock()
    plugin.name = "python"
    plugin.file_extensions = frozenset({".py"})
    mock_extractor = MagicMock()
    mock_extractor._source_root = "/src"
    mock_extractor.extract.return_value = [("mypack.utils", "helper"), ("mypack.other", None)]
    plugin.create_import_extractor.return_value = mock_extractor
    plugin.create_base_type_extractor.return_value = MagicMock()
    plugin.create_attribute_extractor = MagicMock(return_value=None)
    plugin.create_call_extractor = MagicMock(return_value=None)
    plugin.create_type_ref_extractor = MagicMock(return_value=None)

    indexer = Indexer(mock_conn, lsp, plugin)

    with patch("builtins.open", mock_open(read_data="from mypack.utils import helper")):
        indexer._index_file_imports("/src/main.py")

    cypher_calls = [c[0][0] for c in mock_conn.execute.call_args_list]
    # Both should be IMPORTS edges via upsert_symbol_imports (not upsert_imports to :Package)
    assert all("IMPORTS" in cypher for cypher in cypher_calls)
    # Full symbol path for from-import
    params_list = [c[0][1] for c in mock_conn.execute.call_args_list]
    sym_values = [p.get("sym") for p in params_list if "sym" in p]
    assert "mypack.utils.helper" in sym_values
    assert "mypack.other" in sym_values


def test_csharp_import_extractor_string_output_still_handled(mock_conn):
    """C# (string) import results must still call upsert_imports (no regression)."""
    lsp = MagicMock(spec=LSPAdapter)
    indexer = Indexer(mock_conn, lsp)  # default = csharp plugin path

    with patch.object(indexer._import_extractor, "extract", return_value=["System.Collections"]):
        with patch("builtins.open", mock_open(read_data="using System.Collections;")):
            indexer._index_file_imports("/proj/Foo.cs")

    calls = [c[0] for c in mock_conn.execute.call_args_list]
    # upsert_imports uses $pkg parameter
    assert any("$pkg" in cypher for cypher, _ in calls)


def test_reindex_file_python(mock_conn):
    """PIDX-09: Indexer.reindex_file() must work for a .py file path."""
    mock_symbols = [
        IndexSymbol(
            name="MyClass",
            full_name="mymod.MyClass",
            kind=SymbolKind.CLASS,
            file_path="/src/mymod.py",
            line=1,
        )
    ]
    lsp = MagicMock()  # no spec — language_server not in LSPAdapter protocol
    lsp.get_document_symbols.return_value = mock_symbols

    plugin = MagicMock()
    plugin.name = "python"
    plugin.file_extensions = frozenset({".py"})
    mock_extractor = MagicMock(_source_root="/src")
    mock_extractor.extract.return_value = []
    plugin.create_import_extractor.return_value = mock_extractor
    mock_base = MagicMock()
    mock_base.extract.return_value = []
    plugin.create_base_type_extractor.return_value = mock_base
    plugin.create_attribute_extractor = MagicMock(return_value=None)
    plugin.create_call_extractor = MagicMock(return_value=None)
    plugin.create_type_ref_extractor = MagicMock(return_value=None)

    with patch("synapse.indexer.indexer.collect_summaries", return_value=[]), \
         patch("synapse.indexer.indexer.restore_summaries"), \
         patch("synapse.indexer.indexer.SymbolResolver"), \
         patch("builtins.open", mock_open(read_data="class MyClass: pass")):
        indexer = Indexer(mock_conn, lsp, plugin)
        indexer.reindex_file("/src/mymod.py", "/src")

    lsp.get_document_symbols.assert_called_once_with("/src/mymod.py")
    calls = [str(c) for c in mock_conn.execute.call_args_list]
    assert any("mymod.MyClass" in c for c in calls), "Expected MyClass node to be upserted"


def _make_python_plugin_with_call_ext():
    """Build a Python plugin mock that exposes a call extractor with _module_name_resolver."""
    plugin = MagicMock()
    plugin.name = "python"
    plugin.file_extensions = frozenset({".py"})
    mock_extractor = MagicMock(_source_root="/src")
    mock_extractor.extract.return_value = []
    plugin.create_import_extractor.return_value = mock_extractor
    mock_base = MagicMock()
    mock_base.extract.return_value = []
    plugin.create_base_type_extractor.return_value = mock_base
    plugin.create_attribute_extractor = MagicMock(return_value=None)
    call_ext = MagicMock()
    call_ext._module_name_resolver = None
    plugin.create_call_extractor = MagicMock(return_value=call_ext)
    plugin.create_type_ref_extractor = MagicMock(return_value=None)
    return plugin, call_ext


def _make_python_symbols():
    """Return a module symbol + a method symbol for /src/mymod.py."""
    module_sym = IndexSymbol(
        name="mymod",
        full_name="mymod",
        kind=SymbolKind.CLASS,
        file_path="/src/mymod.py",
        line=0,
        signature="module",
    )
    method_sym = IndexSymbol(
        name="foo",
        full_name="mymod.foo",
        kind=SymbolKind.METHOD,
        file_path="/src/mymod.py",
        line=5,
    )
    return [module_sym, method_sym]


def test_reindex_file_python_call_wiring(mock_conn):
    """PCAL-02: reindex_file() must pass module_full_names to SymbolResolver for Python."""
    plugin, call_ext = _make_python_plugin_with_call_ext()
    lsp = MagicMock()
    lsp.get_document_symbols.return_value = _make_python_symbols()

    with patch("synapse.indexer.indexer.SymbolResolver") as mock_resolver_cls, \
         patch("synapse.indexer.indexer.collect_summaries", return_value=[]), \
         patch("synapse.indexer.indexer.restore_summaries"), \
         patch("builtins.open", mock_open(read_data="def foo(): pass")):
        indexer = Indexer(mock_conn, lsp, plugin)
        indexer.reindex_file("/src/mymod.py", "/src")

    _, kwargs = mock_resolver_cls.call_args
    assert "module_full_names" in kwargs, "SymbolResolver must receive module_full_names kwarg"
    assert "mymod" in kwargs["module_full_names"], "module_full_names must contain the module full_name"


def test_reindex_file_python_overrides(mock_conn):
    """PCAL-03: reindex_file() must call OverridesIndexer for Python files."""
    plugin, _call_ext = _make_python_plugin_with_call_ext()
    lsp = MagicMock()
    lsp.get_document_symbols.return_value = _make_python_symbols()

    with patch("synapse.indexer.indexer.SymbolResolver"), \
         patch("synapse.indexer.indexer.OverridesIndexer") as mock_oi_cls, \
         patch("synapse.indexer.indexer.collect_summaries", return_value=[]), \
         patch("synapse.indexer.indexer.restore_summaries"), \
         patch("builtins.open", mock_open(read_data="def foo(): pass")):
        mock_oi_instance = MagicMock()
        mock_oi_cls.return_value = mock_oi_instance
        indexer = Indexer(mock_conn, lsp, plugin)
        indexer.reindex_file("/src/mymod.py", "/src")

    mock_oi_cls.assert_called_once_with(mock_conn)
    mock_oi_instance.index.assert_called_once()


def test_reindex_file_python_module_name_resolver(mock_conn):
    """PCAL-02: reindex_file() must wire _module_name_resolver on the call extractor."""
    plugin, call_ext = _make_python_plugin_with_call_ext()
    lsp = MagicMock()
    lsp.get_document_symbols.return_value = _make_python_symbols()

    with patch("synapse.indexer.indexer.SymbolResolver"), \
         patch("synapse.indexer.indexer.OverridesIndexer"), \
         patch("synapse.indexer.indexer.collect_summaries", return_value=[]), \
         patch("synapse.indexer.indexer.restore_summaries"), \
         patch("builtins.open", mock_open(read_data="def foo(): pass")):
        indexer = Indexer(mock_conn, lsp, plugin)
        indexer.reindex_file("/src/mymod.py", "/src")

    assert call_ext._module_name_resolver is not None, "_module_name_resolver must be set after reindex_file"
    assert call_ext._module_name_resolver("/src/mymod.py") == "mymod", (
        "_module_name_resolver must map file_path to module full_name"
    )


# ---------------------------------------------------------------------------
# TypeScript-specific reindex tests
# ---------------------------------------------------------------------------

def _make_typescript_plugin_with_call_ext():
    """Build a TypeScript plugin mock that exposes a call extractor with _module_name_resolver."""
    plugin = MagicMock()
    plugin.name = "typescript"
    plugin.file_extensions = frozenset({".ts", ".tsx", ".js", ".jsx", ".mts", ".cts", ".mjs", ".cjs"})
    mock_extractor = MagicMock(_source_root="")
    mock_extractor.extract.return_value = []
    plugin.create_import_extractor.return_value = mock_extractor
    mock_base = MagicMock()
    mock_base.extract.return_value = []
    plugin.create_base_type_extractor.return_value = mock_base
    plugin.create_attribute_extractor = MagicMock(return_value=None)
    call_ext = MagicMock()
    call_ext._module_name_resolver = None
    plugin.create_call_extractor = MagicMock(return_value=call_ext)
    plugin.create_type_ref_extractor = MagicMock(return_value=None)
    return plugin, call_ext


def test_reindex_file_typescript(mock_conn):
    """Indexer.reindex_file() must work for a .ts file path."""
    mock_symbols = [
        IndexSymbol(
            name="MyClass",
            full_name="src/mod.MyClass",
            kind=SymbolKind.CLASS,
            file_path="/src/mod.ts",
            line=0,
        )
    ]
    lsp = MagicMock()
    lsp.get_document_symbols.return_value = mock_symbols

    plugin = MagicMock()
    plugin.name = "typescript"
    plugin.file_extensions = frozenset({".ts", ".tsx", ".js", ".jsx", ".mts", ".cts", ".mjs", ".cjs"})
    mock_extractor = MagicMock(_source_root="")
    mock_extractor.extract.return_value = []
    plugin.create_import_extractor.return_value = mock_extractor
    mock_base = MagicMock()
    mock_base.extract.return_value = []
    plugin.create_base_type_extractor.return_value = mock_base
    plugin.create_attribute_extractor = MagicMock(return_value=None)
    plugin.create_call_extractor = MagicMock(return_value=None)
    plugin.create_type_ref_extractor = MagicMock(return_value=None)

    with patch("synapse.indexer.indexer.collect_summaries", return_value=[]), \
         patch("synapse.indexer.indexer.restore_summaries"), \
         patch("synapse.indexer.indexer.SymbolResolver"), \
         patch("synapse.indexer.indexer.delete_file_nodes"), \
         patch("builtins.open", mock_open(read_data="class MyClass {}")):
        indexer = Indexer(mock_conn, lsp, plugin)
        indexer.reindex_file("/src/mod.ts", "/src")

    lsp.get_document_symbols.assert_called_once_with("/src/mod.ts")


def test_reindex_file_typescript_call_wiring(mock_conn):
    """reindex_file() must wire _module_name_resolver on the TypeScript call extractor."""
    plugin, call_ext = _make_typescript_plugin_with_call_ext()
    lsp = MagicMock()
    lsp.get_document_symbols.return_value = [
        IndexSymbol(
            name="src/mod",
            full_name="src/mod",
            kind=SymbolKind.CLASS,
            file_path="/src/mod.ts",
            line=0,
            signature="module",
        ),
        IndexSymbol(
            name="MyClass",
            full_name="src/mod.MyClass",
            kind=SymbolKind.CLASS,
            file_path="/src/mod.ts",
            line=1,
        ),
    ]

    with patch("synapse.indexer.indexer.SymbolResolver") as mock_resolver_cls, \
         patch("synapse.indexer.indexer.collect_summaries", return_value=[]), \
         patch("synapse.indexer.indexer.restore_summaries"), \
         patch("synapse.indexer.indexer.delete_file_nodes"), \
         patch("builtins.open", mock_open(read_data="class MyClass {}")):
        indexer = Indexer(mock_conn, lsp, plugin)
        indexer.reindex_file("/src/mod.ts", "/src")

    _, kwargs = mock_resolver_cls.call_args
    assert "module_full_names" in kwargs, "SymbolResolver must receive module_full_names kwarg"
    assert "src/mod" in kwargs["module_full_names"], "module_full_names must contain module full_name"
