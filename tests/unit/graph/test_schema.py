from unittest.mock import MagicMock
from synapse.graph.schema import ensure_schema


def test_ensure_schema_memgraph_creates_indices() -> None:
    conn = MagicMock()
    conn.dialect = "memgraph"
    ensure_schema(conn)
    calls = [c[0][0] for c in conn.execute_implicit.call_args_list]
    # Memgraph syntax: CREATE INDEX ON :Label(prop)
    assert any("CREATE INDEX ON :File" in c for c in calls)
    assert any("CREATE INDEX ON :Class" in c for c in calls)
    assert any("CREATE INDEX ON :Method" in c for c in calls)


def test_ensure_schema_neo4j_creates_indices() -> None:
    conn = MagicMock()
    conn.dialect = "neo4j"
    ensure_schema(conn)
    calls = [c[0][0] for c in conn.execute_implicit.call_args_list]
    # Neo4j syntax: CREATE INDEX FOR (n:Label) ON (n.prop)
    assert any("CREATE INDEX FOR (n:File)" in c for c in calls)
    assert any("CREATE INDEX FOR (n:Class)" in c for c in calls)
    assert any("CREATE INDEX FOR (n:Method)" in c for c in calls)


def test_schema_includes_package_index() -> None:
    conn = MagicMock()
    conn.dialect = "memgraph"
    ensure_schema(conn)
    calls = [c[0][0] for c in conn.execute_implicit.call_args_list]
    assert any(":Package" in c for c in calls)


def test_schema_includes_interface_index() -> None:
    conn = MagicMock()
    conn.dialect = "memgraph"
    ensure_schema(conn)
    calls = [c[0][0] for c in conn.execute_implicit.call_args_list]
    assert any(":Interface" in c for c in calls)


def test_schema_does_not_include_namespace_index() -> None:
    conn = MagicMock()
    conn.dialect = "memgraph"
    ensure_schema(conn)
    calls = [c[0][0] for c in conn.execute_implicit.call_args_list]
    assert not any(":Namespace" in c for c in calls)


def test_schema_correct_number_of_indices() -> None:
    """One index per node type: Repository, Directory, File, Package,
    Class, Interface, Method, Property, Field = 9 total."""
    conn = MagicMock()
    conn.dialect = "memgraph"
    ensure_schema(conn)
    assert conn.execute_implicit.call_count == 9
