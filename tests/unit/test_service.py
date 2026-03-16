from unittest.mock import MagicMock, patch

import pytest

from synapse.service import SynapseService, _p


class _MockNode:
    """Minimal neo4j graph.Node stand-in for unit tests."""
    def __init__(self, labels: list[str], props: dict, element_id: str | None = None) -> None:
        self._props = props
        self.labels = frozenset(labels)
        self.element_id = element_id or str(id(self))

    def keys(self): return list(self._props.keys())
    def values(self): return list(self._props.values())
    def items(self): return list(self._props.items())
    def __getitem__(self, key): return self._props[key]
    def __iter__(self): return iter(self._props)
    def __len__(self): return len(self._props)
    def get(self, key, default=None): return self._props.get(key, default)


def _node(labels: list[str], props: dict) -> _MockNode:
    return _MockNode(labels, props)


# After wiring _resolve into read methods, we need to bypass resolve_full_name
# in tests that don't care about resolution.
@pytest.fixture(autouse=True)
def bypass_resolve(monkeypatch):
    """Make resolve_full_name return the name unchanged for all service tests."""
    monkeypatch.setattr("synapse.service.resolve_full_name", lambda conn, name: name)


def _service() -> SynapseService:
    conn = MagicMock()
    return SynapseService(conn=conn)


def test_set_summary_delegates_to_nodes() -> None:
    svc = _service()
    with patch("synapse.service.set_summary") as mock_set:
        svc.set_summary("MyNs.MyClass", "Auth handler")
        mock_set.assert_called_once_with(svc._conn, "MyNs.MyClass", "Auth handler")



def test_watch_project_registers_watcher() -> None:
    svc = _service()
    mock_watcher_cls = MagicMock()
    mock_watcher = MagicMock()
    mock_watcher_cls.return_value = mock_watcher
    mock_lsp = MagicMock()
    mock_lsp.get_workspace_files.return_value = []

    with patch("synapse.service.FileWatcher", mock_watcher_cls):
        svc.watch_project("/proj", lsp_adapter=mock_lsp)
        mock_watcher.start.assert_called_once()
        assert "/proj" in svc._watchers


def test_unwatch_project_stops_watcher() -> None:
    svc = _service()
    mock_watcher = MagicMock()
    svc._watchers["/proj"] = mock_watcher

    svc.unwatch_project("/proj")

    mock_watcher.stop.assert_called_once()
    assert "/proj" not in svc._watchers


def test_get_symbol_source_reads_file_and_returns_lines(tmp_path):
    """Service reads the file from disk using line range from the graph."""
    source_file = tmp_path / "Foo.cs"
    source_file.write_text("line0\nline1\nline2\nline3\nline4\nline5\n")

    conn = MagicMock()
    svc = SynapseService(conn)

    with patch("synapse.service.get_symbol_source_info") as mock_query:
        mock_query.return_value = {"file_path": str(source_file), "line": 1, "end_line": 3}
        result = svc.get_symbol_source("Ns.C.M")

    assert "line1" in result
    assert "line2" in result
    assert "line3" in result
    assert "line0" not in result


def test_get_symbol_source_returns_none_when_symbol_not_found():
    conn = MagicMock()
    svc = SynapseService(conn)

    with patch("synapse.service.get_symbol_source_info") as mock_query:
        mock_query.return_value = None
        result = svc.get_symbol_source("Ns.Missing")

    assert result is None


def test_get_symbol_source_returns_error_when_end_line_missing(tmp_path):
    """When end_line is 0, the symbol was indexed before line ranges were added."""
    conn = MagicMock()
    svc = SynapseService(conn)

    with patch("synapse.service.get_symbol_source_info") as mock_query:
        mock_query.return_value = {"file_path": str(tmp_path / "F.cs"), "line": 5, "end_line": 0}
        result = svc.get_symbol_source("Ns.C.M")

    assert result is not None
    assert "re-index" in result.lower()


