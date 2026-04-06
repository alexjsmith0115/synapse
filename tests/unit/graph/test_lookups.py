"""Regression tests for find_neighborhood in synapps.graph.lookups.

Specifically tests that _extract handles neo4j.graph.Node-like objects that
implement the Mapping protocol but are NOT dict subclasses.
"""
from __future__ import annotations

from collections.abc import Mapping


class FakeNode(Mapping):
    """Simulates neo4j.graph.Node: implements Mapping but is not a dict subclass.

    This is the exact bug scenario: isinstance(node, dict) returns False,
    but isinstance(node, Mapping) returns True.
    """

    def __init__(self, data: dict) -> None:
        self._data = data

    def __getitem__(self, key):
        return self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)

    def get(self, key, default=None):
        return self._data.get(key, default)


class FakeConn:
    """Stub GraphConnection that returns pre-built query results."""

    def __init__(self, outgoing: list, incoming: list, center: list | None = None) -> None:
        self._outgoing = outgoing
        self._incoming = incoming
        self._center = center or []
        self._call_count = 0

    def query(self, cypher: str, params: dict | None = None) -> list:
        self._call_count += 1
        if self._call_count == 1:
            return self._outgoing
        if self._call_count == 2:
            return self._incoming
        return self._center


def _make_fake_row(full_name: str, name: str, kind: str = "Method") -> tuple:
    """Return a (FakeNode, rel_type_str) row as returned by conn.query."""
    node = FakeNode({"full_name": full_name, "name": name, "kind": kind,
                     "file_path": "/some/file.py", "line": 10, "signature": f"{name}()"})
    return (node, "CALLS")


def _make_dict_row(full_name: str, name: str, kind: str = "Method") -> tuple:
    """Return a plain dict row for backward-compat tests."""
    node = {"full_name": full_name, "name": name, "kind": kind,
            "file_path": "/other/file.py", "line": 5, "signature": f"{name}()"}
    return (node, "INHERITS")


# --- Proof of the bug (ensures the test would have caught the old code) ---

def test_fake_node_is_not_dict():
    """Verify FakeNode is not a dict subclass — this is the bug precondition."""
    node = FakeNode({"full_name": "a.b", "name": "b", "kind": "Method"})
    assert not isinstance(node, dict), "FakeNode must NOT be a dict for the test to be meaningful"
    assert isinstance(node, Mapping), "FakeNode must be a Mapping for the fix to apply"


# --- Test 1: FakeNode (Mapping, not dict) returns actual neighbors ---

def test_find_neighborhood_with_mapping_nodes():
    """find_neighborhood returns neighbors from Mapping-based (non-dict) objects."""
    from synapps.graph.lookups import find_neighborhood

    outgoing = [_make_fake_row("ns.Callee", "Callee")]
    conn = FakeConn(outgoing=outgoing, incoming=[])

    result = find_neighborhood(conn, "ns.Root")

    assert result["full_name"] == "ns.Root"
    assert len(result["neighbors"]) == 1
    neighbor = result["neighbors"][0]
    assert neighbor["full_name"] == "ns.Callee"
    assert neighbor["name"] == "Callee"
    assert neighbor["kind"] == "Method"
    assert neighbor["rel_type"] == "CALLS"
    assert neighbor["direction"] == "out"


# --- Test 2: Plain dicts still work (backward compat) ---

def test_find_neighborhood_with_plain_dicts():
    """find_neighborhood still works when conn.query returns plain dict objects."""
    from synapps.graph.lookups import find_neighborhood

    incoming = [_make_dict_row("ns.Caller", "Caller", "Class")]
    conn = FakeConn(outgoing=[], incoming=incoming)

    result = find_neighborhood(conn, "ns.Root")

    assert len(result["neighbors"]) == 1
    neighbor = result["neighbors"][0]
    assert neighbor["full_name"] == "ns.Caller"
    assert neighbor["name"] == "Caller"
    assert neighbor["kind"] == "Class"
    assert neighbor["direction"] == "in"
    assert neighbor["rel_type"] == "INHERITS"


# --- Test 3: Deduplication by (full_name, rel_type, direction) ---

def test_find_neighborhood_deduplicates():
    """find_neighborhood deduplicates by (full_name, rel_type, direction) tuple."""
    from synapps.graph.lookups import find_neighborhood

    row = _make_fake_row("ns.Callee", "Callee")
    # Two identical outgoing rows — should be collapsed to one
    outgoing = [row, row]
    conn = FakeConn(outgoing=outgoing, incoming=[])

    result = find_neighborhood(conn, "ns.Root")

    assert len(result["neighbors"]) == 1


# --- Test 4: Rows with empty/missing full_name are skipped ---

