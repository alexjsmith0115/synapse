"""
MCP tool integration tests against the Java fixture (SynappsJavaTest).

Requires Memgraph on localhost:7687 and Eclipse JDT LS (Java JDK 11+).
Run with: pytest tests/integration/test_mcp_tools_java.py -v -m integration

NOTE: GraphHopper (/Users/alex/Dev/opensource/graphhopper) can be used for
real-world validation per D-22, but is NOT included in CI tests (too large/slow).
"""
from __future__ import annotations

import pytest
from mcp.server.fastmcp import FastMCP

from tests.integration.conftest import run, text, result_json, JAVA_FIXTURE_PATH


# ---------------------------------------------------------------------------
# Project-level tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(30)
def test_list_projects(java_mcp: FastMCP) -> None:
    """list_projects returns at least one project with language 'java'."""
    result = run(java_mcp.call_tool("list_projects", {}))
    data = result_json(result)
    assert "synapps_mcp_version" in data
    projects = data["projects"]
    assert len(projects) >= 1
    all_languages = [lang for p in projects for lang in p.get("languages", [])]
    assert "java" in all_languages, f"Expected 'java' in project languages, got: {all_languages}"


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_index_status(java_mcp: FastMCP) -> None:
    """list_projects(path=...) returns a populated status dict for the Java fixture."""
    result = run(java_mcp.call_tool("list_projects", {"path": JAVA_FIXTURE_PATH}))
    status = result_json(result)
    assert status is not None
    assert "synapps_mcp_version" in status
    assert status["file_count"] > 0
    assert status["symbol_count"] > 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_schema(java_mcp: FastMCP) -> None:
    """get_schema returns the graph schema (not Java-specific, but must not error)."""
    result = run(java_mcp.call_tool("get_schema", {}))
    schema = result_json(result)
    assert "node_labels" in schema


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_index_project(java_mcp: FastMCP) -> None:
    """index_project re-indexes the Java fixture without error (upsert -- safe to re-run)."""
    result = run(java_mcp.call_tool("index_project", {
        "path": JAVA_FIXTURE_PATH,
        "language": "java",
    }))
    msg = text(result)
    assert "Indexed" in msg



# ---------------------------------------------------------------------------
# Symbol query tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_search_symbols_finds_classes(java_mcp: FastMCP) -> None:
    """search_symbols for 'Animal' returns Animal and IAnimal."""
    result = run(java_mcp.call_tool("search_symbols", {"query": "Animal"}))
    symbols = result_json(result)
    assert isinstance(symbols, list)
    assert len(symbols) >= 2
    names = [s["full_name"] for s in symbols]
    assert any("Animal" in n for n in names)
    assert any("IAnimal" in n for n in names), f"Expected IAnimal in {names}"


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_search_symbols_by_kind(java_mcp: FastMCP) -> None:
    """search_symbols with kind='interface' finds IAnimal."""
    result = run(java_mcp.call_tool("search_symbols", {
        "query": "Animal",
        "kind": "Interface",
    }))
    symbols = result_json(result)
    assert isinstance(symbols, list)
    assert len(symbols) >= 1
    names = [s["full_name"] for s in symbols]
    assert any("IAnimal" in n for n in names), f"Expected IAnimal in {names}"


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_search_symbols_language_filter(java_mcp: FastMCP) -> None:
    """search_symbols with language='java' returns only Java symbols."""
    result = run(java_mcp.call_tool("search_symbols", {
        "query": "Animal",
        "language": "java",
    }))
    symbols = result_json(result)
    assert isinstance(symbols, list)
    for sym in symbols:
        assert sym.get("language") == "java", (
            f"Expected language='java', got: {sym.get('language')} for {sym.get('full_name')}"
        )


