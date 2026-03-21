from unittest.mock import MagicMock, call

from synapse.indexer.method_implements_indexer import MethodImplementsIndexer


def test_index_writes_edge_for_shared_method_name() -> None:
    conn = MagicMock()
    conn.query.side_effect = [
        # _get_impl_pairs
        [["Ns.MeetingService", "Ns.IMeetingService"]],
        # _get_methods(MeetingService)
        [["CreateAsync", "Ns.MeetingService.CreateAsync"], ["DeleteAsync", "Ns.MeetingService.DeleteAsync"]],
        # _get_methods(IMeetingService)
        [["CreateAsync", "Ns.IMeetingService.CreateAsync"], ["GetAllAsync", "Ns.IMeetingService.GetAllAsync"]],
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
    conn.query.side_effect = [[]]  # no impl pairs
    MethodImplementsIndexer(conn).index()
    conn.execute.assert_not_called()


def test_index_writes_no_edges_when_no_matching_methods() -> None:
    conn = MagicMock()
    conn.query.side_effect = [
        [["Ns.Svc", "Ns.ISvc"]],
        [["PrivateMethod", "Ns.Svc.PrivateMethod"]],   # not on interface
        [["PublicMethod", "Ns.ISvc.PublicMethod"]],     # not on impl
    ]
    MethodImplementsIndexer(conn).index()
    conn.execute.assert_not_called()


def test_index_writes_multiple_edges_for_multiple_pairs() -> None:
    conn = MagicMock()
    conn.query.side_effect = [
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
    ]
    MethodImplementsIndexer(conn).index()
    # Two method pairs × two edges each (IMPLEMENTS + DISPATCHES_TO)
    assert conn.execute.call_count == 4


def test_index_writes_dispatches_to_for_abstract_base() -> None:
    """ABC abstract parent connected via INHERITS with is_abstract=true produces DISPATCHES_TO only."""
    conn = MagicMock()
    conn.query.side_effect = [
        # _get_impl_pairs — no interface pairs
        [],
        # _get_abstract_inherits_pairs — one abstract pair
        [["pkg.Dog", "pkg.Animal"]],
        # _get_methods(Dog)
        [["speak", "pkg.Dog.speak"]],
        # _get_methods(Animal)
        [["speak", "pkg.Animal.speak"]],
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
        # _get_impl_pairs — empty
        [],
        # _get_abstract_inherits_pairs — one pair
        [["pkg.Dog", "pkg.Animal"]],
        # _get_methods(Dog) — disjoint names
        [["bark", "pkg.Dog.bark"]],
        # _get_methods(Animal) — disjoint names
        [["speak", "pkg.Animal.speak"]],
    ]
    MethodImplementsIndexer(conn).index()
    conn.execute.assert_not_called()


def test_index_handles_both_interface_and_abstract_pairs() -> None:
    """Both interface IMPLEMENTS pairs and abstract INHERITS pairs are processed in one run."""
    conn = MagicMock()
    conn.query.side_effect = [
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
    ]
    MethodImplementsIndexer(conn).index()
    # Interface pair: 2 (IMPLEMENTS + DISPATCHES_TO), abstract pair: 1 (DISPATCHES_TO only) = 3 total
    assert conn.execute.call_count == 3
