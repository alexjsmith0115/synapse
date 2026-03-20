"""Impact analysis and architectural audit queries.

These queries aggregate information across multiple graph traversals
to answer higher-level questions about change impact, interface contracts,
and architectural patterns.
"""

from synapse.graph.connection import GraphConnection
from synapse.graph.lookups import _TEST_PATH_PATTERN, find_callees


def analyze_change_impact(conn: GraphConnection, method: str) -> dict:
    """Structured impact report: direct callers, transitive callers, test coverage.

    Answers: 'If I change this method, what breaks?'
    """
    direct = conn.query(
        "MATCH (c:Method)-[:CALLS]->(t:Method) "
        "WHERE (t.full_name = $method OR (:Method {full_name: $method})-[:IMPLEMENTS]->(t)) "
        "AND NOT c.file_path =~ $test_pattern "
        "RETURN DISTINCT c.full_name, c.file_path",
        {"method": method, "test_pattern": _TEST_PATH_PATTERN},
    )
    transitive = conn.query(
        "MATCH (c:Method)-[:CALLS*2..4]->(m) "
        "WHERE (m.full_name = $method OR (:Method {full_name: $method})-[:IMPLEMENTS]->(m)) "
        "AND NOT c.file_path =~ $test_pattern "
        "RETURN DISTINCT c.full_name, c.file_path",
        {"method": method, "test_pattern": _TEST_PATH_PATTERN},
    )
    tests = conn.query(
        "MATCH (t:Method)-[:CALLS*1..4]->(m) "
        "WHERE t.file_path =~ $test_pattern "
        "AND (m.full_name = $method OR (:Method {full_name: $method})-[:IMPLEMENTS]->(m)) "
        "RETURN DISTINCT t.full_name, t.file_path",
        {"method": method, "test_pattern": _TEST_PATH_PATTERN},
    )

    direct_callers = [{"full_name": r[0], "file_path": r[1]} for r in direct]
    transitive_callers = [{"full_name": r[0], "file_path": r[1]} for r in transitive]
    test_coverage = [{"full_name": r[0], "file_path": r[1]} for r in tests]

    callees_raw = find_callees(conn, method)
    direct_callees = []
    for node in callees_raw:
        props = dict(node) if hasattr(node, "element_id") else node
        direct_callees.append({"full_name": props["full_name"], "file_path": props.get("file_path", "")})

    all_names = {r["full_name"] for r in direct_callers + transitive_callers + test_coverage}

    return {
        "target": method,
        "direct_callers": direct_callers,
        "transitive_callers": transitive_callers,
        "test_coverage": test_coverage,
        "direct_callees": direct_callees,
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
    """Find all symbols that reference a type or its interfaces, categorized as prod or test.

    Follows the IMPLEMENTS chain so that dependents referencing an interface
    (e.g. IFooService) are included when querying the concrete type (FooService).
    Uses two queries to keep the logic consistent with the rest of this module.
    """
    iface_rows = conn.query(
        "MATCH (target {full_name: $type}) "
        "OPTIONAL MATCH (target)-[:IMPLEMENTS]->(iface:Interface) "
        "RETURN iface.full_name",
        {"type": type_name},
    )
    # OPTIONAL MATCH returns one row with None when no interfaces are found
    type_names = [type_name] + [r[0] for r in iface_rows if r[0] is not None]

    rows = conn.query(
        "MATCH (n)-[:REFERENCES]->(t) "
        "WHERE t.full_name IN $type_names AND n.full_name IS NOT NULL "
        "RETURN n.full_name, n.file_path, "
        "CASE WHEN n.file_path =~ $test_pattern THEN 'test' ELSE 'prod' END AS context",
        {"type_names": type_names, "test_pattern": _TEST_PATH_PATTERN},
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

_AUDIT_RULES: dict[str, tuple[str, str, dict]] = {
    "layering_violations": (
        "Controllers that bypass the service layer and call DbContext directly",
        "MATCH (ctrl:Class)-[:CONTAINS]->(m:Method)-[:CALLS]->(db:Method) "
        "WHERE ctrl.file_path CONTAINS 'Controllers' "
        "AND db.full_name CONTAINS 'DbContext' "
        "RETURN ctrl.name, m.name, db.full_name",
        {},
    ),
    "untested_services": (
        "Service classes with no test methods calling into them",
        "MATCH (svc:Class)-[:IMPLEMENTS]->(i) "
        "WHERE svc.file_path CONTAINS '/Services/' "
        "OPTIONAL MATCH (t:Method)-[:CALLS*1..3]->(:Method)<-[:CONTAINS]-(svc) "
        "WHERE t.file_path =~ $test_pattern "
        "WITH svc, t "
        "WHERE t IS NULL "
        "RETURN DISTINCT svc.name, svc.file_path",
        {"test_pattern": _TEST_PATH_PATTERN},
    ),
}


def audit_architecture(conn: GraphConnection, rule: str) -> dict:
    """Run an architectural audit rule against the graph.

    Valid rules: layering_violations, untested_services.
    """
    if rule not in _AUDIT_RULES:
        valid = ", ".join(sorted(_AUDIT_RULES.keys()))
        raise ValueError(f"Unknown rule '{rule}'. Valid rules: {valid}")

    description, cypher, params = _AUDIT_RULES[rule]
    rows = conn.query(cypher, params if params else None)

    violations = [dict(r) for r in rows]

    return {
        "rule": rule,
        "description": description,
        "violations": violations,
        "count": len(violations),
    }