def test_get_context_for_method_includes_all_sections(tmp_path):
    source_file = tmp_path / "Foo.cs"
    source_file.write_text(
        "namespace Ns {\n"
        "    class MyClass : IFoo {\n"
        "        public UserDto GetUser(int id) {\n"
        "            return _repo.Find(id);\n"
        "        }\n"
        "    }\n"
        "}\n"
    )

    conn = MagicMock()
    svc = SynapseService(conn)

    with patch.multiple(
        "synapse.service",
        get_symbol=MagicMock(return_value={"full_name": "Ns.MyClass.GetUser", "name": "GetUser", "line": 2, "end_line": 4}),
        get_symbol_source_info=MagicMock(return_value={"file_path": str(source_file), "line": 2, "end_line": 4}),
        get_containing_type=MagicMock(return_value={"full_name": "Ns.MyClass", "name": "MyClass", "kind": "class", "line": 1, "end_line": 5}),
        get_members_overview=MagicMock(return_value=[
            {"full_name": "Ns.MyClass.GetUser", "name": "GetUser", "signature": "UserDto GetUser(int)"},
        ]),
        get_implemented_interfaces=MagicMock(return_value=[
            {"full_name": "Ns.IFoo", "name": "IFoo"},
        ]),
        find_callees=MagicMock(return_value=[
            {"full_name": "Ns.Repo.Find", "name": "Find", "signature": "User Find(int)"},
        ]),
        query_find_dependencies=MagicMock(return_value=[
            {"type": {"full_name": "Ns.UserDto", "name": "UserDto"}, "depth": 1},
        ]),
    ):
        result = svc.get_context_for("Ns.MyClass.GetUser")

    assert "## Target:" in result
    assert "## Containing Type:" in result
    assert "## Implemented Interfaces" in result
    assert "## Called Methods" in result
    assert "## Parameter & Return Types" in result


def test_get_context_for_returns_none_when_symbol_not_found():
    conn = MagicMock()
    svc = SynapseService(conn)

    with patch("synapse.service.get_symbol", return_value=None):
        result = svc.get_context_for("Ns.Missing")

    assert result is None


def test_p_extracts_properties_and_labels_from_neo4j_node():
    node = _node(["Method"], {"full_name": "A.B", "signature": "B() : void"})
    result = _p(node)
    assert result == {"full_name": "A.B", "signature": "B() : void", "_labels": ["Method"]}


def test_p_passes_through_plain_dict():
    d = {"full_name": "A.B"}
    assert _p(d) is d


def test_find_callers_returns_plain_dicts():
    svc = _service()
    node = _node(["Method"], {"full_name": "A.Caller", "signature": "Caller() : void"})
    with patch("synapse.service.find_callers", return_value=[node]):
        result = svc.find_callers("A.B")
    assert result == [{"full_name": "A.Caller", "signature": "Caller() : void", "_labels": ["Method"]}]


def test_find_implementations_returns_plain_dicts():
    svc = _service()
    node = _node(["Class"], {"full_name": "A.Impl"})
    with patch("synapse.service.find_implementations", return_value=[node]):
        result = svc.find_implementations("A.IService")
    assert result == [{"full_name": "A.Impl", "_labels": ["Class"]}]


def test_get_symbol_returns_plain_dict_with_labels():
    svc = _service()
    node = _node(["Class"], {"full_name": "A.Cls"})
    with patch("synapse.service.get_symbol", return_value=node):
        result = svc.get_symbol("A.Cls")
    assert result == {"full_name": "A.Cls", "_labels": ["Class"]}


def test_get_symbol_returns_none_when_not_found():
    svc = _service()
    with patch("synapse.service.get_symbol", return_value=None):
        result = svc.get_symbol("Missing")
    assert result is None


def test_find_type_references_unwraps_nested_nodes():
    svc = _service()
    node = _node(["Method"], {"full_name": "A.Caller"})
    with patch("synapse.service.query_find_type_references", return_value=[{"symbol": node, "kind": "parameter"}]):
        result = svc.find_type_references("A.IService")
    assert result == [{"symbol": {"full_name": "A.Caller", "_labels": ["Method"]}, "kind": "parameter"}]


