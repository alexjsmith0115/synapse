from unittest.mock import MagicMock
from synapse.graph.edges import (
    upsert_dir_contains, upsert_file_contains_symbol, upsert_contains_symbol,
    upsert_calls, upsert_inherits, upsert_implements, upsert_overrides,
    upsert_interface_inherits, upsert_references,
)


def _conn() -> MagicMock:
    return MagicMock()


def test_upsert_dir_contains_matches_both_nodes_by_path() -> None:
    conn = MagicMock()
    upsert_dir_contains(conn, "/proj", "/proj/src")
    cypher, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert "CONTAINS" in cypher
    assert params["parent"] == "/proj"
    assert params["child"] == "/proj/src"


def test_upsert_file_contains_symbol_matches_file_by_path() -> None:
    conn = MagicMock()
    upsert_file_contains_symbol(conn, "/proj/Foo.cs", "MyNs.MyClass")
    cypher, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert "CONTAINS" in cypher
    assert params["file"] == "/proj/Foo.cs"
    assert params["sym"] == "MyNs.MyClass"


def test_upsert_contains_symbol_matches_both_by_full_name() -> None:
    conn = MagicMock()
    upsert_contains_symbol(conn, "MyNs.MyClass", "MyNs.MyClass.DoWork()")
    cypher, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert "CONTAINS" in cypher
    assert params["from_id"] == "MyNs.MyClass"
    assert params["to_id"] == "MyNs.MyClass.DoWork()"


def test_upsert_calls_uses_full_names() -> None:
    conn = _conn()
    upsert_calls(conn, "MyNs.A.Do()", "MyNs.B.Run()")
    cypher, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert "CALLS" in cypher
    assert params["caller"] == "MyNs.A.Do()"
    assert params["callee"] == "MyNs.B.Run()"


def test_upsert_implements_targets_interface_label() -> None:
    conn = MagicMock()
    upsert_implements(conn, "MyNs.ConcreteClass", "MyNs.IService")
    cypher = conn.execute.call_args[0][0]
    assert "IMPLEMENTS" in cypher
    assert ":Interface" in cypher


def test_upsert_inherits_creates_edge() -> None:
    conn = _conn()
    upsert_inherits(conn, "MyNs.Child", "MyNs.Base")
    cypher = conn.execute.call_args[0][0]
    assert "INHERITS" in cypher


def test_upsert_overrides_creates_edge() -> None:
    conn = _conn()
    upsert_overrides(conn, "MyNs.Child.Run()", "MyNs.Base.Run()")
    cypher = conn.execute.call_args[0][0]
    assert "OVERRIDES" in cypher


def test_upsert_interface_inherits_creates_edge() -> None:
    conn = MagicMock()
    upsert_interface_inherits(conn, "MyNs.IChild", "MyNs.IParent")
    cypher = conn.execute.call_args[0][0]
    assert "INHERITS" in cypher
    assert ":Interface" in cypher


def test_upsert_references_creates_edge_with_kind():
    conn = MagicMock()
    upsert_references(conn, "Ns.C.M()", "Ns.UserDto", "parameter")
    cypher, params = conn.execute.call_args[0]
    assert "REFERENCES" in cypher
    assert params["source"] == "Ns.C.M()"
    assert params["target"] == "Ns.UserDto"
    assert params["kind"] == "parameter"