# ---------------------------------------------------------------------------
# Relationship tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_implementations(java_mcp: FastMCP) -> None:
    """find_implementations for IAnimal returns its implementing classes."""
    result = run(java_mcp.call_tool("find_implementations", {
        "full_name": "com.synappstest.IAnimal"
    }))
    impls = result_json(result)
    assert isinstance(impls, list)
    assert len(impls) >= 1, f"Expected at least Animal implementing IAnimal, got {impls}"
    names = [i.get("full_name", "") for i in impls]
    assert any("Animal" in n for n in names), f"Expected Animal in {names}"


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_hierarchy(java_mcp: FastMCP) -> None:
    """get_hierarchy for Dog returns Animal in parent chain."""
    result = run(java_mcp.call_tool("get_hierarchy", {
        "full_name": "com.synappstest.Dog"
    }))
    hierarchy = result_json(result)
    assert "parents" in hierarchy
    parent_names = [p.get("full_name", "") for p in hierarchy["parents"]]
    assert any("Animal" in n for n in parent_names), (
        f"Expected Animal in Dog's parents, got: {parent_names}"
    )


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_callees(java_mcp: FastMCP) -> None:
    """find_callees returns a list (possibly empty) without error for Java method."""
    result = run(java_mcp.call_tool("find_callees", {
        "full_name": "com.synappstest.AnimalService.greet"
    }))
    callees = result_json(result)
    assert isinstance(callees, list)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_type_references(java_mcp: FastMCP) -> None:
    """find_usages with kind='parameter' returns list (possibly empty) without error for Java interface."""
    result = run(java_mcp.call_tool("find_usages", {
        "full_name": "com.synappstest.IAnimal",
        "kind": "parameter",
    }))
    refs = result_json(result)
    assert isinstance(refs, list)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_usages(java_mcp: FastMCP) -> None:
    """find_usages returns compact text summary for a Java interface."""
    result = run(java_mcp.call_tool("find_usages", {
        "full_name": "com.synappstest.IAnimal"
    }))
    output = text(result)
    assert "Usages of" in output
    assert "IAnimal" in output


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_dependencies(java_mcp: FastMCP) -> None:
    """find_dependencies returns result without error for AnimalService."""
    result = run(java_mcp.call_tool("find_dependencies", {
        "full_name": "com.synappstest.AnimalService"
    }))
    deps = result_json(result)
    assert isinstance(deps, (list, dict)), f"Expected list or dict result, got: {type(deps)}"


@pytest.mark.integration
@pytest.mark.timeout(15)
def test_find_dependencies_fields(java_mcp: FastMCP) -> None:
    """FILD-04: find_dependencies returns 'fields' section with @Autowired fields for Java classes."""
    result = run(java_mcp.call_tool("find_dependencies", {
        "full_name": "com.synappstest.AnimalService"
    }))
    deps = result_json(result)
    # AnimalService has @Autowired private IAnimal animal — should return dict with fields section
    assert isinstance(deps, dict), (
        f"Expected dict with 'fields' key for AnimalService (has @Autowired fields), got: {type(deps).__name__}: {deps}"
    )
    assert "fields" in deps, f"Expected 'fields' key in result, got keys: {list(deps.keys())}"
    fields = deps["fields"]
    assert isinstance(fields, list), f"Expected 'fields' to be a list, got: {type(fields)}"
    assert len(fields) >= 1, f"Expected at least 1 field entry, got: {fields}"

    # Verify shape of each field entry
    for f in fields:
        assert "name" in f, f"Field entry missing 'name': {f}"
        assert "type_name" in f, f"Field entry missing 'type_name': {f}"
        assert "annotations" in f, f"Field entry missing 'annotations': {f}"
        assert isinstance(f["annotations"], list), f"'annotations' should be a list: {f}"

    # Verify @Autowired IAnimal field is present
    animal_field = next((f for f in fields if f.get("name") == "animal"), None)
    assert animal_field is not None, f"Expected field 'animal' in fields list, got: {fields}"
    assert animal_field["type_name"] == "IAnimal", (
        f"Expected type_name='IAnimal' for field 'animal', got: {animal_field['type_name']}"
    )
    assert "autowired" in animal_field["annotations"], (
        f"Expected 'autowired' in annotations for field 'animal', got: {animal_field['annotations']}"
    )


@pytest.mark.integration
@pytest.mark.timeout(15)
def test_field_type_name(java_mcp: FastMCP) -> None:
    """FILD-01: Field nodes have non-empty type_name after indexing."""
    result = run(java_mcp.call_tool("execute_query", {
        "cypher": (
            "MATCH (f:Field {name: 'animal'}) "
            "WHERE f.file_path CONTAINS 'AnimalService' "
            "RETURN f.type_name"
        ),
    }))
    data = result_json(result)
    assert len(data) >= 1, f"Expected Field node 'animal' in AnimalService, got: {data}"
    type_names = [row["row"][0] for row in data if row["row"][0]]
    assert any(tn == "IAnimal" for tn in type_names), (
        f"Expected type_name='IAnimal' on field 'animal', got: {type_names}"
    )


