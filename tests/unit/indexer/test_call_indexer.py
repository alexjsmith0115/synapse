from unittest.mock import MagicMock, patch
from synapse.indexer.call_indexer import CallIndexer


def _make_ls(root: str = "/proj") -> MagicMock:
    ls = MagicMock()
    ls.repository_root_path = root
    return ls


def test_writes_calls_edge_when_lsp_resolves_callee():
    conn = MagicMock()
    ls = _make_ls()

    callee_sym = {
        "name": "Helper", "kind": 6,
        "parent": {
            "name": "MyClass", "kind": 5,
            "parent": {"name": "MyNs", "kind": 3, "parent": None}
        }
    }
    ls.request_defining_symbol.return_value = callee_sym

    extractor = MagicMock()
    extractor.extract.return_value = [("MyNs.MyClass.Caller", "Helper", 5, 12)]

    indexer = CallIndexer(conn, ls, extractor=extractor)
    indexer._index_file("/proj/Foo.cs", "namespace X{}", {("/proj/Foo.cs", 3): "MyNs.MyClass.Caller"})

    conn.execute.assert_called_once()
    call_args = conn.execute.call_args
    assert "CALLS" in call_args[0][0]
    assert call_args[0][1]["caller"] == "MyNs.MyClass.Caller"
    assert call_args[0][1]["callee"] == "MyNs.MyClass.Helper"


def test_skips_edge_when_lsp_returns_none():
    conn = MagicMock()
    ls = _make_ls()
    ls.request_defining_symbol.return_value = None

    extractor = MagicMock()
    extractor.extract.return_value = [("MyNs.MyClass.Caller", "Unknown", 5, 12)]

    indexer = CallIndexer(conn, ls, extractor=extractor)
    indexer._index_file("/proj/Foo.cs", "namespace X{}", {("/proj/Foo.cs", 3): "MyNs.MyClass.Caller"})

    conn.execute.assert_not_called()


def test_skips_edge_when_callee_is_not_a_method():
    conn = MagicMock()
    ls = _make_ls()

    class_sym = {"name": "MyClass", "kind": 5, "parent": None}
    ls.request_defining_symbol.return_value = class_sym

    extractor = MagicMock()
    extractor.extract.return_value = [("MyNs.MyClass.Caller", "MyClass", 5, 12)]

    indexer = CallIndexer(conn, ls, extractor=extractor)
    indexer._index_file("/proj/Foo.cs", "namespace X{}", {("/proj/Foo.cs", 3): "MyNs.MyClass.Caller"})

    conn.execute.assert_not_called()


def test_index_calls_reads_all_cs_files(tmp_path):
    (tmp_path / "A.cs").write_text("namespace X { class A { void M() {} } }")
    (tmp_path / "B.cs").write_text("namespace X { class B { void N() {} } }")

    conn = MagicMock()
    ls = _make_ls(str(tmp_path))
    ls.request_defining_symbol.return_value = None

    extractor = MagicMock()
    extractor.extract.return_value = []

    indexer = CallIndexer(conn, ls, extractor=extractor)
    indexer.index_calls(str(tmp_path), {})

    assert extractor.extract.call_count == 2


def test_skips_self_calls():
    """A method calling itself should not produce a CALLS edge."""
    conn = MagicMock()
    ls = _make_ls()

    self_sym = {
        "name": "Caller", "kind": 6,
        "parent": {"name": "MyClass", "kind": 5, "parent": {"name": "MyNs", "kind": 3, "parent": None}}
    }
    ls.request_defining_symbol.return_value = self_sym

    extractor = MagicMock()
    extractor.extract.return_value = [("MyNs.MyClass.Caller", "Caller", 5, 12)]

    indexer = CallIndexer(conn, ls, extractor=extractor)
    indexer._index_file("/proj/Foo.cs", "namespace X{}", {("/proj/Foo.cs", 3): "MyNs.MyClass.Caller"})

    conn.execute.assert_not_called()
