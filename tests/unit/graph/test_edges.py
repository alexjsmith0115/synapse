from unittest.mock import MagicMock
from synapse.graph.edges import (
    upsert_repo_contains_dir, upsert_dir_contains, upsert_file_contains_symbol,
    upsert_contains_symbol, upsert_calls, upsert_inherits, upsert_implements,
    upsert_overrides, upsert_interface_inherits, upsert_references,
    upsert_method_implements,
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


def test_upsert_implements_accepts_class_or_interface_label() -> None:
    """Must accept interface nodes stored as :Class (Roslyn fallback) as well as :Interface."""
    conn = MagicMock()
    upsert_implements(conn, "MyNs.ConcreteClass", "MyNs.IService")
    cypher = conn.execute.call_args[0][0]
    assert "IMPLEMENTS" in cypher
    # Query must tolerate dst being either :Interface or :Class — not require :Interface exclusively
    assert "dst:Interface OR dst:Class" in cypher or "dst:Class OR dst:Interface" in cypher


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


def test_upsert_method_implements_writes_implements_edge() -> None:
    conn = MagicMock()
    upsert_method_implements(conn, "Ns.Impl.CreateAsync", "Ns.IFoo.CreateAsync")
    implements_cypher, implements_params = conn.execute.call_args_list[0][0]
    assert "IMPLEMENTS" in implements_cypher
    assert implements_params["impl"] == "Ns.Impl.CreateAsync"
    assert implements_params["iface"] == "Ns.IFoo.CreateAsync"


def test_upsert_method_implements_writes_dispatches_to_edge() -> None:
    conn = MagicMock()
    upsert_method_implements(conn, "Ns.Impl.CreateAsync", "Ns.IFoo.CreateAsync")
    dispatches_cypher, dispatches_params = conn.execute.call_args_list[1][0]
    assert "DISPATCHES_TO" in dispatches_cypher
    # Direction is iface → impl
    assert dispatches_params["iface"] == "Ns.IFoo.CreateAsync"
    assert dispatches_params["impl"] == "Ns.Impl.CreateAsync"


def test_upsert_repo_contains_dir_matches_repo_by_path() -> None:
    conn = MagicMock()
    upsert_repo_contains_dir(conn, "/proj", "/proj")
    cypher, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert "Repository" in cypher
    assert "CONTAINS" in cypher
    assert params["repo"] == "/proj"
    assert params["dir"] == "/proj"
