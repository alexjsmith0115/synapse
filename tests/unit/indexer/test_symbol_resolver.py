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


def test_resolver_writes_calls_edge_when_lsp_returns_class():
    """Roslyn often returns the containing class rather than the method for a call site.
    The resolver must fall back to matching method children by callee simple name."""
    conn = MagicMock()
    ls = _make_ls()

    method_child = {
        "name": "Helper", "kind": 6,
        "parent": {"name": "MyClass", "kind": 5, "parent": {"name": "MyNs", "kind": 3, "parent": None}},
    }
    # LSP returns the class, not the method
    class_sym = {"name": "MyClass", "kind": 5, "children": [method_child], "parent": None}
    ls.request_defining_symbol.return_value = class_sym

    call_extractor = MagicMock()
    call_extractor.extract.return_value = [("MyNs.MyClass.Caller", "Helper", 5, 12)]
    type_ref_extractor = MagicMock()
    type_ref_extractor.extract.return_value = []

    resolver = SymbolResolver(conn, ls, call_extractor=call_extractor, type_ref_extractor=type_ref_extractor)
    resolver._resolve_file("/proj/Foo.cs", "namespace X{}", {})

    assert any("CALLS" in str(c) for c in conn.execute.call_args_list)


def test_resolver_skips_call_when_lsp_returns_class_without_matching_child():
    conn = MagicMock()
    ls = _make_ls()

    # LSP returns a class whose children don't include the callee
    class_sym = {"name": "MyClass", "kind": 5, "children": [], "parent": None}
    ls.request_defining_symbol.return_value = class_sym

    call_extractor = MagicMock()
    call_extractor.extract.return_value = [("MyNs.MyClass.Caller", "Helper", 5, 12)]
    type_ref_extractor = MagicMock()
    type_ref_extractor.extract.return_value = []

    resolver = SymbolResolver(conn, ls, call_extractor=call_extractor, type_ref_extractor=type_ref_extractor)
    resolver._resolve_file("/proj/Foo.cs", "namespace X{}", {})

    assert not any("CALLS" in str(c) for c in conn.execute.call_args_list)


def test_resolver_writes_references_edge_via_name_map_fallback():
    """When LSP cannot resolve a type reference (returns None), the name map is used."""
    conn = MagicMock()
    ls = _make_ls()
    ls.request_defining_symbol.return_value = None

    from synapse.indexer.type_ref_extractor import TypeRef
    type_ref_extractor = MagicMock()
    type_ref_extractor.extract.return_value = [
        TypeRef(owner_full_name="Ns.TaskService", type_name="ITaskService", line=4, col=21, ref_kind="field_type")
    ]
    call_extractor = MagicMock()
    call_extractor.extract.return_value = []

    resolver = SymbolResolver(
        conn, ls,
        call_extractor=call_extractor,
        type_ref_extractor=type_ref_extractor,
        name_to_full_names={"ITaskService": ["Ns.ITaskService"]},
    )
    resolver._resolve_file("/proj/Foo.cs", "namespace X{}", {})

    assert any("REFERENCES" in str(c) for c in conn.execute.call_args_list)


def test_resolver_skips_references_when_name_map_ambiguous():
    """Ambiguous type names (multiple full_names) must not produce a REFERENCES edge."""
    conn = MagicMock()
    ls = _make_ls()
    ls.request_defining_symbol.return_value = None

    from synapse.indexer.type_ref_extractor import TypeRef
    type_ref_extractor = MagicMock()
    type_ref_extractor.extract.return_value = [
        TypeRef(owner_full_name="Ns.C", type_name="Item", line=3, col=10, ref_kind="field_type")
    ]
    call_extractor = MagicMock()
    call_extractor.extract.return_value = []

    resolver = SymbolResolver(
        conn, ls,
        call_extractor=call_extractor,
        type_ref_extractor=type_ref_extractor,
        name_to_full_names={"Item": ["Ns.A.Item", "Ns.B.Item"]},
    )
    resolver._resolve_file("/proj/Foo.cs", "namespace X{}", {})

    assert not any("REFERENCES" in str(c) for c in conn.execute.call_args_list)


def test_resolve_call_resolves_overloaded_callee_name() -> None:
    """If graph stores 'X.M(int)' but LSP returns 'X.M', the CALLS edge must use the stored overloaded name."""
    conn = MagicMock()
    # Graph has the overloaded full_name (one unambiguous match)
    conn.query.return_value = [["Ns.C.M(int)"]]

    ls = MagicMock()
    ls.repository_root_path = "/repo"
    ls.request_defining_symbol.return_value = {
        "name": "M",
        "kind": 6,
        "parent": {"name": "C", "parent": {"name": "Ns", "parent": None}},
        # No overload_idx — LSP gives plain name
    }

    resolver = SymbolResolver(conn, ls)
    resolver._resolve_call("Ns.C.Caller", "file.cs", 10, 5, "M")

    # Should have written CALLS edge using the resolved overloaded name, not the plain 'Ns.C.M'
    execute_calls = conn.execute.call_args_list
    assert execute_calls, "Expected conn.execute to be called for CALLS edge"
    # upsert_calls passes params as second positional arg: conn.execute(query, params)
    last_call_args = execute_calls[-1][0]
    assert len(last_call_args) >= 2, f"Expected (query, params) positional args, got: {last_call_args}"
    callee_used = last_call_args[1].get("callee")
    assert callee_used == "Ns.C.M(int)", (
        f"Expected overloaded name 'Ns.C.M(int)' to be used, but got: {callee_used!r}"
    )