def test_find_dependencies_unwraps_nested_nodes():
    svc = _service()
    node = _node(["Class"], {"full_name": "A.Dep"})
    with patch("synapse.service.query_find_dependencies", return_value=[{"type": node, "depth": 1}]):
        result = svc.find_dependencies("A.Method")
    assert result == [{"type": {"full_name": "A.Dep", "_labels": ["Class"]}, "depth": 1}]


def test_get_context_for_includes_summaries_when_available(tmp_path):
    source_file = tmp_path / "Foo.cs"
    source_file.write_text("class Foo { void Bar() {} }\n")

    conn = MagicMock()
    svc = SynapseService(conn)

    with patch.multiple(
        "synapse.service",
        get_symbol=MagicMock(return_value={"full_name": "Ns.Foo.Bar", "name": "Bar"}),
        get_symbol_source_info=MagicMock(return_value={"file_path": str(source_file), "line": 0, "end_line": 0}),
        get_containing_type=MagicMock(return_value={"full_name": "Ns.Foo", "name": "Foo", "kind": "class"}),
        get_members_overview=MagicMock(return_value=[]),
        get_implemented_interfaces=MagicMock(return_value=[]),
        find_callees=MagicMock(return_value=[]),
        query_find_dependencies=MagicMock(return_value=[]),
        get_summary=MagicMock(return_value="Handles business logic"),
    ):
        result = svc.get_context_for("Ns.Foo.Bar")

    assert "## Summaries" in result
    assert "Handles business logic" in result


def test_get_context_for_no_summaries_section_when_none_exist(tmp_path):
    source_file = tmp_path / "Foo.cs"
    source_file.write_text("class Foo { void Bar() {} }\n")

    conn = MagicMock()
    svc = SynapseService(conn)

    with patch.multiple(
        "synapse.service",
        get_symbol=MagicMock(return_value={"full_name": "Ns.Foo.Bar", "name": "Bar"}),
        get_symbol_source_info=MagicMock(return_value={"file_path": str(source_file), "line": 0, "end_line": 0}),
        get_containing_type=MagicMock(return_value=None),
        get_summary=MagicMock(return_value=None),
    ):
        result = svc.get_context_for("Ns.Foo.Bar")

    assert "## Summaries" not in result


def test_get_hierarchy_unwraps_nodes():
    svc = _service()
    parent = _node(["Class"], {"full_name": "A.Base"})
    child = _node(["Class"], {"full_name": "A.Child"})
    iface = _node(["Interface"], {"full_name": "A.IFoo"})
    with patch("synapse.service.get_hierarchy", return_value={"parents": [parent], "children": [child], "implements": [iface]}):
        result = svc.get_hierarchy("A.Middle")
    assert result["parents"] == [{"full_name": "A.Base", "_labels": ["Class"]}]
    assert result["children"] == [{"full_name": "A.Child", "_labels": ["Class"]}]
    assert result["implements"] == [{"full_name": "A.IFoo", "_labels": ["Interface"]}]


