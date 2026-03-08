from unittest.mock import MagicMock, patch, call
from synapse.indexer.symbol_resolver import SymbolResolver


def _make_ls(root: str = "/proj") -> MagicMock:
    ls = MagicMock()
    ls.repository_root_path = root
    return ls


def test_resolver_walks_cs_files_and_calls_both_extractors(tmp_path):
    (tmp_path / "A.cs").write_text("namespace X { class A { void M() {} } }")

    conn = MagicMock()
    ls = _make_ls(str(tmp_path))
    ls.request_defining_symbol.return_value = None

    call_extractor = MagicMock()
    call_extractor.extract.return_value = []
    type_ref_extractor = MagicMock()
    type_ref_extractor.extract.return_value = []

    resolver = SymbolResolver(conn, ls, call_extractor=call_extractor, type_ref_extractor=type_ref_extractor)
    resolver.resolve(str(tmp_path), {})

    assert call_extractor.extract.call_count == 1
    assert type_ref_extractor.extract.call_count == 1


def test_resolver_opens_lsp_context_once_per_file(tmp_path):
    (tmp_path / "A.cs").write_text("namespace X { class A {} }")

    conn = MagicMock()
    ls = _make_ls(str(tmp_path))

    call_extractor = MagicMock()
    call_extractor.extract.return_value = [("Ns.C.M", "Helper", 1, 0)]
    type_ref_extractor = MagicMock()
    type_ref_extractor.extract.return_value = []

    resolver = SymbolResolver(conn, ls, call_extractor=call_extractor, type_ref_extractor=type_ref_extractor)
    resolver.resolve(str(tmp_path), {})

    ls.open_file.assert_called_once()


def test_resolver_writes_calls_edge():
    conn = MagicMock()
    ls = _make_ls()

    callee_sym = {
        "name": "Helper", "kind": 6,
        "parent": {"name": "MyClass", "kind": 5, "parent": {"name": "MyNs", "kind": 3, "parent": None}}
    }
    ls.request_defining_symbol.return_value = callee_sym

    call_extractor = MagicMock()
    call_extractor.extract.return_value = [("MyNs.MyClass.Caller", "Helper", 5, 12)]
    type_ref_extractor = MagicMock()
    type_ref_extractor.extract.return_value = []

    resolver = SymbolResolver(conn, ls, call_extractor=call_extractor, type_ref_extractor=type_ref_extractor)
    resolver._resolve_file("/proj/Foo.cs", "namespace X{}", {})

    assert any("CALLS" in str(c) for c in conn.execute.call_args_list)


def test_resolver_writes_references_edge():
    conn = MagicMock()
    ls = _make_ls()

    from synapse.indexer.type_ref_extractor import TypeRef
    type_ref_extractor = MagicMock()
    type_ref_extractor.extract.return_value = [
        TypeRef(owner_full_name="Ns.C.M", type_name="UserDto", line=5, col=15, ref_kind="parameter")
    ]

    type_sym = {
        "name": "UserDto", "kind": 5,
        "parent": {"name": "MyNs", "kind": 3, "parent": None}
    }
    ls.request_defining_symbol.return_value = type_sym

    call_extractor = MagicMock()
    call_extractor.extract.return_value = []

    resolver = SymbolResolver(conn, ls, call_extractor=call_extractor, type_ref_extractor=type_ref_extractor)
    resolver._resolve_file("/proj/Foo.cs", "namespace X{}", {})

    assert any("REFERENCES" in str(c) for c in conn.execute.call_args_list)
