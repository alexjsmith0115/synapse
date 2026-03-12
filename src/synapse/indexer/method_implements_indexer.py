import logging

from synapse.graph.connection import GraphConnection
from synapse.graph.edges import upsert_method_implements

log = logging.getLogger(__name__)


class MethodImplementsIndexer:
    """Post-structural phase that writes method-level IMPLEMENTS edges.

    Requires all class-level IMPLEMENTS edges and all Method nodes to exist in
    the graph. Run after Indexer.index_project's structural + base-type passes.
    No LSP is needed — operates entirely on the graph.
    """

    def __init__(self, conn: GraphConnection) -> None:
        self._conn = conn

    def index(self) -> None:
        pairs = self._get_impl_pairs()
        log.debug("MethodImplementsIndexer: %d impl/iface pairs", len(pairs))
        for impl_full_name, iface_full_name in pairs:
            impl_methods = self._get_methods(impl_full_name)
            iface_methods = self._get_methods(iface_full_name)
            for name in impl_methods.keys() & iface_methods.keys():
                upsert_method_implements(
                    self._conn,
                    impl_methods[name],
                    iface_methods[name],
                )

    def _get_impl_pairs(self) -> list[tuple[str, str]]:
        rows = self._conn.query(
            "MATCH (impl:Class)-[:IMPLEMENTS]->(iface) "
            "RETURN impl.full_name, iface.full_name"
        )
        return [(r[0], r[1]) for r in rows if r[0] and r[1]]

    def _get_methods(self, class_full_name: str) -> dict[str, str]:
        """Return {short_name: full_name} for all Method nodes contained by class_full_name."""
        rows = self._conn.query(
            "MATCH (n {full_name: $full_name})-[:CONTAINS]->(m:Method) "
            "RETURN m.name, m.full_name",
            {"full_name": class_full_name},
        )
        return {r[0]: r[1] for r in rows if r[0] and r[1]}
