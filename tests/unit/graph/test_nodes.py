from unittest.mock import MagicMock
from synapse.graph.nodes import (
    upsert_repository, upsert_directory, upsert_file,
    upsert_package, upsert_interface, upsert_class, upsert_method,
    upsert_property, upsert_field, delete_file_nodes,
    set_summary, remove_summary,
)


def _conn() -> MagicMock:
    return MagicMock()


def test_upsert_repository_calls_merge() -> None:
    conn = _conn()
    upsert_repository(conn, "/proj", "csharp")
    cypher, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert "Repository" in cypher
    assert params["path"] == "/proj"
    assert params["language"] == "csharp"


def test_upsert_class_includes_kind() -> None:
    conn = _conn()
    upsert_class(conn, "MyNs.MyClass", "MyClass", "class")
    cypher, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert "Class" in cypher
    assert params["kind"] == "class"


def test_upsert_method_includes_flags() -> None:
    conn = _conn()
    upsert_method(conn, "MyNs.MyClass.MyMethod()", "MyMethod", "void MyMethod()", is_abstract=True, is_static=False)
    _, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert params["is_abstract"] is True
    assert params["is_static"] is False


def test_delete_file_nodes_uses_file_path() -> None:
    conn = _conn()
    delete_file_nodes(conn, "/proj/src/Foo.cs")
    first_call, second_call = conn.execute.call_args_list
    assert "CONTAINS" in first_call[0][0]   # children deleted first via path traversal
    assert first_call[0][1]["path"] == "/proj/src/Foo.cs"
    assert "File" in second_call[0][0]
    assert second_call[0][1]["path"] == "/proj/src/Foo.cs"


def test_set_summary_adds_summarized_label() -> None:
    conn = _conn()
    set_summary(conn, "MyNs.MyClass", "This class handles auth.")
    cypher, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert "Summarized" in cypher
    assert params["content"] == "This class handles auth."


def test_remove_summary_strips_label_and_properties() -> None:
    conn = _conn()
    remove_summary(conn, "MyNs.MyClass")
    cypher = conn.execute.call_args[0][0]
    assert "REMOVE" in cypher


def test_upsert_package_creates_package_node() -> None:
    conn = MagicMock()
    upsert_package(conn, "MyApp.Services", "Services")
    cypher, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert ":Package" in cypher
    assert params["full_name"] == "MyApp.Services"


def test_upsert_interface_creates_interface_node() -> None:
    conn = MagicMock()
    upsert_interface(conn, "MyApp.IService", "IService")
    cypher, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert ":Interface" in cypher
    assert params["full_name"] == "MyApp.IService"


def test_upsert_class_does_not_use_namespace_label() -> None:
    conn = MagicMock()
    upsert_class(conn, "MyApp.Foo", "Foo", "class")
    cypher = conn.execute.call_args[0][0]
    assert ":Namespace" not in cypher
