from unittest.mock import MagicMock
from synapse.graph.edges import (
    upsert_contains, upsert_calls, upsert_inherits,
    upsert_implements, upsert_overrides, upsert_references,
)


def _conn() -> MagicMock:
    return MagicMock()


def test_upsert_contains_uses_path_for_file_source() -> None:
    conn = _conn()
    upsert_contains(conn, from_path="/proj/Foo.cs", to_full_name="MyNs.MyClass")
    cypher, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert "CONTAINS" in cypher
    assert params["from_id"] == "/proj/Foo.cs"


def test_upsert_calls_uses_full_names() -> None:
    conn = _conn()
    upsert_calls(conn, "MyNs.A.Do()", "MyNs.B.Run()")
    cypher, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert "CALLS" in cypher
    assert params["caller"] == "MyNs.A.Do()"
    assert params["callee"] == "MyNs.B.Run()"


def test_upsert_implements_creates_edge() -> None:
    conn = _conn()
    upsert_implements(conn, "MyNs.ConcreteClass", "MyNs.IService")
    cypher, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert "IMPLEMENTS" in cypher


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


def test_upsert_references_creates_edge() -> None:
    conn = _conn()
    upsert_references(conn, "MyNs.A.DoWork()", "MyNs.SomeType")
    cypher = conn.execute.call_args[0][0]
    assert "REFERENCES" in cypher
