"""Tests for upsert-based reindex_file (D-12: no delete-and-recreate)."""
from unittest.mock import MagicMock, patch, PropertyMock, call
import pytest
from synapse.indexer.indexer import Indexer
from synapse.lsp.interface import IndexSymbol, SymbolKind, LSPAdapter


def _make_parsed_file(file_path: str, source: str):
    """Create a mock ParsedFile for tests."""
    pf = MagicMock()
    pf.file_path = file_path
    pf.source = source
    pf.tree = MagicMock()
    return pf


def _make_plugin():
    plugin = MagicMock()
    plugin.name = "csharp"
    plugin.file_extensions = frozenset({".cs"})
    plugin.create_import_extractor.return_value = MagicMock()
    plugin.create_base_type_extractor.return_value = MagicMock(extract=MagicMock(return_value=[]))
    plugin.create_attribute_extractor = MagicMock(return_value=None)
    plugin.create_call_extractor = MagicMock(return_value=None)
    plugin.create_type_ref_extractor = MagicMock(return_value=None)
    plugin.create_assignment_extractor = MagicMock(return_value=None)
    plugin.parse_file = MagicMock(side_effect=lambda fp, src: _make_parsed_file(fp, src))
    return plugin


def _make_indexer(conn, plugin=None):
    lsp = MagicMock(spec=LSPAdapter)
    type(lsp).language_server = PropertyMock(return_value=MagicMock(repository_root_path="/proj"))
    if plugin is None:
        plugin = _make_plugin()
    return Indexer(conn, lsp, plugin), lsp


def _symbols():
    return [
        IndexSymbol(
            name="Foo", full_name="Ns.Foo", kind=SymbolKind.CLASS,
            file_path="/proj/Foo.cs", line=0, parent_full_name=None,
        ),
        IndexSymbol(
            name="DoWork", full_name="Ns.Foo.DoWork", kind=SymbolKind.METHOD,
            file_path="/proj/Foo.cs", line=5, parent_full_name="Ns.Foo",
        ),
    ]


@patch("synapse.indexer.indexer.delete_outgoing_edges_for_file")
@patch("synapse.indexer.indexer.delete_orphaned_symbols")
@patch("synapse.indexer.indexer.get_file_symbol_names", return_value={"Ns.Foo", "Ns.Foo.DoWork", "Ns.Foo.OldMethod"})
def test_reindex_does_not_call_delete_file_nodes(mock_get_syms, mock_del_orphans, mock_del_edges, tmp_path):
    """D-12: reindex_file must NOT call delete_file_nodes."""
    conn = MagicMock()
    conn.query.return_value = []
    indexer, lsp = _make_indexer(conn)
    lsp.get_document_symbols.return_value = _symbols()

    cs_file = tmp_path / "Foo.cs"
    cs_file.write_text("namespace Ns { class Foo { void DoWork() {} } }")

    with patch("synapse.indexer.indexer.delete_file_nodes") as mock_dfn, \
         patch("synapse.indexer.indexer.SymbolResolver") as MockResolver:
        MockResolver.return_value = MagicMock()
        indexer.reindex_file(str(cs_file), str(tmp_path))
        mock_dfn.assert_not_called()


@patch("synapse.indexer.indexer.delete_outgoing_edges_for_file")
@patch("synapse.indexer.indexer.delete_orphaned_symbols")
@patch("synapse.indexer.indexer.get_file_symbol_names", return_value={"Ns.Foo"})
def test_reindex_does_not_call_collect_or_restore_summaries(mock_get_syms, mock_del_orphans, mock_del_edges, tmp_path):
    """D-12: summaries survive because nodes are not deleted — no collect/restore needed."""
    conn = MagicMock()
    conn.query.return_value = []
    indexer, lsp = _make_indexer(conn)
    lsp.get_document_symbols.return_value = _symbols()

    cs_file = tmp_path / "Foo.cs"
    cs_file.write_text("namespace Ns { class Foo { void DoWork() {} } }")

    with patch("synapse.indexer.indexer.collect_summaries") as mock_cs, \
         patch("synapse.indexer.indexer.restore_summaries") as mock_rs, \
         patch("synapse.indexer.indexer.SymbolResolver") as MockResolver:
        MockResolver.return_value = MagicMock()
        indexer.reindex_file(str(cs_file), str(tmp_path))
        mock_cs.assert_not_called()
        mock_rs.assert_not_called()


