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
        [["Ns.Dog", "Ns.IAnimal"], ["Ns.Cat", "Ns.IAnimal"]],
        # Dog methods
        [["Speak", "Ns.Dog.Speak"]],
        # IAnimal methods
        [["Speak", "Ns.IAnimal.Speak"]],
        # Cat methods
        [["Speak", "Ns.Cat.Speak"]],
        # IAnimal methods (fetched again for Cat)
        [["Speak", "Ns.IAnimal.Speak"]],
    ]
    MethodImplementsIndexer(conn).index()
    # Two method pairs × two edges each (IMPLEMENTS + DISPATCHES_TO)
    assert conn.execute.call_count == 4
