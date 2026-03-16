import json
from unittest.mock import MagicMock
from synapse.graph.nodes import (
    upsert_repository, upsert_directory, upsert_file,
    upsert_package, upsert_interface, upsert_class, upsert_method,
    upsert_property, upsert_field, delete_file_nodes,
    set_summary, remove_summary, collect_summaries, restore_summaries,
    set_attributes,
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


def test_upsert_method_includes_end_line() -> None:
    conn = _conn()
    upsert_method(conn, "Ns.C.M()", "M", "void M()", is_abstract=False, is_static=False, line=5, end_line=15)
    _, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert params["end_line"] == 15


def test_upsert_class_includes_end_line() -> None:
    conn = _conn()
    upsert_class(conn, "Ns.C", "C", "class", end_line=50)
    _, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert params["end_line"] == 50


def test_upsert_interface_includes_end_line() -> None:
    conn = _conn()
    upsert_interface(conn, "Ns.I", "I", end_line=30)
    _, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert params["end_line"] == 30


def test_upsert_property_includes_end_line() -> None:
    conn = _conn()
    upsert_property(conn, "Ns.C.P", "P", "string", end_line=12)
    _, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert params["end_line"] == 12


def test_upsert_field_includes_end_line() -> None:
    conn = _conn()
    upsert_field(conn, "Ns.C._f", "_f", "int", end_line=8)
    _, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert params["end_line"] == 8


def test_upsert_class_stores_file_path() -> None:
    conn = MagicMock()
    upsert_class(conn, "Ns.MyClass", "MyClass", "class", file_path="/proj/MyClass.cs", line=1, end_line=20)
    cypher, params = conn.execute.call_args[0]
    assert "file_path" in cypher
    assert params["file_path"] == "/proj/MyClass.cs"


def test_upsert_interface_stores_file_path() -> None:
    conn = MagicMock()
    upsert_interface(conn, "Ns.IFoo", "IFoo", file_path="/proj/IFoo.cs", line=1, end_line=10)
    cypher, params = conn.execute.call_args[0]
    assert "file_path" in cypher
    assert params["file_path"] == "/proj/IFoo.cs"


def test_upsert_method_stores_file_path() -> None:
    conn = MagicMock()
    upsert_method(conn, "Ns.C.M()", "M", "void M()", False, False,
                  file_path="/proj/C.cs", line=5, end_line=10)
    cypher, params = conn.execute.call_args[0]
    assert "file_path" in cypher
    assert params["file_path"] == "/proj/C.cs"


def test_upsert_repository_strips_trailing_slash() -> None:
    """Paths with and without trailing slash must produce the same node."""
    from synapse.graph.nodes import upsert_repository
    conn = MagicMock()
    upsert_repository(conn, "/Users/alex/Dev/myrepo/", "csharp")
    _, params = conn.execute.call_args[0]
    assert not params["path"].endswith("/"), (
        "Trailing slash must be stripped to prevent duplicate Repository nodes"
    )
    assert params["path"] == "/Users/alex/Dev/myrepo"


def test_upsert_interface_sets_kind_property() -> None:
    """Interface nodes must carry kind='interface' for consistent property access."""
    conn = _conn()
    upsert_interface(conn, "Ns.IFoo", "IFoo")
    cypher = conn.execute.call_args[0][0]
    assert "n.kind = 'interface'" in cypher, "upsert_interface must set n.kind = 'interface' in the SET clause"


def test_collect_summaries_queries_summarized_nodes_under_file() -> None:
    conn = _conn()
    conn.query.return_value = [
        ("MyNs.MyClass", "Class summary", "2026-03-16T00:00:00+00:00"),
        ("MyNs.MyClass.DoWork", "Method summary", "2026-03-16T00:00:00+00:00"),
    ]
    result = collect_summaries(conn, "/proj/Foo.cs")
    cypher = conn.query.call_args[0][0]
    params = conn.query.call_args[0][1]
    assert "Summarized" in cypher
    assert "CONTAINS" in cypher
    assert params["path"] == "/proj/Foo.cs"
    assert len(result) == 2
    assert result[0] == {
        "full_name": "MyNs.MyClass",
        "summary": "Class summary",
        "summary_updated_at": "2026-03-16T00:00:00+00:00",
    }


def test_restore_summaries_reapplies_label_and_properties() -> None:
    conn = _conn()
    summaries = [
        {"full_name": "MyNs.MyClass", "summary": "Class summary", "summary_updated_at": "2026-03-16T00:00:00+00:00"},
    ]
    restore_summaries(conn, summaries)
    cypher = conn.execute.call_args[0][0]
    params = conn.execute.call_args[0][1]
    assert "Summarized" in cypher
    assert "SET" in cypher
    assert params["full_name"] == "MyNs.MyClass"
    assert params["content"] == "Class summary"
    assert params["ts"] == "2026-03-16T00:00:00+00:00"


def test_restore_summaries_skips_empty_list() -> None:
    conn = _conn()
    restore_summaries(conn, [])
    conn.execute.assert_not_called()


def test_set_attributes_stores_json_list() -> None:
    conn = _conn()
    set_attributes(conn, "Ns.MyController", ["ApiController", "Route"])
    conn.execute.assert_called_once()
    cypher, params = conn.execute.call_args[0]
    assert "SET n.attributes" in cypher
    assert params["attrs"] == json.dumps(["ApiController", "Route"])
    assert params["full_name"] == "Ns.MyController"


def test_set_attributes_empty_list() -> None:
    conn = _conn()
    set_attributes(conn, "Ns.Plain", [])
    _, params = conn.execute.call_args[0]
    assert params["attrs"] == "[]"


def test_set_attributes_uses_match_not_merge() -> None:
    conn = _conn()
    set_attributes(conn, "Ns.Foo", ["Bar"])
    cypher = conn.execute.call_args[0][0]
    assert "MATCH" in cypher
    assert "MERGE" not in cypher
