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
    svc._watchers["/proj"] = [mock_watcher]

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


def test_find_type_references_rejects_invalid_kind() -> None:
    conn = MagicMock()
    svc = SynapseService(conn)
    with patch("synapse.service.resolve_full_name", return_value="Ns.Dto"):
        with pytest.raises(ValueError, match="Unknown reference kind"):
            svc.find_type_references("Dto", kind="invalid")


def test_find_type_references_passes_valid_kind() -> None:
    conn = MagicMock()
    svc = SynapseService(conn)
    with patch("synapse.service.resolve_full_name", return_value="Ns.Dto"), \
         patch("synapse.service.query_find_type_references", return_value=[]) as mock_query:
        svc.find_type_references("Dto", kind="parameter")
    mock_query.assert_called_once_with(conn, "Ns.Dto", kind="parameter")


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


def test_callers_section_formats_callers_with_sites():
    svc = _service()
    caller = _node(["Method"], {"full_name": "A.Ctrl.Create", "file_path": "/src/Ctrl.cs"})
    with patch("synapse.service.find_callers_with_sites", return_value=[
        {"caller": caller, "call_sites": [[32, 5], [58, 8]]},
    ]):
        result = svc._callers_section("Ns.Svc.DoWork")
    assert "## Direct Callers" in result
    assert "`A.Ctrl.Create`" in result
    assert "lines 32, 58" in result


def test_callers_section_single_line_uses_singular():
    svc = _service()
    caller = _node(["Method"], {"full_name": "A.Ctrl.Create", "file_path": "/src/Ctrl.cs"})
    with patch("synapse.service.find_callers_with_sites", return_value=[
        {"caller": caller, "call_sites": [[32, 5]]},
    ]):
        result = svc._callers_section("Ns.Svc.DoWork")
    assert "line 32" in result
    assert "lines" not in result


def test_callers_section_no_sites_omits_parenthetical():
    svc = _service()
    caller = _node(["Method"], {"full_name": "A.Ctrl.Create", "file_path": "/src/Ctrl.cs"})
    with patch("synapse.service.find_callers_with_sites", return_value=[
        {"caller": caller, "call_sites": []},
    ]):
        result = svc._callers_section("Ns.Svc.DoWork")
    assert "`A.Ctrl.Create`" in result
    assert "(" not in result


def test_callers_section_returns_none_when_no_callers():
    svc = _service()
    with patch("synapse.service.find_callers_with_sites", return_value=[]):
        result = svc._callers_section("Ns.Svc.DoWork")
    assert result is None


def test_callers_section_limits_to_15_callers():
    svc = _service()
    callers = [
        {"caller": _node(["Method"], {"full_name": f"A.C{i}", "file_path": f"/src/{i}.cs"}), "call_sites": []}
        for i in range(20)
    ]
    with patch("synapse.service.find_callers_with_sites", return_value=callers):
        result = svc._callers_section("Ns.Svc.DoWork")
    assert "... and 5 more callers" in result


def test_test_coverage_section_formats_test_methods():
    svc = _service()
    with patch("synapse.service.find_test_coverage", return_value=[
        {"full_name": "Ns.Tests.FooTests.TestBar", "file_path": "/tests/FooTests.cs"},
    ]):
        result = svc._test_coverage_section("Ns.Foo.Bar")
    assert "## Test Coverage" in result
    assert "Ns.Tests.FooTests.TestBar" in result


def test_test_coverage_section_returns_none_when_empty():
    svc = _service()
    with patch("synapse.service.find_test_coverage", return_value=[]):
        result = svc._test_coverage_section("Ns.Foo.Bar")
    assert result is None


def test_relevant_deps_section_shows_member_signatures():
    svc = _service()
    dep = _node(["Interface"], {"full_name": "Ns.IRepo"})
    with patch("synapse.service.find_relevant_deps", return_value=[dep]), \
         patch("synapse.service.get_called_members", return_value=[
             {"full_name": "Ns.IRepo.Save", "name": "Save", "signature": "Task Save(Entity)"},
         ]):
        result = svc._relevant_deps_section("Ns.MyClass", "Ns.MyClass.DoWork")
    assert "## Constructor Dependencies (used by this method)" in result
    assert "Ns.IRepo" in result
    assert "Save" in result


