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


def test_find_overridden_method_non_override_returns_none() -> None:
    from synapse.lsp.csharp import CSharpLSPAdapter
    from synapse.lsp.interface import IndexSymbol, SymbolKind

    adapter = CSharpLSPAdapter(MagicMock())
    symbol = IndexSymbol(
        name="DoWork", full_name="MyNs.MyClass.DoWork", kind=SymbolKind.METHOD,
        file_path="/proj/Foo.cs", line=10, signature="public void DoWork()",
    )
    assert adapter.find_overridden_method(symbol) is None


def test_find_overridden_method_returns_base_full_name() -> None:
    from synapse.lsp.csharp import CSharpLSPAdapter
    from synapse.lsp.interface import IndexSymbol, SymbolKind

    mock_ls = MagicMock()
    mock_ls.repository_root_path = "/proj"

    # request_containing_symbol → containing class
    class_sym = {
        "name": "MyClass", "kind": 5,
        "location": {
            "uri": "file:///proj/Foo.cs",
            "range": {"start": {"line": 5, "character": 0}},
        },
    }
    mock_ls.request_containing_symbol.return_value = class_sym

    # prepare_type_hierarchy → one hierarchy item
    hier_item = {"name": "MyClass", "uri": "file:///proj/Foo.cs", "range": {"start": {"line": 5, "character": 0}}}
    mock_ls.server.send.prepare_type_hierarchy.return_value = [hier_item]

    # type_hierarchy_supertypes → one parent type
    parent_type = {"name": "BaseClass", "uri": "file:///proj/Base.cs", "range": {"start": {"line": 1, "character": 0}}}
    mock_ls.server.send.type_hierarchy_supertypes.return_value = [parent_type]

    # request_document_symbols → doc with matching method
    ns_sym = {"name": "MyNs", "kind": 3, "parent": None}
    base_class_sym = {"name": "BaseClass", "kind": 5, "parent": ns_sym}
    base_method_sym = {"name": "DoWork", "kind": 6, "parent": base_class_sym}
    mock_doc = MagicMock()
    mock_doc.iter_symbols.return_value = [base_method_sym]
    mock_ls.request_document_symbols.return_value = mock_doc

    adapter = CSharpLSPAdapter(mock_ls)
    symbol = IndexSymbol(
        name="DoWork", full_name="MyNs.MyClass.DoWork", kind=SymbolKind.METHOD,
        file_path="/proj/Foo.cs", line=10, signature="public override void DoWork()",
    )

    result = adapter.find_overridden_method(symbol)
    assert result == "MyNs.BaseClass.DoWork"


def test_find_overridden_method_exception_returns_none() -> None:
    from synapse.lsp.csharp import CSharpLSPAdapter
    from synapse.lsp.interface import IndexSymbol, SymbolKind

    mock_ls = MagicMock()
    mock_ls.repository_root_path = "/proj"
    mock_ls.request_containing_symbol.side_effect = RuntimeError("LSP error")

    adapter = CSharpLSPAdapter(mock_ls)
    symbol = IndexSymbol(
        name="DoWork", full_name="MyNs.MyClass.DoWork", kind=SymbolKind.METHOD,
        file_path="/proj/Foo.cs", line=10, signature="public override void DoWork()",
    )
    assert adapter.find_overridden_method(symbol) is None