def test_get_context_for_scope_structure_returns_signatures_only(tmp_path):
    source_file = tmp_path / "Foo.cs"
    source_file.write_text(
        "namespace Ns {\n"
        "    class MyClass : IFoo {\n"
        "        public MyClass(IRepo repo) { _repo = repo; }\n"
        "        public UserDto GetUser(int id) { return _repo.Find(id); }\n"
        "    }\n"
        "}\n"
    )

    svc = _service()
    symbol = _node(["Class"], {"full_name": "Ns.MyClass", "name": "MyClass", "kind": "class"})
    ctor_node = _node(["Method"], {"full_name": "Ns.MyClass.MyClass", "name": "MyClass",
                                    "line": 2, "end_line": 2})

    with patch.multiple(
        "synapse.service",
        get_symbol=MagicMock(return_value=symbol),
        get_constructor=MagicMock(return_value=ctor_node),
        get_symbol_source_info=MagicMock(return_value={
            "file_path": str(source_file), "line": 2, "end_line": 2,
        }),
        get_members_overview=MagicMock(return_value=[
            {"full_name": "Ns.MyClass.MyClass", "name": "MyClass", "signature": "MyClass(IRepo)"},
            {"full_name": "Ns.MyClass.GetUser", "name": "GetUser", "signature": "UserDto GetUser(int)"},
        ]),
        get_implemented_interfaces=MagicMock(return_value=[
            _node(["Interface"], {"full_name": "Ns.IFoo", "name": "IFoo"}),
        ]),
        get_summary=MagicMock(return_value="Main service class"),
    ):
        result = svc.get_context_for("Ns.MyClass", scope="structure")

    assert result is not None
    assert "## Constructor" in result
    assert "public MyClass(IRepo repo)" in result
    assert "## Members" in result
    assert "GetUser: UserDto GetUser(int)" in result
    assert "## Implemented Interfaces" in result
    assert "## Summaries" in result
    # Must NOT contain full source or callees
    assert "## Target:" not in result
    assert "## Called Methods" not in result
    assert "## Parameter & Return Types" not in result


def test_get_context_for_scope_structure_on_interface():
    svc = _service()
    symbol = _node(["Interface"], {"full_name": "Ns.IFoo", "name": "IFoo", "kind": "interface"})

    with patch.multiple(
        "synapse.service",
        get_symbol=MagicMock(return_value=symbol),
        get_constructor=MagicMock(return_value=None),
        get_members_overview=MagicMock(return_value=[
            {"full_name": "Ns.IFoo.DoWork", "name": "DoWork", "signature": "void DoWork()"},
        ]),
        get_implemented_interfaces=MagicMock(return_value=[]),
        get_summary=MagicMock(return_value=None),
    ):
        result = svc.get_context_for("Ns.IFoo", scope="structure")

    assert result is not None
    assert "## Members" in result
    assert "DoWork: void DoWork()" in result
    # No constructor section for an interface with no constructor
    assert "## Constructor" not in result


def test_get_context_for_scope_structure_empty_type_returns_message():
    svc = _service()
    symbol = _node(["Class"], {"full_name": "Ns.Empty", "name": "Empty", "kind": "class"})

    with patch.multiple(
        "synapse.service",
        get_symbol=MagicMock(return_value=symbol),
        get_constructor=MagicMock(return_value=None),
        get_members_overview=MagicMock(return_value=[]),
        get_implemented_interfaces=MagicMock(return_value=[]),
        get_summary=MagicMock(return_value=None),
    ):
        result = svc.get_context_for("Ns.Empty", scope="structure")

    assert result is not None
    assert "No structure information available" in result
    assert "Ns.Empty" in result


def test_get_constructor_returns_constructor_node():
    from synapse.graph.lookups import get_constructor
    conn = MagicMock()
    ctor_node = _node(["Method"], {"full_name": "Ns.Foo.Foo", "name": "Foo"})
    conn.query.return_value = [[ctor_node]]
    result = get_constructor(conn, "Ns.Foo")
    assert result is not None
    assert result["name"] == "Foo"
    conn.query.assert_called_once()


def test_get_constructor_returns_none_when_no_constructor():
    from synapse.graph.lookups import get_constructor
    conn = MagicMock()
    conn.query.return_value = []
    result = get_constructor(conn, "Ns.Foo")
    assert result is None


def test_index_method_implements_calls_indexer() -> None:
    """SynapseService.index_method_implements must delegate to MethodImplementsIndexer."""
    svc = _service()
    with patch("synapse.service.MethodImplementsIndexer") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        svc.index_method_implements()

    mock_cls.assert_called_once_with(svc._conn)
    mock_instance.index.assert_called_once()