def test_relevant_deps_section_returns_none_when_empty():
    svc = _service()
    with patch("synapse.service.find_relevant_deps", return_value=[]):
        result = svc._relevant_deps_section("Ns.MyClass", "Ns.MyClass.DoWork")
    assert result is None


def test_relevant_deps_section_shows_only_called_members() -> None:
    conn = MagicMock()
    svc = SynapseService(conn)
    dep_node = {"full_name": "Ns.DbContext", "name": "DbContext"}
    with patch("synapse.service.find_relevant_deps", return_value=[dep_node]), \
         patch("synapse.service.get_called_members") as mock_called:
        mock_called.return_value = [
            {"full_name": "Ns.DbContext.MeetingNotes", "name": "MeetingNotes", "type_name": "DbSet<MeetingNote>"},
        ]
        result = svc._relevant_deps_section("Ns.Svc", "Ns.Svc.Create")
    assert result is not None
    assert "MeetingNotes" in result


def test_relevant_deps_section_fallback_to_all_members() -> None:
    conn = MagicMock()
    svc = SynapseService(conn)
    dep_node = {"full_name": "Ns.DbContext", "name": "DbContext"}
    with patch("synapse.service.find_relevant_deps", return_value=[dep_node]), \
         patch("synapse.service.get_called_members", return_value=[]), \
         patch("synapse.service.get_members_overview") as mock_members:
        mock_members.return_value = [
            {"full_name": "Ns.DbContext.All", "name": "All", "type_name": "DbSet<All>"},
        ]
        result = svc._relevant_deps_section("Ns.Svc", "Ns.Svc.Create")
    assert result is not None
    assert "all members shown" in result.lower()


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


def test_get_context_for_scope_edit_method_includes_all_sections(tmp_path):
    source_file = tmp_path / "Foo.cs"
    source_file.write_text(
        "namespace Ns {\n"
        "    class Svc : ISvc {\n"
        "        public Result DoWork(int id) {\n"
        "            return _repo.Find(id);\n"
        "        }\n"
        "    }\n"
        "}\n"
    )

    svc = _service()
    symbol = _node(["Method"], {"full_name": "Ns.Svc.DoWork", "name": "DoWork", "kind": "method"})
    caller = _node(["Method"], {"full_name": "Ns.Ctrl.Action", "file_path": "/src/Ctrl.cs"})
    dep = _node(["Interface"], {"full_name": "Ns.IRepo"})

    with patch.multiple(
        "synapse.service",
        get_symbol=MagicMock(return_value=symbol),
        get_symbol_source_info=MagicMock(return_value={
            "file_path": str(source_file), "line": 2, "end_line": 4,
        }),
        find_interface_contract=MagicMock(return_value={
            "method": "Ns.Svc.DoWork",
            "interface": "Ns.ISvc",
            "contract_method": "Ns.ISvc.DoWork",
            "sibling_implementations": [],
        }),
        find_callers_with_sites=MagicMock(return_value=[
            {"caller": caller, "call_sites": [[32, 5]]},
        ]),
        get_containing_type=MagicMock(return_value=_node(
            ["Class"], {"full_name": "Ns.Svc", "name": "Svc"}
        )),
        find_relevant_deps=MagicMock(return_value=[dep]),
        get_members_overview=MagicMock(return_value=[
            {"full_name": "Ns.IRepo.Find", "name": "Find", "signature": "Result Find(int)"},
        ]),
        find_test_coverage=MagicMock(return_value=[
            {"full_name": "Ns.Tests.SvcTests.TestDoWork", "file_path": "/tests/SvcTests.cs"},
        ]),
        get_summary=MagicMock(return_value=None),
        get_implemented_interfaces=MagicMock(return_value=[]),
    ):
        result = svc.get_context_for("Ns.Svc.DoWork", scope="edit")

    assert result is not None
    assert "## Target:" in result
    assert "## Interface Contract" in result
    assert "## Direct Callers" in result
    assert "line 32" in result
    assert "## Constructor Dependencies (used by this method)" in result
    assert "Ns.IRepo" in result
    assert "## Test Coverage" in result
    assert "Ns.Tests.SvcTests.TestDoWork" in result