@pytest.mark.integration
@pytest.mark.timeout(15)
def test_field_references(java_mcp: FastMCP) -> None:
    """FILD-02: REFERENCES edges exist from Field nodes to project-defined types."""
    result = run(java_mcp.call_tool("execute_query", {
        "cypher": (
            "MATCH (f:Field {name: 'animal'})-[:REFERENCES]->(t) "
            "WHERE f.file_path CONTAINS 'AnimalService' "
            "RETURN t.full_name, t.name"
        ),
    }))
    data = result_json(result)
    assert len(data) >= 1, (
        f"Expected REFERENCES edge from Field 'animal' to IAnimal, got: {data}"
    )
    target_names = [row["row"][0] for row in data if row["row"][0]]
    assert any("IAnimal" in n for n in target_names), (
        f"Expected target containing 'IAnimal', got: {target_names}"
    )


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_context_for(java_mcp: FastMCP) -> None:
    """get_context_for returns context string for a Java class."""
    result = run(java_mcp.call_tool("get_context_for", {
        "full_name": "com.synappstest.Dog"
    }))
    ctx = text(result)
    assert len(ctx) > 0
    assert "Dog" in ctx


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_context_for_structure_scope(java_mcp: FastMCP) -> None:
    """get_context_for(scope='structure') returns Members but not Called Methods for a Java class."""
    result = run(java_mcp.call_tool("get_context_for", {
        "full_name": "com.synappstest.AnimalService",
        "scope": "structure",
    }))
    ctx = text(result)
    assert "## Members" in ctx
    assert "AnimalService" in ctx
    assert "## Called Methods" not in ctx


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_context_for_method_scope(java_mcp: FastMCP) -> None:
    """get_context_for(scope='method') returns Target but not Containing Type or Members list."""
    result = run(java_mcp.call_tool("get_context_for", {
        "full_name": "com.synappstest.AnimalService.greet()",
        "scope": "method",
    }))
    ctx = text(result)
    assert "## Target:" in ctx
    assert "greet" in ctx
    assert "## Containing Type:" not in ctx
    assert "## Members:" not in ctx


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_context_for_edit_scope_method(java_mcp: FastMCP) -> None:
    """get_context_for(scope='edit') on a method returns Target but not Containing Type or Called Methods."""
    result = run(java_mcp.call_tool("get_context_for", {
        "full_name": "com.synappstest.AnimalService.greet()",
        "scope": "edit",
    }))
    ctx = text(result)
    assert "## Target:" in ctx
    assert "greet" in ctx
    assert "## Containing Type:" not in ctx
    assert "## Called Methods" not in ctx


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_context_for_edit_scope_class(java_mcp: FastMCP) -> None:
    """get_context_for(scope='edit') on a class returns Target and the class name."""
    result = run(java_mcp.call_tool("get_context_for", {
        "full_name": "com.synappstest.AnimalService",
        "scope": "edit",
    }))
    ctx = text(result)
    assert "## Target:" in ctx
    assert "AnimalService" in ctx


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_context_for_edit_scope_rejects_field(java_mcp: FastMCP) -> None:
    """get_context_for(scope='edit') on a Field node returns the rejection message."""
    result = run(java_mcp.call_tool("get_context_for", {
        "full_name": "com.synappstest.Animal.name",
        "scope": "edit",
    }))
    ctx = text(result)
    assert "scope='edit' requires" in ctx


# ---------------------------------------------------------------------------
# Call chain / entry point / impact tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_find_entry_points(java_mcp: FastMCP) -> None:
    """find_entry_points returns dict with entry_points key without error."""
    result = run(java_mcp.call_tool("find_entry_points", {
        "full_name": "com.synappstest.AnimalService.greet",
    }))
    ep = result_json(result)
    assert isinstance(ep, dict)
    assert "entry_points" in ep


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_call_depth(java_mcp: FastMCP) -> None:
    """find_callees with depth param returns dict with callees key without error."""
    result = run(java_mcp.call_tool("find_callees", {
        "full_name": "com.synappstest.AnimalService.greet",
        "depth": 3,
    }))
    depth_result = result_json(result)
    assert isinstance(depth_result, dict)
    assert "callees" in depth_result


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_context_for_impact(java_mcp: FastMCP) -> None:
    """get_context_for(scope='impact') returns compact text summary for a Java method."""
    result = run(java_mcp.call_tool("get_context_for", {
        "full_name": "com.synappstest.AnimalService.greet",
        "scope": "impact",
    }))
    output = text(result)
    assert "Change Impact" in output
    assert "greet" in output
    assert "affected" in output