def test_get_context_for_scope_structure_on_method_returns_error():
    svc = _service()
    symbol = _node(["Method"], {"full_name": "Ns.Foo.Bar", "name": "Bar", "kind": "method"})
    with patch("synapse.service.get_symbol", return_value=symbol):
        result = svc.get_context_for("Ns.Foo.Bar", scope="structure")
    assert result is not None
    assert "scope='structure' requires a type" in result
    assert "method" in result


def test_get_context_for_scope_method_on_class_returns_error():
    svc = _service()
    symbol = _node(["Class"], {"full_name": "Ns.Foo", "name": "Foo", "kind": "class"})
    with patch("synapse.service.get_symbol", return_value=symbol):
        result = svc.get_context_for("Ns.Foo", scope="method")
    assert result is not None
    assert "scope='method' requires a method or property" in result
    assert "class" in result


def test_get_context_for_unknown_scope_returns_error():
    svc = _service()
    symbol = _node(["Class"], {"full_name": "Ns.Foo", "name": "Foo", "kind": "class"})
    with patch("synapse.service.get_symbol", return_value=symbol):
        result = svc.get_context_for("Ns.Foo", scope="bogus")
    assert result is not None
    assert "Unknown scope" in result
    assert "'bogus'" in result


def test_get_context_for_scope_method_returns_focused_context(tmp_path):
    source_file = tmp_path / "Foo.cs"
    source_file.write_text(
        "namespace Ns {\n"
        "    class MyClass : IFoo {\n"
        "        public UserDto GetUser(int id) {\n"
        "            return _repo.Find(id);\n"
        "        }\n"
        "    }\n"
        "}\n"
    )

    svc = _service()
    symbol = _node(["Method"], {"full_name": "Ns.MyClass.GetUser", "name": "GetUser", "kind": "method"})

    with patch.multiple(
        "synapse.service",
        get_symbol=MagicMock(return_value=symbol),
        get_symbol_source_info=MagicMock(return_value={
            "file_path": str(source_file), "line": 2, "end_line": 4,
        }),
        find_interface_contract=MagicMock(return_value={
            "method": "Ns.MyClass.GetUser",
            "interface": "Ns.IFoo",
            "contract_method": "Ns.IFoo.GetUser",
            "sibling_implementations": [],
        }),
        find_callees=MagicMock(return_value=[
            {"full_name": "Ns.Repo.Find", "name": "Find", "signature": "User Find(int)"},
        ]),
        query_find_dependencies=MagicMock(return_value=[
            {"type": _node(["Class"], {"full_name": "Ns.UserDto", "name": "UserDto"}), "depth": 1},
        ]),
        get_containing_type=MagicMock(return_value=_node(
            ["Class"], {"full_name": "Ns.MyClass", "name": "MyClass"}
        )),
        get_summary=MagicMock(return_value="Fetches user by ID"),
        get_members_overview=MagicMock(return_value=[
            {"full_name": "Ns.UserDto.Id", "name": "Id", "signature": "int"},
        ]),
    ):
        result = svc.get_context_for("Ns.MyClass.GetUser", scope="method")

    assert result is not None
    assert "## Target:" in result
    assert "GetUser" in result
    assert "## Interface Contract" in result
    assert "Ns.IFoo.GetUser" in result
    assert "## Called Methods" in result
    assert "`Ns.Repo.Find`" in result
    assert "## Parameter & Return Types" in result
    assert "Ns.UserDto" in result
    assert "## Summaries" in result
    # Must NOT contain full containing type member list
    assert "## Containing Type:" not in result
    assert "## Members:" not in result