def test_get_context_for_scope_edit_method_omits_empty_sections(tmp_path):
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
            "method": "Ns.Foo.Simple", "interface": None,
            "contract_method": None, "sibling_implementations": [],
        }),
        find_callers_with_sites=MagicMock(return_value=[]),
        get_containing_type=MagicMock(return_value=None),
        find_test_coverage=MagicMock(return_value=[]),
        get_summary=MagicMock(return_value=None),
    ):
        result = svc.get_context_for("Ns.Foo.Simple", scope="edit")

    assert "## Target:" in result
    assert "## Interface Contract" not in result
    assert "## Direct Callers" not in result
    assert "## Constructor Dependencies" not in result
    assert "## Test Coverage" not in result


def test_get_context_for_scope_edit_rejects_property():
    svc = _service()
    symbol = _node(["Property"], {"full_name": "Ns.Foo.Name", "name": "Name", "kind": "property"})
    with patch("synapse.service.get_symbol", return_value=symbol):
        result = svc.get_context_for("Ns.Foo.Name", scope="edit")
    assert "scope='edit' requires" in result
    assert "property" in result


def test_get_context_for_scope_edit_class_includes_all_sections(tmp_path):
    source_file = tmp_path / "Svc.cs"
    source_file.write_text(
        "namespace Ns {\n"
        "    class Svc : ISvc {\n"
        "        public void DoWork() {}\n"
        "    }\n"
        "}\n"
    )

    svc = _service()
    symbol = _node(["Class"], {"full_name": "Ns.Svc", "name": "Svc", "kind": "class"})
    method = _node(["Method"], {"full_name": "Ns.Svc.DoWork", "name": "DoWork", "signature": "void DoWork()"})
    caller = _node(["Method"], {"full_name": "Ns.Ctrl.Action", "file_path": "/src/Ctrl.cs"})
    dep = _node(["Interface"], {"full_name": "Ns.IRepo"})

    with patch.multiple(
        "synapse.service",
        get_symbol=MagicMock(return_value=symbol),
        get_symbol_source_info=MagicMock(return_value={
            "file_path": str(source_file), "line": 1, "end_line": 3,
        }),
        get_implemented_interfaces=MagicMock(return_value=[
            _node(["Interface"], {"full_name": "Ns.ISvc", "name": "ISvc"}),
        ]),
        get_members_overview=MagicMock(return_value=[method]),
        find_callers_with_sites=MagicMock(return_value=[
            {"caller": caller, "call_sites": [[10, 0]]},
        ]),
        find_all_deps=MagicMock(return_value=[dep]),
        find_test_coverage=MagicMock(return_value=[
            {"full_name": "Ns.Tests.SvcTests.TestDoWork", "file_path": "/tests/SvcTests.cs"},
        ]),
        get_summary=MagicMock(return_value=None),
    ):
        result = svc.get_context_for("Ns.Svc", scope="edit")

    assert "## Target:" in result
    assert "## Implemented Interfaces" in result
    assert "## Callers" in result
    assert "DoWork" in result
    assert "`Ns.Ctrl.Action`" in result
    assert "## Constructor Dependencies" in result
    assert "Ns.IRepo" in result
    assert "## Test Coverage" in result


def test_get_context_for_scope_edit_interface_skips_constructor_deps():
    svc = _service()
    symbol = _node(["Interface"], {"full_name": "Ns.ISvc", "name": "ISvc", "kind": "interface"})

    with patch.multiple(
        "synapse.service",
        get_symbol=MagicMock(return_value=symbol),
        get_symbol_source_info=MagicMock(return_value={
            "file_path": "/src/ISvc.cs", "line": 0, "end_line": 5,
        }),
        get_implemented_interfaces=MagicMock(return_value=[]),
        get_members_overview=MagicMock(return_value=[]),
        find_callers_with_sites=MagicMock(return_value=[]),
        find_all_deps=MagicMock(return_value=[]),
        find_test_coverage=MagicMock(return_value=[]),
        get_summary=MagicMock(return_value=None),
    ):
        result = svc.get_context_for("Ns.ISvc", scope="edit")

    assert "## Target:" in result
    assert "## Constructor Dependencies" not in result
    assert "## Implemented Interfaces" not in result


