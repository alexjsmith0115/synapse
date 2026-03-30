import logging

from synapps.graph.connection import GraphConnection
from synapps.graph.edges import upsert_abstract_dispatches_to, upsert_method_implements

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
        self._materialize_transitive_implements()

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

        abstract_pairs = self._get_abstract_inherits_pairs()
        log.debug("MethodImplementsIndexer: %d abstract/base pairs", len(abstract_pairs))
        for child_full_name, parent_full_name in abstract_pairs:
            child_methods = self._get_methods(child_full_name)
            parent_methods = self._get_methods(parent_full_name)
            for name in child_methods.keys() & parent_methods.keys():
                upsert_abstract_dispatches_to(self._conn, child_methods[name], parent_methods[name])

        protocol_dispatches = self._get_protocol_dispatch_candidates()
        log.debug("MethodImplementsIndexer: %d protocol dispatch edges", len(protocol_dispatches))
        for concrete_method, iface_method in protocol_dispatches:
            upsert_abstract_dispatches_to(self._conn, concrete_method, iface_method)

    def _get_abstract_inherits_pairs(self) -> list[tuple[str, str]]:
        rows = self._conn.query(
            "MATCH (child:Class)-[:INHERITS]->(parent:Class) "
            "WHERE parent.is_abstract = true "
            "RETURN child.full_name, parent.full_name"
        )
        return [(r[0], r[1]) for r in rows if r[0] and r[1]]

    def _get_impl_pairs(self) -> list[tuple[str, str]]:
        rows = self._conn.query(
            "MATCH (impl:Class)-[:IMPLEMENTS]->(iface) "
            "RETURN impl.full_name, iface.full_name"
        )
        return [(r[0], r[1]) for r in rows if r[0] and r[1]]

    def _materialize_transitive_implements(self) -> None:
        """Create IMPLEMENTS edges for interfaces inherited through the chain.

        If class A IMPLEMENTS interface B, and B INHERITS interface C,
        then A should also IMPLEMENTS C. Without this, method-level
        IMPLEMENTS edges are never created for ancestor interface methods.
        """
        rows = self._conn.query(
            "MATCH (cls:Class)-[:IMPLEMENTS]->(direct)-[:INHERITS*1..5]->(ancestor) "
            "WHERE ancestor:Interface "
            "AND NOT (cls)-[:IMPLEMENTS]->(ancestor) "
            "RETURN DISTINCT cls.full_name, ancestor.full_name"
        )
        if not rows:
            return
        count = 0
        for cls_fn, ancestor_fn in rows:
            if cls_fn and ancestor_fn:
                self._conn.execute(
                    "MATCH (cls:Class {full_name: $cls}), (iface {full_name: $iface}) "
                    "WHERE iface:Interface OR iface:Class "
                    "MERGE (cls)-[:IMPLEMENTS]->(iface)",
                    {"cls": cls_fn, "iface": ancestor_fn},
                )
                count += 1
        if count:
            log.debug("MethodImplementsIndexer: %d transitive IMPLEMENTS edges", count)

    def _get_protocol_dispatch_candidates(self) -> list[tuple[str, str]]:
        """Find concrete methods that structurally match Protocol/Interface methods.

        Only creates edges where the concrete class implements ALL methods of
        the interface (structural typing: the class satisfies the full protocol).
        Skips pairs that already have IMPLEMENTS or DISPATCHES_TO edges.

        Restricted to Python interfaces only — Python uses structural typing
        (Protocols) where a class satisfies an interface by having matching
        methods. C#, Java, and TypeScript use nominal typing where IMPLEMENTS
        edges come from explicit declarations resolved by the LSP.
        """
        # Step 1: Get all Interface classes and their method sets (Python only)
        iface_rows = self._conn.query(
            "MATCH (iface:Interface)-[:CONTAINS]->(im:Method) "
            "RETURN iface.full_name, im.name, im.full_name, iface.language"
        )
        # Group methods by interface: {iface_full_name: {method_name: method_full_name}}
        iface_methods: dict[str, dict[str, str]] = {}
        for iface_fn, m_name, m_fn, lang in iface_rows:
            if not iface_fn or not m_name or not m_fn:
                continue
            if lang != "python":
                continue
            iface_methods.setdefault(iface_fn, {})[m_name] = m_fn

        if not iface_methods:
            return []

        # Step 2: For each interface, find concrete classes with ALL matching method names
        results: list[tuple[str, str]] = []
        for iface_fn, methods in iface_methods.items():
            method_names = list(methods.keys())
            if not method_names:
                continue

            # Find concrete classes that contain methods matching every interface method name
            # and don't already have an explicit IMPLEMENTS edge to this interface
            candidate_rows = self._conn.query(
                "MATCH (cls:Class)-[:CONTAINS]->(cm:Method) "
                "WHERE NOT cls:Interface "
                "AND NOT (cls)-[:IMPLEMENTS]->({full_name: $iface}) "
                "AND cm.name IN $names "
                "WITH cls, collect(DISTINCT cm.name) AS matched_names, "
                "     collect({name: cm.name, full_name: cm.full_name}) AS matched_methods "
                "WHERE size(matched_names) = $count "
                "RETURN matched_methods",
                {"iface": iface_fn, "names": method_names, "count": len(method_names)},
            )

            for row in candidate_rows:
                for method_entry in row[0]:
                    m_name = method_entry["name"]
                    concrete_fn = method_entry["full_name"]
                    iface_method_fn = methods[m_name]
                    results.append((concrete_fn, iface_method_fn))

        return results

    def _get_methods(self, class_full_name: str) -> dict[str, str]:
        """Return {short_name: full_name} for all Method nodes contained by class_full_name."""
        rows = self._conn.query(
            "MATCH (n {full_name: $full_name})-[:CONTAINS]->(m:Method) "
            "RETURN m.name, m.full_name",
            {"full_name": class_full_name},
        )
        return {r[0]: r[1] for r in rows if r[0] and r[1]}
