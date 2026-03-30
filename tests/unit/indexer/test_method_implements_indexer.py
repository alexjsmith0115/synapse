from unittest.mock import MagicMock, call

from synapps.indexer.method_implements_indexer import MethodImplementsIndexer


def test_index_writes_edge_for_shared_method_name() -> None:
    conn = MagicMock()
    conn.query.side_effect = [
        # _materialize_transitive_implements — no transitive pairs
        [],
        # _get_impl_pairs
        [["Ns.MeetingService", "Ns.IMeetingService"]],
        # _get_methods(MeetingService)
        [["CreateAsync", "Ns.MeetingService.CreateAsync"], ["DeleteAsync", "Ns.MeetingService.DeleteAsync"]],
        # _get_methods(IMeetingService)
        [["CreateAsync", "Ns.IMeetingService.CreateAsync"], ["GetAllAsync", "Ns.IMeetingService.GetAllAsync"]],
        # _get_abstract_inherits_pairs — none
        [],
        # _get_protocol_dispatch_candidates — interface methods
        [],
    ]
    MethodImplementsIndexer(conn).index()
    # Only CreateAsync is shared — one IMPLEMENTS + one DISPATCHES_TO edge written
    assert conn.execute.call_count == 2
    implements_cypher, implements_params = conn.execute.call_args_list[0][0]
    assert "IMPLEMENTS" in implements_cypher
    assert implements_params["impl"] == "Ns.MeetingService.CreateAsync"
    assert implements_params["iface"] == "Ns.IMeetingService.CreateAsync"
    dispatches_cypher, _ = conn.execute.call_args_list[1][0]
    assert "DISPATCHES_TO" in dispatches_cypher


def test_index_writes_no_edges_when_no_pairs() -> None:
    conn = MagicMock()
    conn.query.side_effect = [[], [], [], []]  # transitive, impl pairs, abstract pairs, protocol
    MethodImplementsIndexer(conn).index()
    conn.execute.assert_not_called()


def test_index_writes_no_edges_when_no_matching_methods() -> None:
    conn = MagicMock()
    conn.query.side_effect = [
        # _materialize_transitive_implements — none
        [],
        [["Ns.Svc", "Ns.ISvc"]],
        [["PrivateMethod", "Ns.Svc.PrivateMethod"]],   # not on interface
        [["PublicMethod", "Ns.ISvc.PublicMethod"]],     # not on impl
        # _get_abstract_inherits_pairs — none
        [],
        # _get_protocol_dispatch_candidates — interface methods
        [],
    ]
    MethodImplementsIndexer(conn).index()
    conn.execute.assert_not_called()


def test_index_writes_multiple_edges_for_multiple_pairs() -> None:
    conn = MagicMock()
    conn.query.side_effect = [
        # _materialize_transitive_implements — none
        [],
        # Two impl pairs
        [["Ns.TaskService", "Ns.ITaskService"], ["Ns.TaskController", "Ns.ITaskService"]],
        # TaskService methods
        [["CreateAsync", "Ns.TaskService.CreateAsync"]],
        # ITaskService methods
        [["CreateAsync", "Ns.ITaskService.CreateAsync"]],
        # TaskController methods
        [["CreateAsync", "Ns.TaskController.CreateAsync"]],
        # ITaskService methods (fetched again for TaskController)
        [["CreateAsync", "Ns.ITaskService.CreateAsync"]],
        # _get_abstract_inherits_pairs — none
        [],
        # _get_protocol_dispatch_candidates — interface methods
        [],
    ]
    MethodImplementsIndexer(conn).index()
    # Two method pairs × two edges each (IMPLEMENTS + DISPATCHES_TO)
    assert conn.execute.call_count == 4


def test_index_writes_dispatches_to_for_abstract_base() -> None:
    """ABC abstract parent connected via INHERITS with is_abstract=true produces DISPATCHES_TO only."""
    conn = MagicMock()
    conn.query.side_effect = [
        # _materialize_transitive_implements — none
        [],
        # _get_impl_pairs — no interface pairs
        [],
        # _get_abstract_inherits_pairs — one abstract pair
        [["pkg.Dog", "pkg.Animal"]],
        # _get_methods(Dog)
        [["speak", "pkg.Dog.speak"]],
        # _get_methods(Animal)
        [["speak", "pkg.Animal.speak"]],
        # _get_protocol_dispatch_candidates — interface methods
        [],
    ]
    MethodImplementsIndexer(conn).index()
    # Exactly 1 execute call: DISPATCHES_TO only (no IMPLEMENTS for abstract base)
    assert conn.execute.call_count == 1
    cypher, params = conn.execute.call_args_list[0][0]
    assert "DISPATCHES_TO" in cypher
    assert "IMPLEMENTS" not in cypher
    assert params["parent"] == "pkg.Animal.speak"
    assert params["child"] == "pkg.Dog.speak"


def test_index_no_edges_for_abstract_base_no_matching_methods() -> None:
    """No edges when abstract parent has no matching method names with child."""
    conn = MagicMock()
    conn.query.side_effect = [
        # _materialize_transitive_implements — none
        [],
        # _get_impl_pairs — empty
        [],
        # _get_abstract_inherits_pairs — one pair
        [["pkg.Dog", "pkg.Animal"]],
        # _get_methods(Dog) — disjoint names
        [["bark", "pkg.Dog.bark"]],
        # _get_methods(Animal) — disjoint names
        [["speak", "pkg.Animal.speak"]],
        # _get_protocol_dispatch_candidates — interface methods
        [],
    ]
    MethodImplementsIndexer(conn).index()
    conn.execute.assert_not_called()