@patch("synapse.indexer.indexer.delete_outgoing_edges_for_file")
@patch("synapse.indexer.indexer.delete_orphaned_symbols")
@patch("synapse.indexer.indexer.get_file_symbol_names", return_value={"Ns.Foo", "Ns.Foo.OldMethod"})
def test_reindex_calls_get_file_symbol_names_before_upsert(mock_get_syms, mock_del_orphans, mock_del_edges, tmp_path):
    """get_file_symbol_names is called to capture old symbols before upserting new ones."""
    conn = MagicMock()
    conn.query.return_value = []
    indexer, lsp = _make_indexer(conn)
    lsp.get_document_symbols.return_value = _symbols()

    cs_file = tmp_path / "Foo.cs"
    cs_file.write_text("namespace Ns { class Foo { void DoWork() {} } }")

    with patch("synapse.indexer.indexer.SymbolResolver") as MockResolver:
        MockResolver.return_value = MagicMock()
        indexer.reindex_file(str(cs_file), str(tmp_path))

    mock_get_syms.assert_called_once_with(conn, str(cs_file))


@patch("synapse.indexer.indexer.delete_outgoing_edges_for_file")
@patch("synapse.indexer.indexer.delete_orphaned_symbols")
@patch("synapse.indexer.indexer.get_file_symbol_names", return_value={"Ns.Foo", "Ns.Foo.OldMethod"})
def test_reindex_calls_delete_orphaned_symbols_after_upsert(mock_get_syms, mock_del_orphans, mock_del_edges, tmp_path):
    """delete_orphaned_symbols is called with new symbol full_names after structure upsert."""
    conn = MagicMock()
    conn.query.return_value = []
    indexer, lsp = _make_indexer(conn)
    syms = _symbols()
    lsp.get_document_symbols.return_value = syms

    cs_file = tmp_path / "Foo.cs"
    cs_file.write_text("namespace Ns { class Foo { void DoWork() {} } }")

    with patch("synapse.indexer.indexer.SymbolResolver") as MockResolver:
        MockResolver.return_value = MagicMock()
        indexer.reindex_file(str(cs_file), str(tmp_path))

    mock_del_orphans.assert_called_once()
    args = mock_del_orphans.call_args[0]
    assert args[0] is conn
    assert args[1] == str(cs_file)
    assert args[2] == {s.full_name for s in syms}


@patch("synapse.indexer.indexer.delete_outgoing_edges_for_file")
@patch("synapse.indexer.indexer.delete_orphaned_symbols")
@patch("synapse.indexer.indexer.get_file_symbol_names", return_value=set())
def test_reindex_calls_delete_outgoing_edges_before_resolve(mock_get_syms, mock_del_orphans, mock_del_edges, tmp_path):
    """D-11: delete_outgoing_edges_for_file is called before _resolve_calls_and_refs."""
    conn = MagicMock()
    conn.query.return_value = []
    indexer, lsp = _make_indexer(conn)
    lsp.get_document_symbols.return_value = _symbols()

    cs_file = tmp_path / "Foo.cs"
    cs_file.write_text("namespace Ns { class Foo { void DoWork() {} } }")

    call_order = []
    mock_del_edges.side_effect = lambda *a, **kw: call_order.append("delete_edges")

    with patch("synapse.indexer.indexer.SymbolResolver") as MockResolver:
        mock_instance = MagicMock()
        MockResolver.return_value = mock_instance
        mock_instance.resolve_single_file.side_effect = lambda *a, **kw: call_order.append("resolve")
        indexer.reindex_file(str(cs_file), str(tmp_path))

    mock_del_edges.assert_called_once_with(conn, str(cs_file))
    assert call_order.index("delete_edges") < call_order.index("resolve")


@patch("synapse.indexer.indexer.delete_outgoing_edges_for_file")
@patch("synapse.indexer.indexer.delete_orphaned_symbols")
@patch("synapse.indexer.indexer.get_file_symbol_names", return_value=set())
def test_delete_file_still_uses_delete_file_nodes(mock_get_syms, mock_del_orphans, mock_del_edges):
    """delete_file method must still use delete_file_nodes for actual file deletion."""
    conn = MagicMock()
    indexer, _ = _make_indexer(conn)

    with patch("synapse.indexer.indexer.delete_file_nodes") as mock_dfn:
        indexer.delete_file("/proj/Gone.cs")
        mock_dfn.assert_called_once_with(conn, "/proj/Gone.cs")
