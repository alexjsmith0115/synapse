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
        "MATCH (impl:Class)-[:CONTAINS]->(m:Method) "
        "WHERE m.full_name = $full_name "
        "MATCH (impl)-[:IMPLEMENTS]->(i)-[:CONTAINS]->(contract:Method {name: $name}) "
        "RETURN i.full_name, contract.full_name, impl.full_name",
        {"name": simple_name, "full_name": method},
    )

    if not rows:
        return {
            "method": method,
            "interface": None,
            "contract_method": None,
            "sibling_implementations": [],
        }

    iface_full_name = rows[0][0]
    impl_class_full_name = rows[0][2]

    sibling_rows = conn.query(
        "MATCH (sibling:Class)-[:IMPLEMENTS]->(i {full_name: $iface}) "
        "WHERE sibling.full_name <> $impl_class "
        "RETURN sibling.name, sibling.file_path",
        {"iface": iface_full_name, "impl_class": impl_class_full_name},
    )

    return {
        "method": method,
        "interface": iface_full_name,
        "contract_method": rows[0][1],
        "sibling_implementations": [
            {"class_name": r[0], "file_path": r[1]} for r in sibling_rows
        ],
    }


def find_type_impact(conn: GraphConnection, type_name: str) -> dict:
    """Find all symbols that reference a type, categorized as prod or test.

    Uses unlabeled (n) because REFERENCES edges can originate from any
    symbol type (Method, Class, Property, Field).
    """
    rows = conn.query(
        "MATCH (n)-[:REFERENCES]->(t {full_name: $type}) "
        "WHERE n.full_name IS NOT NULL "
        "RETURN n.full_name, n.file_path, "
        "CASE WHEN n.file_path CONTAINS 'Tests' THEN 'test' ELSE 'prod' END AS context",
        {"type": type_name},
    )

    references = [{"full_name": r[0], "file_path": r[1], "context": r[2]} for r in rows]
    prod_count = sum(1 for r in references if r["context"] == "prod")
    test_count = sum(1 for r in references if r["context"] == "test")

    return {
        "type": type_name,
        "references": references,
        "prod_count": prod_count,
        "test_count": test_count,
    }


# These audit rules are C#/.NET-specific. If Synapse later supports other
# languages, these rules need language-aware variants or should be skipped
# for non-C# projects.

_AUDIT_RULES: dict[str, tuple[str, str]] = {
    "layering_violations": (
        "Controllers that bypass the service layer and call DbContext directly",
        "MATCH (ctrl:Class)-[:CONTAINS]->(m:Method)-[:CALLS]->(db:Method) "
        "WHERE ctrl.file_path CONTAINS 'Controllers' "
        "AND db.full_name CONTAINS 'DbContext' "
        "RETURN ctrl.name, m.name, db.full_name",
    ),
    "untested_services": (
        "Service classes with no test methods calling into them",
        "MATCH (svc:Class)-[:IMPLEMENTS]->(i) "
        "WHERE svc.file_path CONTAINS '/Services/' "
        "OPTIONAL MATCH (t:Method)-[:CALLS*1..3]->(:Method)<-[:CONTAINS]-(svc) "
        "WHERE t.file_path CONTAINS 'Tests' "
        "WITH svc, t "
        "WHERE t IS NULL "
        "RETURN DISTINCT svc.name, svc.file_path",
    ),
    "repeated_db_writes": (
        "Methods calling multiple distinct SaveChangesAsync targets. "
        "NOTE: CALLS edges are created with MERGE, so this counts distinct "
        "callees, not call sites. It detects methods calling SaveChangesAsync "
        "on multiple DbContext types but not repeated calls to the same one.",
        "MATCH (m:Method)-[:CALLS]->(save:Method) "
        "WHERE save.name = 'SaveChangesAsync' "
        "WITH m, count(save) AS save_count "
        "WHERE save_count > 1 "
        "RETURN m.full_name, save_count ORDER BY save_count DESC",
    ),
}


def audit_architecture(conn: GraphConnection, rule: str) -> dict:
    """Run an architectural audit rule against the graph.

    Valid rules: layering_violations, untested_services, repeated_db_writes.
    """
    if rule not in _AUDIT_RULES:
        valid = ", ".join(sorted(_AUDIT_RULES.keys()))
        raise ValueError(f"Unknown rule '{rule}'. Valid rules: {valid}")

    description, cypher = _AUDIT_RULES[rule]
    rows = conn.query(cypher)

    violations = [dict(zip(range(len(r)), r)) for r in rows]

    return {
        "rule": rule,
        "description": description,
        "violations": violations,
        "count": len(violations),
    }
