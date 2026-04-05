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

    def __init__(self, outgoing: list, incoming: list) -> None:
        self._outgoing = outgoing
        self._incoming = incoming
        self._call_count = 0

    def query(self, cypher: str, params: dict | None = None) -> list:
        self._call_count += 1
        if self._call_count == 1:
            return self._outgoing
        return self._incoming


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
