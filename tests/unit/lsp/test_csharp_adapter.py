from unittest.mock import MagicMock
from synapse.lsp.interface import SymbolKind


def test_symbol_kind_values_cover_csharp_types() -> None:
    assert SymbolKind.CLASS in SymbolKind.__members__.values()
    assert SymbolKind.INTERFACE in SymbolKind.__members__.values()
    assert SymbolKind.METHOD in SymbolKind.__members__.values()
    assert SymbolKind.PROPERTY in SymbolKind.__members__.values()
    assert SymbolKind.FIELD in SymbolKind.__members__.values()
    assert SymbolKind.NAMESPACE in SymbolKind.__members__.values()


def test_csharp_adapter_implements_protocol() -> None:
    from synapse.lsp.interface import LSPAdapter
    from synapse.lsp.csharp import CSharpLSPAdapter
    # Protocol runtime check
    assert issubclass(CSharpLSPAdapter, LSPAdapter) or hasattr(CSharpLSPAdapter, "get_workspace_files")


from synapse.lsp.util import build_full_name


def test_build_full_name_root_symbol() -> None:
    raw = {"name": "MyNamespace", "kind": 3}
    assert build_full_name(raw) == "MyNamespace"


def test_build_full_name_one_parent() -> None:
    parent = {"name": "MyNs", "kind": 3}
    raw = {"name": "MyClass", "kind": 5, "parent": parent}
    assert build_full_name(raw) == "MyNs.MyClass"


def test_build_full_name_two_parents() -> None:
    grandparent = {"name": "MyNs", "kind": 3}
    parent = {"name": "MyClass", "kind": 5, "parent": grandparent}
    raw = {"name": "MyMethod", "kind": 6, "parent": parent}
    assert build_full_name(raw) == "MyNs.MyClass.MyMethod"


def test_build_full_name_overload_appends_params() -> None:
    parent = {"name": "MyClass", "kind": 5}
    raw = {"name": "DoWork", "kind": 6, "parent": parent, "overload_idx": 1, "detail": "void DoWork(int x, string y)"}
    assert build_full_name(raw) == "MyClass.DoWork(int x, string y)"


def test_build_full_name_overload_no_paren_in_detail() -> None:
    parent = {"name": "MyClass", "kind": 5}
    raw = {"name": "DoWork", "kind": 6, "parent": parent, "overload_idx": 0, "detail": "void DoWork"}
    assert build_full_name(raw) == "MyClass.DoWork"


def test_convert_produces_qualified_full_name() -> None:
    from synapse.lsp.csharp import CSharpLSPAdapter

    grandparent = {"name": "MyNs", "kind": 3, "parent": None}
    parent = {"name": "MyClass", "kind": 5, "parent": grandparent}
    symbol_raw = {
        "name": "MyMethod",
        "kind": 6,
        "parent": parent,
        "detail": "public void MyMethod()",
        "location": {"range": {"start": {"line": 10}}},
    }

    mock_doc_syms = MagicMock()
    mock_doc_syms.iter_symbols.return_value = [symbol_raw]
    mock_ls = MagicMock()
    mock_ls.request_document_symbols.return_value = mock_doc_syms

    adapter = CSharpLSPAdapter(mock_ls)
    symbols = adapter.get_document_symbols("/proj/Foo.cs")

    assert len(symbols) == 1
    assert symbols[0].full_name == "MyNs.MyClass.MyMethod"
    assert symbols[0].name == "MyMethod"


def test_find_method_calls_returns_empty() -> None:
    from synapse.lsp.csharp import CSharpLSPAdapter
    from synapse.lsp.interface import IndexSymbol, SymbolKind

    adapter = CSharpLSPAdapter(MagicMock())
    symbol = IndexSymbol(
        name="DoWork", full_name="MyNs.MyClass.DoWork", kind=SymbolKind.METHOD,
        file_path="/proj/Foo.cs", line=10, signature="public void DoWork()",
    )
    assert adapter.find_method_calls(symbol) == []


def test_find_overridden_method_returns_none() -> None:
    from synapse.lsp.csharp import CSharpLSPAdapter
    from synapse.lsp.interface import IndexSymbol, SymbolKind

    adapter = CSharpLSPAdapter(MagicMock())
    symbol = IndexSymbol(
        name="Execute", full_name="MyNs.MyClass.Execute", kind=SymbolKind.METHOD,
        file_path="/proj/Foo.cs", line=5, signature="public override void Execute()",
    )
    assert adapter.find_overridden_method(symbol) is None


def test_create_uses_csharp_language_enum() -> None:
    import sys
    from unittest.mock import patch, MagicMock
    from synapse.lsp.csharp import CSharpLSPAdapter

    mock_config_class = MagicMock()

    class FakeLanguage:
        CSHARP = "csharp"

    fake_ls_config = MagicMock()
    fake_ls_config.Language = FakeLanguage
    fake_ls_config.LanguageServerConfig = mock_config_class

    fake_csharp_ls = MagicMock()
    fake_csharp_ls.CSharpLanguageServer.return_value = MagicMock()

    with patch.dict(sys.modules, {
        "solidlsp.ls_config": fake_ls_config,
        "solidlsp.settings": MagicMock(),
        "solidlsp.language_servers.csharp_language_server": fake_csharp_ls,
    }):
        CSharpLSPAdapter.create("/some/project")

    _, kwargs = mock_config_class.call_args
    assert kwargs["code_language"] is FakeLanguage.CSHARP

    _, ls_kwargs = fake_csharp_ls.CSharpLanguageServer.call_args
    assert ls_kwargs["repository_root_path"] == "/some/project"
