from unittest.mock import MagicMock, patch
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


from synapse.lsp.csharp import _build_full_name


def test_build_full_name_root_symbol() -> None:
    raw = {"name": "MyNamespace", "kind": 3}
    assert _build_full_name(raw) == "MyNamespace"


def test_build_full_name_one_parent() -> None:
    parent = {"name": "MyNs", "kind": 3}
    raw = {"name": "MyClass", "kind": 5, "parent": parent}
    assert _build_full_name(raw) == "MyNs.MyClass"


def test_build_full_name_two_parents() -> None:
    grandparent = {"name": "MyNs", "kind": 3}
    parent = {"name": "MyClass", "kind": 5, "parent": grandparent}
    raw = {"name": "MyMethod", "kind": 6, "parent": parent}
    assert _build_full_name(raw) == "MyNs.MyClass.MyMethod"


def test_build_full_name_overload_appends_params() -> None:
    parent = {"name": "MyClass", "kind": 5}
    raw = {"name": "DoWork", "kind": 6, "parent": parent, "overload_idx": 1, "detail": "void DoWork(int x, string y)"}
    assert _build_full_name(raw) == "MyClass.DoWork(int x, string y)"


def test_build_full_name_overload_no_paren_in_detail() -> None:
    parent = {"name": "MyClass", "kind": 5}
    raw = {"name": "DoWork", "kind": 6, "parent": parent, "overload_idx": 0, "detail": "void DoWork"}
    assert _build_full_name(raw) == "MyClass.DoWork"


def test_convert_produces_qualified_full_name() -> None:
    from unittest.mock import MagicMock
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