# ---------------------------------------------------------------------------
# Summary tools
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_get_summary_no_summary(java_mcp: FastMCP) -> None:
    """summary action=get returns None or empty when no summary set for Java symbol."""
    result = run(java_mcp.call_tool("summary", {
        "action": "get",
        "full_name": "com.synappstest.Cat",
    }))
    summary = result_json(result)
    assert summary is None or isinstance(summary, str)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_set_and_get_summary(java_mcp: FastMCP) -> None:
    """summary action=set/get round-trip correctly for a Java symbol."""
    run(java_mcp.call_tool("summary", {
        "action": "set",
        "full_name": "com.synappstest.Dog",
        "content": "A dog class that barks.",
    }))
    result = run(java_mcp.call_tool("summary", {
        "action": "get",
        "full_name": "com.synappstest.Dog",
    }))
    assert text(result) == "A dog class that barks."


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_list_summarized(java_mcp: FastMCP) -> None:
    """summary action=list includes the symbol annotated in test_set_and_get_summary."""
    run(java_mcp.call_tool("summary", {
        "action": "set",
        "full_name": "com.synappstest.Dog",
        "content": "A dog class that barks.",
    }))
    result = run(java_mcp.call_tool("summary", {"action": "list"}))
    items = result_json(result)
    names = [i.get("full_name") for i in items]
    assert "com.synappstest.Dog" in names


# ---------------------------------------------------------------------------
# Execute query
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_execute_query(java_mcp: FastMCP) -> None:
    """execute_query can count Java Class nodes in the graph."""
    result = run(java_mcp.call_tool("execute_query", {
        "cypher": "MATCH (n:Class {language: 'java'}) RETURN count(n) AS cnt"
    }))
    rows = result_json(result)
    assert isinstance(rows, list)
    assert len(rows) > 0
    count = rows[0]["row"][0]
    assert count > 0, f"Expected at least one Java Class node, got count={count}"


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_execute_mutating_query_blocked(java_mcp: FastMCP) -> None:
    """execute_query raises when a mutating (CREATE) Cypher query is submitted."""
    with pytest.raises(Exception):
        run(java_mcp.call_tool("execute_query", {
            "cypher": "CREATE (n:Fake) RETURN n"
        }))


# ---------------------------------------------------------------------------
# Inheritance and implementation edge assertions
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_java_inherits_edges(java_mcp: FastMCP) -> None:
    """Dog class has an INHERITS edge to Animal class after indexing."""
    result = run(java_mcp.call_tool("execute_query", {
        "cypher": (
            "MATCH (child)-[:INHERITS]->(parent) "
            "WHERE child.full_name CONTAINS 'Dog' AND parent.full_name CONTAINS 'Animal' "
            "RETURN child.full_name, parent.full_name"
        ),
    }))
    data = result_json(result)
    assert isinstance(data, list) and len(data) >= 1, (
        f"Expected Dog INHERITS Animal edge, got: {data}"
    )


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_java_implements_edges(java_mcp: FastMCP) -> None:
    """Animal class has an IMPLEMENTS edge to IAnimal interface after indexing."""
    result = run(java_mcp.call_tool("execute_query", {
        "cypher": (
            "MATCH (impl)-[:IMPLEMENTS]->(iface) "
            "WHERE impl.full_name CONTAINS 'Animal' "
            "AND NOT impl.full_name CONTAINS 'Service' "
            "AND iface.full_name CONTAINS 'IAnimal' "
            "RETURN impl.full_name, iface.full_name"
        ),
    }))
    data = result_json(result)
    assert isinstance(data, list) and len(data) >= 1, (
        f"Expected Animal IMPLEMENTS IAnimal edge, got: {data}"
    )


