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
        "WHERE s.full_name = $start "
        "AND (e.full_name = $end OR (:Method {full_name: $end})-[:IMPLEMENTS]->(e)) "
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


def find_entry_points(
    conn: GraphConnection,
    method: str,
    max_depth: int = 8,
) -> dict:
    """Walk backwards to find root callers with no incoming CALLS edges.

    Returns up to 20 paths, each with the entry point and full path to target.
    """
    depth = _clamp_depth(max_depth)
    rows = conn.query(
        f"MATCH p=(entry:Method)-[:CALLS*1..{depth}]->(m:Method) "
        "WHERE NOT ()-[:CALLS]->(entry) "
        "AND (m.full_name = $method OR (:Method {full_name: $method})-[:IMPLEMENTS]->(m)) "
        "RETURN [n in nodes(p) | n.full_name] AS path "
        "LIMIT 20",
        {"method": method},
    )
    return {
        "entry_points": [
            {"entry": r[0][0], "path": r[0]}
            for r in rows
        ],
        "target": method,
        "max_depth": depth,
    }


def get_call_depth(
    conn: GraphConnection,
    method: str,
    depth: int = 3,
) -> dict:
    """Recursive fanout — all methods reachable from a starting method up to N levels."""
    clamped = _clamp_depth(depth)
    rows = conn.query(
        f"MATCH p=(m:Method {{full_name: $method}})-[:CALLS*1..{clamped}]->(callee:Method) "
        "RETURN DISTINCT callee.full_name, callee.file_path, length(p) AS depth "
        "ORDER BY depth",
        {"method": method},
    )
    return {
        "root": method,
        "callees": [
            {"full_name": r[0], "file_path": r[1], "depth": r[2]}
            for r in rows
        ],
        "depth_limit": clamped,
    }
