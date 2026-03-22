from __future__ import annotations

from unittest.mock import MagicMock

from synapse.graph.nodes import (
    set_last_indexed_commit,
    get_last_indexed_commit,
    rename_file_node,
    get_file_symbol_names,
    delete_orphaned_symbols,
)


def _conn() -> MagicMock:
    return MagicMock()


class TestSetLastIndexedCommit:
    def test_executes_match_set_with_sha(self) -> None:
        conn = _conn()
        set_last_indexed_commit(conn, "/proj", "abc123")
        conn.execute.assert_called_once()
        cypher, params = conn.execute.call_args[0]
        assert "Repository" in cypher
        assert "MATCH" in cypher
        assert "SET" in cypher
        assert "last_indexed_commit" in cypher
        assert params["path"] == "/proj"
        assert params["sha"] == "abc123"


class TestGetLastIndexedCommit:
    def test_returns_sha_when_present(self) -> None:
        conn = _conn()
        conn.query.return_value = [("abc123",)]
        result = get_last_indexed_commit(conn, "/proj")
        assert result == "abc123"
        cypher, params = conn.query.call_args[0]
        assert "Repository" in cypher
        assert "last_indexed_commit" in cypher
        assert params["path"] == "/proj"

    def test_returns_none_when_no_rows(self) -> None:
        conn = _conn()
        conn.query.return_value = []
        assert get_last_indexed_commit(conn, "/proj") is None

    def test_returns_none_when_sha_is_none(self) -> None:
        conn = _conn()
        conn.query.return_value = [(None,)]
        assert get_last_indexed_commit(conn, "/proj") is None


class TestRenameFileNode:
    def test_updates_file_path_name_and_child_symbols(self) -> None:
        conn = _conn()
        rename_file_node(conn, "/proj/old.py", "/proj/new.py")
        assert conn.execute.call_count == 2
        # First call: update File node
        cypher1, params1 = conn.execute.call_args_list[0][0]
        assert "File" in cypher1
        assert params1["old"] == "/proj/old.py"
        assert params1["new"] == "/proj/new.py"
        assert params1["name"] == "new.py"
        # Second call: update child symbols' file_path
        cypher2, params2 = conn.execute.call_args_list[1][0]
        assert "CONTAINS" in cypher2
        assert "file_path" in cypher2
        assert params2["old"] == "/proj/old.py"
        assert params2["new"] == "/proj/new.py"


class TestGetFileSymbolNames:
    def test_returns_set_of_full_names(self) -> None:
        conn = _conn()
        conn.query.return_value = [("Ns.Foo",), ("Ns.Foo.bar",)]
        result = get_file_symbol_names(conn, "/proj/foo.py")
        assert result == {"Ns.Foo", "Ns.Foo.bar"}
        cypher, params = conn.query.call_args[0]
        assert "CONTAINS" in cypher
        assert "full_name" in cypher
        assert params["path"] == "/proj/foo.py"

    def test_returns_empty_set_when_no_symbols(self) -> None:
        conn = _conn()
        conn.query.return_value = []
        assert get_file_symbol_names(conn, "/proj/empty.py") == set()


class TestDeleteOrphanedSymbols:
    def test_deletes_symbols_not_in_keep_set(self) -> None:
        conn = _conn()
        conn.query.return_value = [("Ns.Foo.old_method",)]
        count = delete_orphaned_symbols(conn, "/proj/foo.py", {"Ns.Foo", "Ns.Foo.new_method"})
        assert count == 1
        # Verify the query was called
        cypher, params = conn.query.call_args[0]
        assert "CONTAINS" in cypher
        assert "NOT" in cypher
        assert params["path"] == "/proj/foo.py"
        assert set(params["keep"]) == {"Ns.Foo", "Ns.Foo.new_method"}
        # Verify each orphan was detach-deleted
        conn.execute.assert_called_once()
        del_cypher, del_params = conn.execute.call_args[0]
        assert "DETACH DELETE" in del_cypher
        assert del_params["fn"] == "Ns.Foo.old_method"

    def test_returns_zero_when_no_orphans(self) -> None:
        conn = _conn()
        conn.query.return_value = []
        count = delete_orphaned_symbols(conn, "/proj/foo.py", {"Ns.Foo"})
        assert count == 0
        conn.execute.assert_not_called()
