"""Impact analysis and architectural audit queries.

These queries aggregate information across multiple graph traversals
to answer higher-level questions about change impact, interface contracts,
and architectural patterns.
"""

from synapse.graph.connection import GraphConnection


def analyze_change_impact(conn: GraphConnection, method: str) -> dict:
    """Structured impact report: direct callers, transitive callers, test coverage.

    Answers: 'If I change this method, what breaks?'
    """
    direct = conn.query(
        "MATCH (c:Method)-[:CALLS]->(m {full_name: $method}) "
        "RETURN c.full_name, c.file_path",
        {"method": method},
    )
    transitive = conn.query(
        "MATCH (c:Method)-[:CALLS*2..4]->(m {full_name: $method}) "
        "RETURN DISTINCT c.full_name, c.file_path",
        {"method": method},
    )
    tests = conn.query(
        "MATCH (t:Method)-[:CALLS*1..4]->(m {full_name: $method}) "
        "WHERE t.file_path CONTAINS 'Tests' "
        "RETURN DISTINCT t.full_name, t.file_path",
        {"method": method},
    )

    direct_callers = [{"full_name": r[0], "file_path": r[1]} for r in direct]
    transitive_callers = [{"full_name": r[0], "file_path": r[1]} for r in transitive]
    test_coverage = [{"full_name": r[0], "file_path": r[1]} for r in tests]

    all_names = {r["full_name"] for r in direct_callers + transitive_callers + test_coverage}

    return {
        "target": method,
        "direct_callers": direct_callers,
        "transitive_callers": transitive_callers,
        "test_coverage": test_coverage,
        "total_affected": len(all_names),
    }


def find_interface_contract(conn: GraphConnection, method: str) -> dict:
    """Find the interface a method satisfies and all sibling implementations.

    The method parameter should be a resolved full_name. The simple method
    name is extracted by splitting on '.' and taking the last segment.
    """
    simple_name = method.rsplit(".", 1)[-1]
    rows = conn.query(
        "MATCH (impl:Class)-[:CONTAINS]->(m:Method {name: $name}) "
        "WHERE m.full_name = $full_name "
        "MATCH (impl)-[:IMPLEMENTS]->(i)-[:CONTAINS]->(contract:Method {name: $name}) "
        "MATCH (sibling:Class)-[:IMPLEMENTS]->(i) "
        "WHERE sibling <> impl "
        "RETURN i.full_name, contract.full_name, sibling.name, sibling.file_path",
        {"name": simple_name, "full_name": method},
    )

    if not rows:
        return {
            "method": method,
            "interface": None,
            "contract_method": None,
            "sibling_implementations": [],
        }

    return {
        "method": method,
        "interface": rows[0][0],
        "contract_method": rows[0][1],
        "sibling_implementations": [
            {"class_name": r[2], "file_path": r[3]} for r in rows
        ],
    }
