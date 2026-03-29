"""Impact analysis and architectural audit queries.

These queries aggregate information across multiple graph traversals
to answer higher-level questions about change impact, interface contracts,
and architectural patterns.
"""

from synapps.graph.connection import GraphConnection
from synapps.graph.lookups import _TEST_PATH_PATTERN, find_callees


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
        "MATCH (impl)-[:CONTAINS]->(m:Method) "
        "WHERE m.full_name = $full_name "
        "MATCH (m)-[:OVERRIDES*0..]->(base:Method)-[:IMPLEMENTS]->(contract:Method {name: $name}) "
        "MATCH (contract)<-[:CONTAINS]-(i) "
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


# These audit rules are C#/.NET-specific. If Synapps later supports other
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


def find_dead_code(conn: GraphConnection, exclude_pattern: str = "") -> dict:
    """Query for methods with zero inbound CALLS, excluding test/framework/infra methods."""
    dead_rows = conn.query(
        "MATCH (m:Method) "
        "WHERE NOT m.file_path =~ $test_pattern "
        "AND NOT (m)-[:SERVES]->() "
        "AND NOT ()-[:IMPLEMENTS]->(m) "
        "AND NOT ()-[:DISPATCHES_TO]->(m) "
        "AND NOT (m)-[:OVERRIDES]->() "
        "AND NOT m.name IN ['__init__', 'constructor'] "
        "AND NOT EXISTS { MATCH (parent)-[:CONTAINS]->(m) "
        "WHERE (parent:Class OR parent:Interface) AND parent.name = m.name } "
        "AND ($exclude_pattern = '' OR NOT m.full_name =~ $exclude_pattern) "
        "AND NOT EXISTS { MATCH ()-[:CALLS]->(m) } "
        "RETURN m.full_name, m.file_path, m.line "
        "ORDER BY m.file_path, m.full_name",
        {"test_pattern": _TEST_PATH_PATTERN, "exclude_pattern": exclude_pattern},
    )
    total_rows = conn.query(
        "MATCH (m:Method) "
        "WHERE NOT m.file_path =~ $test_pattern "
        "AND NOT (m)-[:SERVES]->() "
        "AND NOT ()-[:IMPLEMENTS]->(m) "
        "AND NOT ()-[:DISPATCHES_TO]->(m) "
        "AND NOT (m)-[:OVERRIDES]->() "
        "AND NOT m.name IN ['__init__', 'constructor'] "
        "AND NOT EXISTS { MATCH (parent)-[:CONTAINS]->(m) "
        "WHERE (parent:Class OR parent:Interface) AND parent.name = m.name } "
        "AND ($exclude_pattern = '' OR NOT m.full_name =~ $exclude_pattern) "
        "RETURN count(m)",
        {"test_pattern": _TEST_PATH_PATTERN, "exclude_pattern": exclude_pattern},
    )
    methods = [
        {"full_name": r[0], "file_path": r[1], "line": r[2], "inbound_call_count": 0}
        for r in dead_rows
    ]
    total_methods = total_rows[0][0] if total_rows else 0
    dead_count = len(methods)
    return {
        "methods": methods,
        "stats": {
            "total_methods": total_methods,
            "dead_count": dead_count,
            "dead_ratio": round(dead_count / total_methods, 4) if total_methods else 0.0,
        },
    }


def find_untested(conn: GraphConnection, exclude_pattern: str = "") -> dict:
    """Query for production methods with no inbound TESTS edges."""
    untested_rows = conn.query(
        "MATCH (m:Method) "
        "WHERE NOT m.file_path =~ $test_pattern "
        "AND NOT (m)-[:SERVES]->() "
        "AND NOT ()-[:IMPLEMENTS]->(m) "
        "AND NOT ()-[:DISPATCHES_TO]->(m) "
        "AND NOT (m)-[:OVERRIDES]->() "
        "AND NOT m.name IN ['__init__', 'constructor'] "
        "AND NOT EXISTS { MATCH (parent)-[:CONTAINS]->(m) "
        "WHERE (parent:Class OR parent:Interface) AND parent.name = m.name } "
        "AND ($exclude_pattern = '' OR NOT m.full_name =~ $exclude_pattern) "
        "AND NOT EXISTS { MATCH ()-[:TESTS]->(m) } "
        "RETURN m.full_name, m.file_path, m.line "
        "ORDER BY m.file_path, m.full_name",
        {"test_pattern": _TEST_PATH_PATTERN, "exclude_pattern": exclude_pattern},
    )
    total_rows = conn.query(
        "MATCH (m:Method) "
        "WHERE NOT m.file_path =~ $test_pattern "
        "AND NOT (m)-[:SERVES]->() "
        "AND NOT ()-[:IMPLEMENTS]->(m) "
        "AND NOT ()-[:DISPATCHES_TO]->(m) "
        "AND NOT (m)-[:OVERRIDES]->() "
        "AND NOT m.name IN ['__init__', 'constructor'] "
        "AND NOT EXISTS { MATCH (parent)-[:CONTAINS]->(m) "
        "WHERE (parent:Class OR parent:Interface) AND parent.name = m.name } "
        "AND ($exclude_pattern = '' OR NOT m.full_name =~ $exclude_pattern) "
        "RETURN count(m)",
        {"test_pattern": _TEST_PATH_PATTERN, "exclude_pattern": exclude_pattern},
    )
    methods = [
        {"full_name": r[0], "file_path": r[1], "line": r[2]}
        for r in untested_rows
    ]
    total_methods = total_rows[0][0] if total_rows else 0
    untested_count = len(methods)
    return {
        "methods": methods,
        "stats": {
            "total_methods": total_methods,
            "untested_count": untested_count,
            "untested_ratio": round(untested_count / total_methods, 4) if total_methods else 0.0,
        },
    }