def test_get_context_for_scope_edit_class_no_methods_shows_note():
    svc = _service()
    symbol = _node(["Class"], {"full_name": "Ns.Empty", "name": "Empty", "kind": "class"})

    with patch.multiple(
        "synapse.service",
        get_symbol=MagicMock(return_value=symbol),
        get_symbol_source_info=MagicMock(return_value={
            "file_path": "/src/Empty.cs", "line": 0, "end_line": 1,
        }),
        get_implemented_interfaces=MagicMock(return_value=[]),
        get_members_overview=MagicMock(return_value=[]),
        find_all_deps=MagicMock(return_value=[]),
        find_test_coverage=MagicMock(return_value=[]),
        get_summary=MagicMock(return_value=None),
    ):
        result = svc.get_context_for("Ns.Empty", scope="edit")

    assert "No public methods found" in result


# --- find_usages tests ---


def test_find_usages_method_returns_callers() -> None:
    """For a Method symbol, find_usages returns callers."""
    svc = _service()
    method_node = _node(["Method"], {"full_name": "Ns.Svc.DoWork", "name": "DoWork"})
    caller = {"full_name": "Ns.Controller.Action", "file_path": "/src/Controller.cs", "_labels": ["Method"]}

    with patch("synapse.service.get_symbol", return_value=method_node):
        svc.find_callers = MagicMock(return_value=[caller])
        result = svc.find_usages("Ns.Svc.DoWork")

    assert result["symbol"] == "Ns.Svc.DoWork"
    assert result["kind"] == "Method"
    assert len(result["callers"]) == 1
    assert "type_references" not in result
    assert "method_callers" not in result


def test_find_usages_class_returns_type_refs_and_method_callers() -> None:
    """For a Class symbol, find_usages returns type_references and method_callers."""
    svc = _service()
    class_node = _node(["Class"], {"full_name": "Ns.MyService", "name": "MyService", "kind": "class"})
    method_member = _node(["Method"], {"full_name": "Ns.MyService.DoWork", "name": "DoWork"})
    ref_symbol = _node(["Field"], {"full_name": "Ns.Controller._svc", "file_path": "/src/Controller.cs"})
    caller = {"full_name": "Ns.Controller.Action", "file_path": "/src/Controller.cs", "_labels": ["Method"]}

    with patch.multiple(
        "synapse.service",
        get_symbol=MagicMock(return_value=class_node),
        get_members_overview=MagicMock(return_value=[method_member]),
        query_find_type_references=MagicMock(return_value=[{"symbol": ref_symbol, "kind": "field_type"}]),
    ):
        svc.find_callers = MagicMock(return_value=[caller])
        result = svc.find_usages("Ns.MyService")

    assert result["kind"] == "Class"
    assert len(result["type_references"]) == 1
    assert "Ns.MyService.DoWork" in result["method_callers"]
    assert len(result["method_callers"]["Ns.MyService.DoWork"]) == 1
    assert "callers" not in result


def test_find_usages_symbol_not_found() -> None:
    svc = _service()
    with patch("synapse.service.get_symbol", return_value=None):
        result = svc.find_usages("Ns.Missing")
    assert "error" in result
    assert "not found" in result["error"].lower()


def test_find_usages_unsupported_label() -> None:
    svc = _service()
    file_node = _node(["File"], {"full_name": "/src/Foo.cs", "name": "Foo.cs"})
    with patch("synapse.service.get_symbol", return_value=file_node):
        result = svc.find_usages("/src/Foo.cs")
    assert "error" in result
    assert "does not support" in result["error"].lower()


