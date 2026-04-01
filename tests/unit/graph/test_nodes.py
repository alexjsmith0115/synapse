import json
from unittest.mock import MagicMock
from synapps.graph.nodes import (
    upsert_repository, upsert_directory, upsert_file,
    upsert_package, upsert_interface, upsert_class, upsert_method,
    upsert_property, upsert_field, delete_file_nodes,
    set_summary, remove_summary, collect_summaries, restore_summaries,
    set_attributes, set_metadata_flags,
)
from synapps.lsp.interface import IndexSymbol, SymbolKind


def _conn() -> MagicMock:
    return MagicMock()


def test_upsert_repository_calls_merge() -> None:
    conn = _conn()
    upsert_repository(conn, "/proj", "csharp")
    cypher, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert "Repository" in cypher
    assert params["path"] == "/proj"
    assert params["language"] == "csharp"
    assert "languages" in cypher


def test_upsert_repository_uses_languages_list() -> None:
    """upsert_repository must write a 'languages' list, not a singular 'language' string."""
    conn = _conn()
    upsert_repository(conn, "/proj", "csharp")
    cypher = conn.execute.call_args[0][0]
    assert "languages" in cypher, "Must use 'languages' (list), not 'language' (string)"
    assert "REMOVE n.language" in cypher, "Must clean up old singular 'language' property"


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
    from synapps.graph.nodes import upsert_repository
    conn = MagicMock()
    upsert_repository(conn, "/Users/alex/Dev/myrepo/", "csharp")
    _, params = conn.execute.call_args[0]
    assert not params["path"].endswith("/"), (
        "Trailing slash must be stripped to prevent duplicate Repository nodes"
    )
    assert params["path"] == "/Users/alex/Dev/myrepo"


def test_upsert_repository_sets_name() -> None:
    """upsert_repository must set n.name to the basename of the path."""
    conn = MagicMock()
    upsert_repository(conn, "/Users/alex/Dev/myrepo", "csharp")
    cypher, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert "n.name" in cypher, "Cypher must contain 'n.name'"
    assert params["name"] == "myrepo", f"Expected name='myrepo', got: {params.get('name')}"


def test_upsert_repository_sets_name_after_strip() -> None:
    """upsert_repository with trailing slash must still set correct basename."""
    conn = MagicMock()
    upsert_repository(conn, "/Users/alex/Dev/myrepo/", "csharp")
    cypher, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert "n.name" in cypher, "Cypher must contain 'n.name'"
    assert params["name"] == "myrepo", (
        f"Trailing slash must be stripped before computing basename; got: {params.get('name')}"
    )


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


# --- language parameter tests ---

def test_upsert_class_language_param_sets_node_language() -> None:
    conn = _conn()
    upsert_class(conn, "MyNs.MyClass", "MyClass", "class", language="python")
    cypher, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert "n.language = $language" in cypher
    assert params["language"] == "python"


def test_upsert_method_language_param_sets_node_language() -> None:
    conn = _conn()
    upsert_method(conn, "MyNs.MyClass.MyMethod()", "MyMethod", "void MyMethod()", False, False, language="python")
    cypher, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert "n.language = $language" in cypher
    assert params["language"] == "python"


def test_upsert_property_language_param_sets_node_language() -> None:
    conn = _conn()
    upsert_property(conn, "MyNs.MyClass.Prop", "Prop", "str", language="python")
    cypher, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert "n.language = $language" in cypher
    assert params["language"] == "python"


def test_upsert_field_language_param_sets_node_language() -> None:
    conn = _conn()
    upsert_field(conn, "MyNs.MyClass._field", "_field", "int", language="python")
    cypher, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert "n.language = $language" in cypher
    assert params["language"] == "python"


def test_upsert_interface_language_param_sets_node_language() -> None:
    conn = _conn()
    upsert_interface(conn, "MyNs.IAnimal", "IAnimal", language="python")
    cypher, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert "n.language = $language" in cypher
    assert params["language"] == "python"