# ---------------------------------------------------------------------------
# Attribute property verification
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_attributes_populated_on_java_nodes(java_mcp: FastMCP) -> None:
    """n.attributes JSON property is populated for annotated Java methods after indexing."""
    result = run(java_mcp.call_tool("execute_query", {
        "cypher": (
            "MATCH (n:Method) WHERE n.full_name CONTAINS 'legacyMethod' "
            "RETURN n.attributes, n.is_static"
        )
    }))
    rows = result_json(result)
    assert rows and len(rows) > 0, "legacyMethod node not found in graph"
    row = rows[0]["row"]
    attributes_value = row[0]
    is_static_value = row[1]
    assert attributes_value is not None, (
        "n.attributes is null on legacyMethod — Java attribute extraction pipeline not writing to graph"
    )
    assert "deprecated" in attributes_value, (
        f"Expected 'deprecated' in legacyMethod.attributes, got: {attributes_value}"
    )
    assert is_static_value is True, (
        f"Expected n.is_static=true on legacyMethod (static modifier), got: {is_static_value}"
    )


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_class_level_attributes_populated(java_mcp: FastMCP) -> None:
    """Abstract modifier on Java class produces n.attributes entry after indexing."""
    result = run(java_mcp.call_tool("execute_query", {
        "cypher": (
            "MATCH (n) WHERE n.full_name = 'com.synappstest.Animal' "
            "RETURN n.attributes"
        )
    }))
    rows = result_json(result)
    assert rows and len(rows) > 0, "Animal class node not found in graph"
    attributes_value = rows[0]["row"][0]
    assert attributes_value is not None, (
        "n.attributes is null on Animal class — abstract modifier not extracted"
    )
    assert "abstract" in attributes_value, (
        f"Expected 'abstract' in Animal.attributes, got: {attributes_value}"
    )


# ---------------------------------------------------------------------------
# Java Package node and CONTAINS edge tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_java_package_node_exists(java_mcp: FastMCP) -> None:
    """Package node for 'com.synappstest' exists after indexing."""
    result = run(java_mcp.call_tool("execute_query", {
        "cypher": "MATCH (p:Package) WHERE p.full_name CONTAINS 'synappstest' RETURN p.full_name, p.name",
    }))
    data = result_json(result)
    assert len(data) >= 1, f"Expected at least 1 package node, got: {data}"
    pkg_names = [row["row"][0] for row in data]
    assert any("com.synappstest" in p for p in pkg_names), (
        f"Expected com.synappstest package, got: {pkg_names}"
    )


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_java_package_contains_edges(java_mcp: FastMCP) -> None:
    """Package node 'com.synappstest' exists and has CONTAINS edges to top-level classes."""
    result = run(java_mcp.call_tool("execute_query", {
        "cypher": (
            "MATCH (p:Package {full_name: 'com.synappstest'})-[:CONTAINS]->(c) "
            "RETURN c.full_name ORDER BY c.full_name"
        ),
    }))
    data = result_json(result)
    contained = [row["row"][0] for row in data]
    # SynappsJavaTest has: Animal, AnimalService, Cat, Dog, Formatter, IAnimal
    assert len(contained) >= 3, f"Expected at least 3 contained symbols, got: {contained}"
    full_names_str = " ".join(str(c) for c in contained)
    assert "Animal" in full_names_str, f"Expected Animal class in package, got: {contained}"
    assert "IAnimal" in full_names_str, f"Expected IAnimal interface in package, got: {contained}"


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_java_no_anonymous_class_nodes(java_mcp: FastMCP) -> None:
    """Anonymous class expressions must not produce Class nodes in the graph."""
    result = run(java_mcp.call_tool("execute_query", {
        "cypher": "MATCH (c:Class) WHERE c.name STARTS WITH 'new ' RETURN c.name, c.full_name",
    }))
    data = result_json(result)
    assert len(data) == 0, f"Expected 0 anonymous class nodes, got: {data}"