def test_find_usages_class_filters_test_type_references() -> None:
    """Type references from test files should be excluded by default."""
    svc = _service()
    class_node = _node(["Class"], {"full_name": "Ns.MyService", "name": "MyService", "kind": "class"})
    prod_ref = _node(["Field"], {"full_name": "Ns.Controller._svc", "file_path": "/src/Controller.cs"})
    test_ref = _node(["Field"], {"full_name": "Ns.Tests.Setup._svc", "file_path": "/proj/MyApp.Tests/Setup.cs"})

    with patch.multiple(
        "synapse.service",
        get_symbol=MagicMock(return_value=class_node),
        get_members_overview=MagicMock(return_value=[]),
        query_find_type_references=MagicMock(return_value=[
            {"symbol": prod_ref, "kind": "field_type"},
            {"symbol": test_ref, "kind": "field_type"},
        ]),
    ):
        svc.find_callers = MagicMock(return_value=[])
        result = svc.find_usages("Ns.MyService")

    assert len(result["type_references"]) == 1
    assert result["type_references"][0]["symbol"]["full_name"] == "Ns.Controller._svc"


def test_find_usages_class_includes_test_refs_when_requested() -> None:
    """exclude_test_callers=False should include test type references."""
    svc = _service()
    class_node = _node(["Class"], {"full_name": "Ns.MyService", "name": "MyService", "kind": "class"})
    prod_ref = _node(["Field"], {"full_name": "Ns.Controller._svc", "file_path": "/src/Controller.cs"})
    test_ref = _node(["Field"], {"full_name": "Ns.Tests.Setup._svc", "file_path": "/proj/MyApp.Tests/Setup.cs"})

    with patch.multiple(
        "synapse.service",
        get_symbol=MagicMock(return_value=class_node),
        get_members_overview=MagicMock(return_value=[]),
        query_find_type_references=MagicMock(return_value=[
            {"symbol": prod_ref, "kind": "field_type"},
            {"symbol": test_ref, "kind": "field_type"},
        ]),
    ):
        svc.find_callers = MagicMock(return_value=[])
        result = svc.find_usages("Ns.MyService", exclude_test_callers=False)

    assert len(result["type_references"]) == 2


def test_find_usages_property_returns_callers() -> None:
    """For a Property symbol, find_usages returns callers with kind=Property."""
    svc = _service()
    prop_node = _node(["Property"], {"full_name": "Ns.Svc.Name", "name": "Name"})
    caller = {"full_name": "Ns.Controller.Action", "file_path": "/src/Controller.cs", "_labels": ["Method"]}

    with patch("synapse.service.get_symbol", return_value=prop_node):
        svc.find_callers = MagicMock(return_value=[caller])
        result = svc.find_usages("Ns.Svc.Name")

    assert result["kind"] == "Property"
    assert len(result["callers"]) == 1


# --- max_lines fallback tests ---


def test_get_context_for_falls_back_to_structure_when_source_exceeds_max_lines(tmp_path) -> None:
    """When source > max_lines, show structure overview instead of full source."""
    source_file = tmp_path / "BigClass.cs"
    source_lines = "\n".join([f"// line {i}" for i in range(300)])
    source_file.write_text(source_lines)

    conn = MagicMock()
    svc = SynapseService(conn)

    class_node = _node(["Class"], {
        "full_name": "Ns.BigClass", "name": "BigClass", "kind": "class",
        "line": 0, "end_line": 299,
    })
    member = _node(["Method"], {
        "full_name": "Ns.BigClass.DoWork", "name": "DoWork",
        "signature": "void DoWork()",
    })

    with patch.multiple(
        "synapse.service",
        get_symbol=MagicMock(return_value=class_node),
        get_symbol_source_info=MagicMock(return_value={"file_path": str(source_file), "line": 0, "end_line": 299}),
        get_containing_type=MagicMock(return_value=None),
        get_members_overview=MagicMock(return_value=[member]),
        get_implemented_interfaces=MagicMock(return_value=[]),
        find_callees=MagicMock(return_value=[]),
        query_find_dependencies=MagicMock(return_value=[]),
        get_summary=MagicMock(return_value=None),
    ):
        result = svc.get_context_for("Ns.BigClass", max_lines=50)

    assert "Source exceeds 50 lines" in result
    assert "scope='method'" in result
    assert "DoWork" in result  # member signature visible


