"""Multi-hop call chain traversal queries.

These queries follow CALLS edges across multiple hops. FalkorDB does not
support parameterized variable-length relationship bounds, so the depth
integer is inlined into the Cypher string after validation (must be int,
clamped 1-10).
"""

from synapse.graph.connection import GraphConnection


def _clamp_depth(depth: int, max_allowed: int = 10) -> int:
    return max(1, min(int(depth), max_allowed))


def trace_call_chain(
    conn: GraphConnection,
    start: str,
    end: str,
    max_depth: int = 6,
) -> dict:
    """Find all call paths between two methods.

    Returns up to 10 paths, each a list of full_names from start to end.
    """
    depth = _clamp_depth(max_depth)
    rows = conn.query(
        f"MATCH p=(s:Method)-[:CALLS*1..{depth}]->(e:Method) "
        "WHERE s.full_name = $start AND e.full_name = $end "
        "RETURN [n in nodes(p) | n.full_name] AS path "
        "LIMIT 10",
        {"start": start, "end": end},
    )
    return {
        "paths": [r[0] for r in rows],
        "start": start,
        "end": end,
        "max_depth": depth,
    }