def test_find_neighborhood_skips_empty_full_name():
    """find_neighborhood skips rows where full_name is empty or missing."""
    from synapps.graph.lookups import find_neighborhood

    empty_node = FakeNode({"full_name": "", "name": "ghost", "kind": "Method"})
    missing_node = FakeNode({"name": "phantom", "kind": "Class"})  # no full_name key

    outgoing = [
        (empty_node, "CALLS"),
        (missing_node, "CALLS"),
        _make_fake_row("ns.Valid", "Valid"),
    ]
    conn = FakeConn(outgoing=outgoing, incoming=[])

    result = find_neighborhood(conn, "ns.Root")

    assert len(result["neighbors"]) == 1
    assert result["neighbors"][0]["full_name"] == "ns.Valid"


# ============================================================================
# find_explore tests
# ============================================================================

class FakeRelationship:
    """Simulates a neo4j Relationship object with a .type attribute."""

    def __init__(self, rel_type: str) -> None:
        self.type = rel_type


def _make_explore_node(full_name: str, name: str, kind: str = "Method") -> FakeNode:
    return FakeNode({
        "full_name": full_name,
        "name": name,
        "kind": kind,
        "file_path": f"/src/{name.lower()}.py",
        "line": 10,
    })


def _make_path_row(nodes: list, rels: list) -> tuple:
    """Return a (nodes_list, relationships_list) row as returned by nodes(p), relationships(p)."""
    return (nodes, rels)


class FakeConnExplore:
    """Stub GraphConnection for find_explore tests.

    Inspects the Cypher string to distinguish the three query calls:
    - outgoing path query: contains "RETURN nodes(p)" and source node precedes arrow
    - incoming path query: contains "RETURN nodes(p)" and source node follows arrow
    - center node query: contains "RETURN n" without "nodes(p)"
    """

    def __init__(
        self,
        outgoing_paths: list | None = None,
        incoming_paths: list | None = None,
        center: list | None = None,
    ) -> None:
        self._outgoing_paths = outgoing_paths or []
        self._incoming_paths = incoming_paths or []
        self._center = center or []

    def query(self, cypher: str, params: dict | None = None) -> list:
        if "RETURN nodes(p)" in cypher:
            # Distinguish outgoing vs incoming by direction of the path pattern.
            # Outgoing: MATCH p=(n {full_name: ...})-[...]->(m) — n appears first
            # Incoming: MATCH p=(m)-[...]->(n {full_name: ...}) — n appears last
            if cypher.lstrip().startswith("MATCH p=(n "):
                return self._outgoing_paths
            else:
                return self._incoming_paths
        # Center node query: MATCH (n {full_name: ...}) RETURN n
        return self._center