def test_get_context_for_shows_full_source_when_under_max_lines(tmp_path) -> None:
    """When source <= max_lines, show full source as usual."""
    source_file = tmp_path / "Small.cs"
    source_file.write_text("public class Small {}\nint x;\n")

    conn = MagicMock()
    svc = SynapseService(conn)

    class_node = _node(["Class"], {
        "full_name": "Ns.Small", "name": "Small", "kind": "class",
        "line": 0, "end_line": 1,
    })

    with patch.multiple(
        "synapse.service",
        get_symbol=MagicMock(return_value=class_node),
        get_symbol_source_info=MagicMock(return_value={"file_path": str(source_file), "line": 0, "end_line": 1}),
        get_containing_type=MagicMock(return_value=None),
        get_members_overview=MagicMock(return_value=[]),
        get_implemented_interfaces=MagicMock(return_value=[]),
        find_callees=MagicMock(return_value=[]),
        query_find_dependencies=MagicMock(return_value=[]),
        get_summary=MagicMock(return_value=None),
    ):
        result = svc.get_context_for("Ns.Small", max_lines=200)

    assert "Source exceeds" not in result
    assert "public class Small" in result


def test_get_context_for_max_lines_zero_always_uses_structure(tmp_path) -> None:
    """max_lines=0 means always use structure view."""
    source_file = tmp_path / "X.cs"
    source_file.write_text("class X {}\n")

    conn = MagicMock()
    svc = SynapseService(conn)

    class_node = _node(["Class"], {
        "full_name": "Ns.X", "name": "X", "kind": "class",
        "line": 0, "end_line": 0,
    })

    with patch.multiple(
        "synapse.service",
        get_symbol=MagicMock(return_value=class_node),
        get_symbol_source_info=MagicMock(return_value={"file_path": str(source_file), "line": 0, "end_line": 0}),
        get_containing_type=MagicMock(return_value=None),
        get_members_overview=MagicMock(return_value=[]),
        get_implemented_interfaces=MagicMock(return_value=[]),
        find_callees=MagicMock(return_value=[]),
        query_find_dependencies=MagicMock(return_value=[]),
        get_summary=MagicMock(return_value=None),
    ):
        result = svc.get_context_for("Ns.X", max_lines=0)

    assert "Source exceeds 0 lines" in result


def test_get_context_for_negative_max_lines_disables_fallback(tmp_path) -> None:
    """Negative max_lines means unlimited — no fallback."""
    source_file = tmp_path / "Huge.cs"
    source_lines = "\n".join([f"// line {i}" for i in range(500)])
    source_file.write_text(source_lines)

    conn = MagicMock()
    svc = SynapseService(conn)

    class_node = _node(["Class"], {
        "full_name": "Ns.Huge", "name": "Huge", "kind": "class",
        "line": 0, "end_line": 499,
    })

    with patch.multiple(
        "synapse.service",
        get_symbol=MagicMock(return_value=class_node),
        get_symbol_source_info=MagicMock(return_value={"file_path": str(source_file), "line": 0, "end_line": 499}),
        get_containing_type=MagicMock(return_value=None),
        get_members_overview=MagicMock(return_value=[]),
        get_implemented_interfaces=MagicMock(return_value=[]),
        find_callees=MagicMock(return_value=[]),
        query_find_dependencies=MagicMock(return_value=[]),
        get_summary=MagicMock(return_value=None),
    ):
        result = svc.get_context_for("Ns.Huge", max_lines=-1)

    assert "Source exceeds" not in result
    assert "// line 0" in result


def test_resolve_preference_concrete_selects_class() -> None:
    conn = MagicMock()
    svc = SynapseService(conn)
    with patch("synapse.service.resolve_full_name") as mock_resolve, \
         patch("synapse.service.resolve_full_name_with_labels") as mock_labels:
        mock_resolve.return_value = ["Ns.ITaskService", "Ns.TaskService"]
        mock_labels.return_value = [("Ns.ITaskService", ["Interface"]), ("Ns.TaskService", ["Class"])]
        result = svc._resolve("TaskService", preference="concrete")
    assert result == "Ns.TaskService"


def test_resolve_preference_interface_selects_interface() -> None:
    conn = MagicMock()
    svc = SynapseService(conn)
    with patch("synapse.service.resolve_full_name") as mock_resolve, \
         patch("synapse.service.resolve_full_name_with_labels") as mock_labels:
        mock_resolve.return_value = ["Ns.ITaskService", "Ns.TaskService"]
        mock_labels.return_value = [("Ns.ITaskService", ["Interface"]), ("Ns.TaskService", ["Class"])]
        result = svc._resolve("TaskService", preference="interface")
    assert result == "Ns.ITaskService"