def test_index_handles_both_interface_and_abstract_pairs() -> None:
    """Both interface IMPLEMENTS pairs and abstract INHERITS pairs are processed in one run."""
    conn = MagicMock()
    conn.query.side_effect = [
        # _materialize_transitive_implements — none
        [],
        # _get_impl_pairs — one interface pair
        [["Ns.Svc", "Ns.ISvc"]],
        # _get_methods(Ns.Svc)
        [["Run", "Ns.Svc.Run"]],
        # _get_methods(Ns.ISvc)
        [["Run", "Ns.ISvc.Run"]],
        # _get_abstract_inherits_pairs — one abstract pair
        [["pkg.Dog", "pkg.Animal"]],
        # _get_methods(pkg.Dog)
        [["speak", "pkg.Dog.speak"]],
        # _get_methods(pkg.Animal)
        [["speak", "pkg.Animal.speak"]],
        # _get_protocol_dispatch_candidates — interface methods
        [],
    ]
    MethodImplementsIndexer(conn).index()
    # Interface pair: 2 (IMPLEMENTS + DISPATCHES_TO), abstract pair: 1 (DISPATCHES_TO only) = 3 total
    assert conn.execute.call_count == 3


# ---------------------------------------------------------------------------
# Regression: transitive IMPLEMENTS through interface inheritance chain
# ---------------------------------------------------------------------------


def test_transitive_implements_creates_edges() -> None:
    """Class → InterfaceB → InterfaceA chain should create IMPLEMENTS to InterfaceA."""
    conn = MagicMock()
    conn.query.side_effect = [
        # _materialize_transitive_implements — finds one transitive pair
        [["Ns.JiraProvider", "Ns.IIntegrationProvider"]],
        # _get_impl_pairs — includes the new transitive edge
        [["Ns.JiraProvider", "Ns.IJiraProvider"], ["Ns.JiraProvider", "Ns.IIntegrationProvider"]],
        # _get_methods(JiraProvider) — for IJiraProvider pair
        [["Revoke", "Ns.JiraProvider.Revoke"]],
        # _get_methods(IJiraProvider)
        [["Revoke", "Ns.IJiraProvider.Revoke"]],
        # _get_methods(JiraProvider) — for IIntegrationProvider pair
        [["Revoke", "Ns.JiraProvider.Revoke"]],
        # _get_methods(IIntegrationProvider)
        [["Revoke", "Ns.IIntegrationProvider.Revoke"]],
        # _get_abstract_inherits_pairs — none
        [],
        # _get_protocol_dispatch_candidates — none
        [],
    ]
    MethodImplementsIndexer(conn).index()
    # 1 transitive IMPLEMENTS + 2 impl pairs × 2 edges each = 5 execute calls
    assert conn.execute.call_count >= 3


# ---------------------------------------------------------------------------
# Regression: Protocol structural dispatch creates DISPATCHES_TO edges
# ---------------------------------------------------------------------------


def test_protocol_dispatch_creates_edges() -> None:
    """Concrete class with matching methods to a Protocol gets DISPATCHES_TO edges."""
    conn = MagicMock()
    conn.query.side_effect = [
        # _materialize_transitive_implements — none
        [],
        # _get_impl_pairs — empty
        [],
        # _get_abstract_inherits_pairs — empty
        [],
        # _get_protocol_dispatch_candidates — interface methods query (Python only)
        [["pkg.LanguagePlugin", "create_lsp_adapter", "pkg.LanguagePlugin.create_lsp_adapter", "python"],
         ["pkg.LanguagePlugin", "name", "pkg.LanguagePlugin.name", "python"]],
        # candidate query for LanguagePlugin (2 methods)
        [[
            [{"name": "create_lsp_adapter", "full_name": "pkg.CSharpPlugin.create_lsp_adapter"},
             {"name": "name", "full_name": "pkg.CSharpPlugin.name"}],
        ]],
    ]
    MethodImplementsIndexer(conn).index()
    assert conn.execute.call_count == 2
    for call_args in conn.execute.call_args_list:
        cypher = call_args[0][0]
        assert "DISPATCHES_TO" in cypher


# ---------------------------------------------------------------------------
# Regression: nominally-typed languages must NOT get protocol dispatch edges
# ---------------------------------------------------------------------------


def test_protocol_dispatch_skips_csharp_interfaces() -> None:
    """C# interfaces must not produce structural dispatch edges — C# uses nominal typing."""
    conn = MagicMock()
    conn.query.side_effect = [
        # _materialize_transitive_implements — none
        [],
        # _get_impl_pairs — empty
        [],
        # _get_abstract_inherits_pairs — empty
        [],
        # _get_protocol_dispatch_candidates — returns C# interfaces
        [["ProjectA.IUserService", "CreateAsync", "ProjectA.IUserService.CreateAsync", "csharp"],
         ["ProjectA.IUserService", "GetAsync", "ProjectA.IUserService.GetAsync", "csharp"]],
    ]
    MethodImplementsIndexer(conn).index()
    # No execute calls — C# interfaces should be skipped entirely
    conn.execute.assert_not_called()


def test_protocol_dispatch_skips_java_interfaces() -> None:
    """Java interfaces must not produce structural dispatch edges."""
    conn = MagicMock()
    conn.query.side_effect = [
        # _materialize_transitive_implements — none
        [],
        # _get_impl_pairs — empty
        [],
        # _get_abstract_inherits_pairs — empty
        [],
        # _get_protocol_dispatch_candidates — returns Java interfaces
        [["com.app.UserService", "create", "com.app.UserService.create", "java"]],
    ]
    MethodImplementsIndexer(conn).index()
    conn.execute.assert_not_called()