class SpyConn(FakeConnExplore):
    """FakeConnExplore subclass that records all Cypher strings passed to query()."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.captured_cyphers: list[str] = []

    def query(self, cypher: str, params: dict | None = None) -> list:
        self.captured_cyphers.append(cypher)
        return super().query(cypher, params)


# --- Test 1: depth=1 returns root, nodes, links ---

def test_find_explore_depth1():
    """find_explore returns root + neighbor nodes and links at depth=1."""
    from synapps.graph.lookups import find_explore

    root_node = _make_explore_node("A.Root", "Root")
    neighbor_node = _make_explore_node("A.Neighbor", "Neighbor")
    rel = FakeRelationship("CALLS")

    # One path: Root -> Neighbor
    outgoing = [_make_path_row([root_node, neighbor_node], [rel])]
    center = [(root_node,)]
    conn = FakeConnExplore(outgoing_paths=outgoing, center=center)

    result = find_explore(conn, "A.Root", depth=1)

    assert result["root"]["full_name"] == "A.Root"
    node_fns = {n["full_name"] for n in result["nodes"]}
    assert "A.Root" in node_fns
    assert "A.Neighbor" in node_fns
    assert len(result["links"]) == 1
    link = result["links"][0]
    assert link["source"] == "A.Root"
    assert link["target"] == "A.Neighbor"
    assert link["type"] == "CALLS"


# --- Test 2: depth=2 includes intermediate nodes ---

def test_find_explore_depth2_intermediate_nodes():
    """find_explore at depth=2 includes intermediate nodes, not just leaves."""
    from synapps.graph.lookups import find_explore

    root_node = _make_explore_node("A.Root", "Root")
    mid_node = _make_explore_node("A.Mid", "Mid")
    leaf_node = _make_explore_node("A.Leaf", "Leaf")
    rel1 = FakeRelationship("CALLS")
    rel2 = FakeRelationship("CALLS")

    # One depth-2 path: Root -> Mid -> Leaf (all three nodes present)
    outgoing = [_make_path_row([root_node, mid_node, leaf_node], [rel1, rel2])]
    center = [(root_node,)]
    conn = FakeConnExplore(outgoing_paths=outgoing, center=center)

    result = find_explore(conn, "A.Root", depth=2)

    node_fns = {n["full_name"] for n in result["nodes"]}
    assert "A.Mid" in node_fns, "Intermediate node A.Mid must be in nodes"
    assert "A.Leaf" in node_fns, "Leaf node A.Leaf must be in nodes"
    assert len(result["links"]) == 2


# --- Test 3: deduplication of links across paths ---

def test_find_explore_dedup_links():
    """When two paths share an edge A->B, only one link entry for (A, B, CALLS) appears."""
    from synapps.graph.lookups import find_explore

    root_node = _make_explore_node("A.Root", "Root")
    mid_node = _make_explore_node("A.Mid", "Mid")
    leaf1_node = _make_explore_node("A.Leaf1", "Leaf1")
    leaf2_node = _make_explore_node("A.Leaf2", "Leaf2")
    rel_calls = FakeRelationship("CALLS")

    # Two paths both traverse Root->Mid edge:
    # Path 1: Root -> Mid -> Leaf1
    # Path 2: Root -> Mid -> Leaf2
    outgoing = [
        _make_path_row([root_node, mid_node, leaf1_node], [rel_calls, rel_calls]),
        _make_path_row([root_node, mid_node, leaf2_node], [rel_calls, rel_calls]),
    ]
    center = [(root_node,)]
    conn = FakeConnExplore(outgoing_paths=outgoing, center=center)

    result = find_explore(conn, "A.Root", depth=2)

    # Root->Mid should appear only once despite two paths
    root_mid_links = [
        lk for lk in result["links"]
        if lk["source"] == "A.Root" and lk["target"] == "A.Mid"
    ]
    assert len(root_mid_links) == 1, "Edge Root->Mid must be deduplicated"


# --- Test 4: safety ceiling clamps depth=100 to 50 ---

def test_find_explore_safety_ceiling():
    """find_explore clamps depth=100 to effective_depth=50 (Cypher injection safety ceiling)."""
    from synapps.graph.lookups import find_explore

    root_node = _make_explore_node("X.Root", "Root")
    center = [(root_node,)]
    conn = SpyConn(center=center)

    find_explore(conn, "X.Root", depth=100)

    path_cyphers = [c for c in conn.captured_cyphers if "RETURN nodes(p)" in c]
    assert any("*1..50" in c for c in path_cyphers), (
        "depth=100 must be clamped to 50 in Cypher string"
    )


# --- Test 5: high depth honored (not capped) per D-02 ---

def test_find_explore_high_depth_honored():
    """find_explore passes depth=10 through to Cypher without capping (per D-02)."""
    from synapps.graph.lookups import find_explore

    root_node = _make_explore_node("X.Root", "Root")
    center = [(root_node,)]
    conn = SpyConn(center=center)

    find_explore(conn, "X.Root", depth=10)

    path_cyphers = [c for c in conn.captured_cyphers if "RETURN nodes(p)" in c]
    assert any("*1..10" in c for c in path_cyphers), (
        "depth=10 must pass through to Cypher without capping"
    )


# --- Test 6: CONTAINS edges included ---

def test_find_explore_includes_contains():
    """CONTAINS is in _EXPLORE_EDGE_FILTER so File/Directory/Repository structural neighbors appear."""
    from synapps.graph.lookups import _EXPLORE_EDGE_FILTER

    assert "CONTAINS" in _EXPLORE_EDGE_FILTER, (
        "_EXPLORE_EDGE_FILTER must include CONTAINS"
    )
    assert "CALLS" in _EXPLORE_EDGE_FILTER
    assert "INHERITS" in _EXPLORE_EDGE_FILTER
    assert "IMPLEMENTS" in _EXPLORE_EDGE_FILTER


# --- Test 8: _extract_kind recognizes Directory and Repository labels ---

def test_extract_kind_directory_repository():
    """_extract_kind returns 'Directory' and 'Repository' for nodes with those labels."""
    from synapps.graph.lookups import _extract_kind

    class FakeNeo4jNode:
        """Minimal neo4j Node-like object with a labels attribute."""
        def __init__(self, labels: set) -> None:
            self.labels = labels

    dir_node = FakeNeo4jNode({"Directory", "Node"})
    repo_node = FakeNeo4jNode({"Repository", "Node"})
    class_node = FakeNeo4jNode({"Class", "Node"})

    assert _extract_kind(dir_node) == "Directory", (
        "_extract_kind must return 'Directory' for a node with the Directory label"
    )
    assert _extract_kind(repo_node) == "Repository", (
        "_extract_kind must return 'Repository' for a node with the Repository label"
    )
    assert _extract_kind(class_node) == "Class", (
        "_extract_kind must return 'Class' for a node with the Class label"
    )


# --- Test 7: empty neighbors returns root in nodes and empty links ---

def test_find_explore_empty_neighbors():
    """find_explore for a symbol with no neighbors returns root node and empty links."""
    from synapps.graph.lookups import find_explore

    root_node = _make_explore_node("A.Isolated", "Isolated")
    center = [(root_node,)]
    conn = FakeConnExplore(outgoing_paths=[], incoming_paths=[], center=center)

    result = find_explore(conn, "A.Isolated", depth=1)

    assert result["root"]["full_name"] == "A.Isolated"
    assert len(result["links"]) == 0
    node_fns = {n["full_name"] for n in result["nodes"]}
    assert "A.Isolated" in node_fns