def test_resolve_preference_none_raises_on_ambiguity() -> None:
    conn = MagicMock()
    svc = SynapseService(conn)
    with patch("synapse.service.resolve_full_name") as mock_resolve:
        mock_resolve.return_value = ["Ns.ITaskService", "Ns.TaskService"]
        with pytest.raises(ValueError, match="Ambiguous"):
            svc._resolve("TaskService")


def test_resolve_preference_still_raises_if_multiple_match() -> None:
    conn = MagicMock()
    svc = SynapseService(conn)
    with patch("synapse.service.resolve_full_name") as mock_resolve, \
         patch("synapse.service.resolve_full_name_with_labels") as mock_labels:
        mock_resolve.return_value = ["Ns.A.TaskService", "Ns.B.TaskService"]
        mock_labels.return_value = [("Ns.A.TaskService", ["Class"]), ("Ns.B.TaskService", ["Class"])]
        with pytest.raises(ValueError, match="Ambiguous"):
            svc._resolve("TaskService", preference="concrete")


def test_resolve_preference_method_checks_parent_type() -> None:
    """When both candidates are :Method, prefer the one whose parent is :Class (concrete)."""
    conn = MagicMock()
    # Parent label query returns both methods with their parent labels
    conn.query.return_value = [
        ["Ns.MeetingService.CreateAsync", ["Class"]],
        ["Ns.IMeetingService.CreateAsync", ["Interface"]],
    ]
    svc = SynapseService(conn)
    with patch("synapse.service.resolve_full_name") as mock_resolve, \
         patch("synapse.service.resolve_full_name_with_labels") as mock_labels:
        mock_resolve.return_value = ["Ns.IMeetingService.CreateAsync", "Ns.MeetingService.CreateAsync"]
        mock_labels.return_value = [
            ("Ns.IMeetingService.CreateAsync", ["Method"]),
            ("Ns.MeetingService.CreateAsync", ["Method"]),
        ]
        result = svc._resolve("CreateAsync", preference="concrete")
    assert result == "Ns.MeetingService.CreateAsync"


def test_resolve_preference_method_interface_checks_parent() -> None:
    """When both candidates are :Method, prefer the one whose parent is :Interface."""
    conn = MagicMock()
    conn.query.return_value = [
        ["Ns.MeetingService.CreateAsync", ["Class"]],
        ["Ns.IMeetingService.CreateAsync", ["Interface"]],
    ]
    svc = SynapseService(conn)
    with patch("synapse.service.resolve_full_name") as mock_resolve, \
         patch("synapse.service.resolve_full_name_with_labels") as mock_labels:
        mock_resolve.return_value = ["Ns.IMeetingService.CreateAsync", "Ns.MeetingService.CreateAsync"]
        mock_labels.return_value = [
            ("Ns.IMeetingService.CreateAsync", ["Method"]),
            ("Ns.MeetingService.CreateAsync", ["Method"]),
        ]
        result = svc._resolve("CreateAsync", preference="interface")
    assert result == "Ns.IMeetingService.CreateAsync"


def test_resolve_preference_method_still_ambiguous_if_multiple_concrete() -> None:
    """If multiple methods have :Class parents, still raise."""
    conn = MagicMock()
    conn.query.return_value = [
        ["Ns.A.CreateAsync", ["Class"]],
        ["Ns.B.CreateAsync", ["Class"]],
    ]
    svc = SynapseService(conn)
    with patch("synapse.service.resolve_full_name") as mock_resolve, \
         patch("synapse.service.resolve_full_name_with_labels") as mock_labels:
        mock_resolve.return_value = ["Ns.A.CreateAsync", "Ns.B.CreateAsync"]
        mock_labels.return_value = [
            ("Ns.A.CreateAsync", ["Method"]),
            ("Ns.B.CreateAsync", ["Method"]),
        ]
        with pytest.raises(ValueError, match="Ambiguous"):
            svc._resolve("CreateAsync", preference="concrete")
