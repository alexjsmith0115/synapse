"""Multi-hop call chain traversal queries.

These queries follow CALLS and DISPATCHES_TO edges across multiple hops.
DISPATCHES_TO (iface_method → impl_method) is the traversal-friendly inverse
of IMPLEMENTS, written at index time so paths can cross interface dispatch
boundaries without mixed-direction variable-length patterns.

Graph databases do not support parameterized variable-length relationship bounds,
so the depth integer is inlined into the Cypher string after validation
(must be int, clamped 1-10).
"""

from synapse.graph.connection import GraphConnection
from synapse.graph.lookups import _TEST_PATH_PATTERN


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
        f"MATCH p=(s:Method)-[:CALLS|DISPATCHES_TO*1..{depth}]->(e:Method) "
        "WHERE s.full_name = $start "
        "AND e.full_name = $end "
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
    exclude_pattern: str = "",
    exclude_test_callers: bool = True,
) -> dict:
    """Walk backwards to find root callers with no incoming CALLS edges from non-excluded sources.

    exclude_pattern: optional regex applied to caller full_names during traversal.
    Callers matching the pattern are invisible — so their callees become roots.
    For example, passing ".*\\.Tests\\..*" promotes controller actions to roots
    even when they are called by test methods.
    exclude_test_callers: when True (default), filters out entry points whose file_path
    matches the test path pattern (directories named Tests/tests/Test/test).
    Returns up to 20 paths, deduplicated by entry point (shortest path wins).
    """
    depth = _clamp_depth(max_depth)
    test_pattern = _TEST_PATH_PATTERN if exclude_test_callers else ""
    test_clause = "AND ($test_pattern = '' OR NOT entry.file_path =~ $test_pattern) " if exclude_test_callers else ""
    rows = conn.query(
        f"MATCH p=(entry:Method)-[:CALLS|DISPATCHES_TO*1..{depth}]->(m:Method) "
        "WHERE NOT EXISTS { "
        "    MATCH (caller)-[:CALLS]->(entry) "
        "    WHERE ($exclude_pattern = '' OR NOT caller.full_name =~ $exclude_pattern) "
        "    AND ($test_pattern = '' OR NOT caller.file_path =~ $test_pattern) "
        "} "
        "AND m.full_name = $method "
        "AND ($exclude_pattern = '' OR NOT entry.full_name =~ $exclude_pattern) "
        f"{test_clause}"
        "WITH entry, [n in nodes(p) | n.full_name] AS path "
        "ORDER BY size(path) ASC "
        "WITH entry, collect(path)[0] AS path "
        "RETURN path "
        "LIMIT 20",
        {"method": method, "exclude_pattern": exclude_pattern, "test_pattern": test_pattern},
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
        f"MATCH p=(m:Method {{full_name: $method}})-[:CALLS|DISPATCHES_TO*1..{clamped}]->(callee:Method) "
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