def test_upsert_functions_default_language_to_empty_string() -> None:
    conn = _conn()
    upsert_class(conn, "MyNs.MyClass", "MyClass", "class")
    _, params = conn.execute.call_args[0][0], conn.execute.call_args[0][1]
    assert params["language"] == ""

    conn2 = _conn()
    upsert_method(conn2, "MyNs.MyClass.MyMethod()", "MyMethod", "void MyMethod()", False, False)
    _, params2 = conn2.execute.call_args[0][0], conn2.execute.call_args[0][1]
    assert params2["language"] == ""

    conn3 = _conn()
    upsert_property(conn3, "MyNs.MyClass.Prop", "Prop", "str")
    _, params3 = conn3.execute.call_args[0][0], conn3.execute.call_args[0][1]
    assert params3["language"] == ""

    conn4 = _conn()
    upsert_field(conn4, "MyNs.MyClass._field", "_field", "int")
    _, params4 = conn4.execute.call_args[0][0], conn4.execute.call_args[0][1]
    assert params4["language"] == ""

    conn5 = _conn()
    upsert_interface(conn5, "MyNs.IAnimal", "IAnimal")
    _, params5 = conn5.execute.call_args[0][0], conn5.execute.call_args[0][1]
    assert params5["language"] == ""


# --- set_metadata_flags tests ---

def test_set_metadata_flags_writes_whitelisted_flags() -> None:
    conn = _conn()
    set_metadata_flags(conn, "Ns.C.M()", {"is_abstract": True, "is_static": False})
    conn.execute.assert_called_once()
    cypher, params = conn.execute.call_args[0]
    assert "MATCH" in cypher
    assert "n.is_abstract" in cypher
    assert "n.is_static" in cypher
    assert params["full_name"] == "Ns.C.M()"
    assert params["is_abstract"] is True
    assert params["is_static"] is False


def test_set_metadata_flags_ignores_non_whitelisted_keys() -> None:
    conn = _conn()
    set_metadata_flags(conn, "Ns.C.M()", {"is_abstract": True, "dangerous": True})
    conn.execute.assert_called_once()
    cypher, params = conn.execute.call_args[0]
    assert "dangerous" not in cypher
    assert "dangerous" not in params
    assert "is_abstract" in cypher


def test_set_metadata_flags_noop_on_empty_dict() -> None:
    conn = _conn()
    set_metadata_flags(conn, "Ns.C.M()", {})
    conn.execute.assert_not_called()


def test_set_metadata_flags_noop_when_all_keys_non_whitelisted() -> None:
    conn = _conn()
    set_metadata_flags(conn, "Ns.C.M()", {"foo": True, "bar": False})
    conn.execute.assert_not_called()


def test_set_metadata_flags_classmethod_and_async() -> None:
    conn = _conn()
    set_metadata_flags(conn, "Ns.C.M()", {"is_classmethod": True, "is_async": True})
    conn.execute.assert_called_once()
    cypher, params = conn.execute.call_args[0]
    assert "n.is_classmethod" in cypher
    assert "n.is_async" in cypher
    assert params["is_classmethod"] is True
    assert params["is_async"] is True


# --- upsert_method with is_classmethod and is_async ---

def test_upsert_method_accepts_is_classmethod_and_is_async() -> None:
    conn = _conn()
    upsert_method(
        conn, "Ns.C.from_name()", "from_name", "classmethod from_name(cls)",
        is_abstract=False, is_static=False, is_classmethod=True, is_async=False,
    )
    cypher, params = conn.execute.call_args[0]
    assert "n.is_classmethod" in cypher
    assert params["is_classmethod"] is True
    assert params["is_async"] is False


def test_upsert_method_defaults_is_classmethod_and_is_async_to_false() -> None:
    conn = _conn()
    upsert_method(conn, "Ns.C.M()", "M", "void M()", False, False)
    _, params = conn.execute.call_args[0]
    assert params["is_classmethod"] is False
    assert params["is_async"] is False


# --- IndexSymbol with is_classmethod and is_async ---

def test_index_symbol_accepts_is_classmethod_and_is_async() -> None:
    sym = IndexSymbol(
        name="from_name",
        full_name="svc.AnimalService.from_name",
        kind=SymbolKind.METHOD,
        file_path="/proj/services.py",
        line=10,
        is_classmethod=True,
        is_async=False,
    )
    assert sym.is_classmethod is True
    assert sym.is_async is False


def test_index_symbol_defaults_is_classmethod_and_is_async_to_false() -> None:
    sym = IndexSymbol(
        name="speak",
        full_name="svc.Animal.speak",
        kind=SymbolKind.METHOD,
        file_path="/proj/animals.py",
        line=5,
    )
    assert sym.is_classmethod is False
    assert sym.is_async is False