def test_get_context_for_scope_method_empty_callees_and_no_interface(tmp_path):
    source_file = tmp_path / "Foo.cs"
    source_file.write_text("class Foo { void Simple() {} }\n")

    svc = _service()
    symbol = _node(["Method"], {"full_name": "Ns.Foo.Simple", "name": "Simple", "kind": "method"})

    with patch.multiple(
        "synapse.service",
        get_symbol=MagicMock(return_value=symbol),
        get_symbol_source_info=MagicMock(return_value={
            "file_path": str(source_file), "line": 0, "end_line": 0,
        }),
        find_interface_contract=MagicMock(return_value={
            "method": "Ns.Foo.Simple",
            "interface": None,
            "contract_method": None,
            "sibling_implementations": [],
        }),
        find_callees=MagicMock(return_value=[]),
        query_find_dependencies=MagicMock(return_value=[]),
        get_containing_type=MagicMock(return_value=None),
        get_summary=MagicMock(return_value=None),
    ):
        result = svc.get_context_for("Ns.Foo.Simple", scope="method")

    assert result is not None
    assert "## Target:" in result
    # Sections with no data should be omitted
    assert "## Interface Contract" not in result
    assert "## Called Methods" not in result
    assert "## Parameter & Return Types" not in result
    assert "## Summaries" not in result


def test_get_context_for_scope_method_interface_contract_only_matching(tmp_path):
    source_file = tmp_path / "Foo.cs"
    source_file.write_text("class Foo : IBar { void DoWork() {} }\n")

    svc = _service()
    symbol = _node(["Method"], {"full_name": "Ns.Foo.DoWork", "name": "DoWork", "kind": "method"})

    with patch.multiple(
        "synapse.service",
        get_symbol=MagicMock(return_value=symbol),
        get_symbol_source_info=MagicMock(return_value={
            "file_path": str(source_file), "line": 0, "end_line": 0,
        }),
        find_interface_contract=MagicMock(return_value={
            "method": "Ns.Foo.DoWork",
            "interface": "Ns.IBar",
            "contract_method": "Ns.IBar.DoWork",
            "sibling_implementations": [{"class_name": "Baz", "file_path": "Baz.cs"}],
        }),
        find_callees=MagicMock(return_value=[]),
        query_find_dependencies=MagicMock(return_value=[]),
        get_containing_type=MagicMock(return_value=None),
        get_summary=MagicMock(return_value=None),
    ):
        result = svc.get_context_for("Ns.Foo.DoWork", scope="method")

    assert "## Interface Contract" in result
    assert "Ns.IBar" in result
    assert "Ns.IBar.DoWork" in result
    assert "Baz" in result


def test_get_context_for_default_scope_unchanged(tmp_path):
    """Verify that scope=None produces identical output to the original get_context_for."""
    source_file = tmp_path / "Foo.cs"
    source_file.write_text(
        "namespace Ns {\n"
        "    class MyClass : IFoo {\n"
        "        public UserDto GetUser(int id) {\n"
        "            return _repo.Find(id);\n"
        "        }\n"
        "    }\n"
        "}\n"
    )

    conn = MagicMock()
    svc = SynapseService(conn)

    patches = dict(
        get_symbol=MagicMock(return_value=_node(
            ["Method"], {"full_name": "Ns.MyClass.GetUser", "name": "GetUser", "line": 2, "end_line": 4}
        )),
        get_symbol_source_info=MagicMock(return_value={
            "file_path": str(source_file), "line": 2, "end_line": 4,
        }),
        get_containing_type=MagicMock(return_value=_node(
            ["Class"], {"full_name": "Ns.MyClass", "name": "MyClass", "kind": "class"}
        )),
        get_members_overview=MagicMock(return_value=[
            {"full_name": "Ns.MyClass.GetUser", "name": "GetUser", "signature": "UserDto GetUser(int)"},
        ]),
        get_implemented_interfaces=MagicMock(return_value=[]),
        find_callees=MagicMock(return_value=[]),
        query_find_dependencies=MagicMock(return_value=[]),
        get_summary=MagicMock(return_value=None),
    )

    with patch.multiple("synapse.service", **patches):
        result_default = svc.get_context_for("Ns.MyClass.GetUser")
    with patch.multiple("synapse.service", **patches):
        result_explicit = svc.get_context_for("Ns.MyClass.GetUser", scope=None)

    assert result_default == result_explicit
    assert "## Target:" in result_default
    assert "## Containing Type:" in result_default