# ---------------------------------------------------------------------------
# IMPORTS edge tests (JI-01, JI-02)
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_java_imports_edges(java_mcp: FastMCP) -> None:
    """Java class-level imports produce IMPORTS edges in the graph (JI-01).

    Dog.java imports com.synappstest.Formatter and Cat.java imports
    com.synappstest.Animal — both should create IMPORTS edges from the File node
    to the corresponding Class node (not just a Package node).
    """
    result = run(java_mcp.call_tool("execute_query", {
        "cypher": (
            "MATCH (f:File)-[:IMPORTS]->(target) "
            "WHERE f.path CONTAINS 'SynappsJavaTest' "
            "RETURN f.path AS file, target.full_name AS imported, labels(target) AS labels"
        ),
    }))
    data = result_json(result)
    assert isinstance(data, list), f"Expected list, got: {type(data)}"
    assert len(data) >= 1, f"Expected at least 1 IMPORTS edge for Java fixtures, got: {data}"

    imported_names = [row["row"][1] for row in data]

    # At least one import must resolve to a class-level node (full_name ending in PascalCase)
    has_class_import = any(
        name and "." in name and name.rsplit(".", 1)[-1][0].isupper()
        for name in imported_names
    )
    assert has_class_import, (
        f"Expected at least one class-level IMPORTS edge (e.g. to Formatter or Animal), "
        f"got imported names: {imported_names}"
    )


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_main_method_not_in_dead_code(java_mcp: FastMCP) -> None:
    """DEAD-01: Java main(String[]) entry point must NOT appear in find_dead_code results."""
    result = run(java_mcp.call_tool("find_dead_code", {
        "path": JAVA_FIXTURE_PATH,
    }))
    output = text(result)
    # main() has no callers within the project — it would appear as dead code if not excluded.
    # It must be excluded by the name-based filter in _build_base_exclusion_where.
    assert "Application.main" not in output, (
        "main(String[]) entry point appeared in find_dead_code — exclusion is broken"
    )


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_main_method_not_in_untested(java_mcp: FastMCP) -> None:
    """DEAD-02: Java main(String[]) entry point must NOT appear in find_untested results."""
    result = run(java_mcp.call_tool("find_untested", {
        "path": JAVA_FIXTURE_PATH,
    }))
    output = text(result)
    # main() has no TESTS edges — it would appear as untested if not excluded.
    assert "Application.main" not in output, (
        "main(String[]) entry point appeared in find_untested — exclusion is broken"
    )


# ---------------------------------------------------------------------------
# CALL-01 / CALL-02 — Spring Data stub Method nodes
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_spring_data_stub_nodes_exist(java_mcp: FastMCP) -> None:
    """CALL-01/02: search_symbols finds OrderRepository stub methods (save, count)."""
    result = run(java_mcp.call_tool("search_symbols", {
        "query": "OrderRepository.save",
    }))
    symbols = result_json(result)
    assert isinstance(symbols, list)
    assert len(symbols) >= 1, f"Expected at least one OrderRepository.save stub, got: {symbols}"
    full_names = [s.get("full_name", "") for s in symbols]
    assert any("OrderRepository" in fn and "save" in fn for fn in full_names), (
        f"Expected OrderRepository.save in results, got: {full_names}"
    )


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_spring_data_stub_has_stub_property(java_service) -> None:
    """CALL-01/02: Stub Method nodes have stub=true property in the graph."""
    rows = java_service._conn.query(
        "MATCH (m:Method) WHERE m.full_name CONTAINS 'OrderRepository' "
        "AND m.name = 'save' "
        "RETURN m.stub"
    )
    assert rows, "No OrderRepository.save stub found in graph"
    stub_val = rows[0][0]
    assert stub_val is True, f"Expected stub=True, got: {stub_val}"


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_spring_data_callees_resolved(java_mcp: FastMCP) -> None:
    """CALL-03: find_callees for OrderService.createAnimal returns OrderRepository.save stub."""
    result = run(java_mcp.call_tool("find_callees", {
        "full_name": "com.synappstest.OrderService.createAnimal",
    }))
    callees = result_json(result)
    assert isinstance(callees, list), f"Expected list of callees, got: {type(callees)}"
    callee_names = [c.get("full_name", "") for c in callees]
    assert any("OrderRepository" in fn and "save" in fn for fn in callee_names), (
        f"Expected OrderRepository.save callee, got: {callee_names}"
    )


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_spring_data_stubs_excluded_from_dead_code(java_mcp: FastMCP) -> None:
    """CALL-04: find_dead_code does not return any stub Method node."""
    result = run(java_mcp.call_tool("find_dead_code", {}))
    data = result_json(result)
    methods = data.get("methods", [])
    stub_methods = [
        m for m in methods
        if "OrderRepository" in m.get("full_name", "")
    ]
    assert stub_methods == [], (
        f"find_dead_code returned stub methods that should be excluded: {stub_methods}"
    )