def get_architecture_overview(conn: GraphConnection, limit: int = 10) -> dict:
    """Single-call project architecture overview for agent orientation.

    Returns a dict with four sections:
    - packages: list of {name, file_count, symbol_count} per package.
      Most meaningful for C# projects — Python/TypeScript projects may return [].
    - hotspots: top N methods by inbound caller count, excluding test methods
    - http_service_map: flat list of {route, method, handler, file_path, direction} entries
    - stats: {total_files, total_symbols, total_packages, total_endpoints, files_by_language}
    """
    # Query 1: Package breakdown
    pkg_rows = conn.query(
        "MATCH (p:Package) "
        "OPTIONAL MATCH (f:File)-[:IMPORTS]->(p) "
        "WITH p, count(DISTINCT f) AS file_count "
        "OPTIONAL MATCH (s) "
        "WHERE (s:Class OR s:Interface OR s:Method OR s:Property OR s:Field) "
        "  AND s.full_name STARTS WITH (p.full_name + '.') "
        "WITH p, file_count, count(DISTINCT s) AS symbol_count "
        "RETURN p.name, file_count, symbol_count "
        "ORDER BY symbol_count DESC"
    )
    packages = [{"name": r[0], "file_count": r[1], "symbol_count": r[2]} for r in pkg_rows]

    # Query 2: Hotspot methods (most inbound callers, excluding test methods)
    hotspot_rows = conn.query(
        "MATCH (caller:Method)-[:CALLS]->(m:Method) "
        "WHERE NOT m.file_path =~ $test_pattern "
        "WITH m, count(DISTINCT caller) AS inbound_callers "
        "ORDER BY inbound_callers DESC "
        "LIMIT $limit "
        "RETURN m.full_name, m.file_path, m.line, inbound_callers",
        {"test_pattern": _TEST_PATH_PATTERN, "limit": limit},
    )
    hotspots = [
        {"full_name": r[0], "file_path": r[1], "line": r[2], "inbound_callers": r[3]}
        for r in hotspot_rows
    ]

    # Query 3: HTTP endpoints served by this codebase
    serves_rows = conn.query(
        "MATCH (handler:Method)-[:SERVES]->(ep:Endpoint) "
        "RETURN ep.route, ep.http_method, handler.full_name, handler.file_path"
    )
    serves = [
        {"route": r[0], "method": r[1], "handler": r[2], "file_path": r[3], "direction": "serves"}
        for r in serves_rows
    ]

    # Query 4: Client-only HTTP calls (orphan endpoints with no SERVES handler)
    calls_rows = conn.query(
        "MATCH (caller:Method)-[:HTTP_CALLS]->(ep:Endpoint) "
        "WHERE NOT exists((ep)<-[:SERVES]-(:Method)) "
        "RETURN ep.route, ep.http_method, caller.full_name, caller.file_path"
    )
    calls = [
        {"route": r[0], "method": r[1], "handler": r[2], "file_path": r[3], "direction": "calls"}
        for r in calls_rows
    ]

    # Query 5: File count by language
    lang_rows = conn.query(
        "MATCH (f:File) WHERE f.language IS NOT NULL "
        "RETURN f.language, count(f)"
    )
    files_by_language = {r[0]: r[1] for r in lang_rows}
    total_files = sum(files_by_language.values())

    # Query 6: Total symbol count
    symbol_count_rows = conn.query(
        "MATCH (s) WHERE s:Class OR s:Interface OR s:Method OR s:Property OR s:Field "
        "RETURN count(s)"
    )
    total_symbols = symbol_count_rows[0][0] if symbol_count_rows else 0

    # Query 7: Total endpoint count
    endpoint_count_rows = conn.query(
        "MATCH (ep:Endpoint) RETURN count(ep)"
    )
    total_endpoints = endpoint_count_rows[0][0] if endpoint_count_rows else 0

    return {
        "packages": packages,
        "hotspots": hotspots,
        "http_service_map": serves + calls,
        "stats": {
            "total_files": total_files,
            "total_symbols": total_symbols,
            "total_packages": len(packages),
            "total_endpoints": total_endpoints,
            "files_by_language": files_by_language,
        },
    }
