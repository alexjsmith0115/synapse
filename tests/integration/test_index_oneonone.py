"""
Integration tests against the oneonone C# project.
Requires FalkorDB running on localhost:6379.
Run with: pytest tests/integration/ -v -m integration
"""

import pytest
from synapse.graph.connection import GraphConnection
from synapse.graph.schema import ensure_schema
from synapse.service import SynapseService

ONEONONE_PATH = "/Users/alex/Dev/oneonone"
CSHARP_BACKEND_PATH = f"{ONEONONE_PATH}/backend"  # adjust if needed


@pytest.fixture(scope="module")
def service() -> SynapseService:
    conn = GraphConnection.create(graph_name="synapse_test")
    ensure_schema(conn)
    # Clear test graph
    conn.execute("MATCH (n) DETACH DELETE n")
    svc = SynapseService(conn)
    return svc


@pytest.mark.integration
@pytest.mark.timeout(120)
def test_index_project_completes(service: SynapseService) -> None:
    service.index_project(CSHARP_BACKEND_PATH, "csharp")
    status = service.get_index_status(CSHARP_BACKEND_PATH)
    assert status is not None
    assert status["file_count"] > 0
    assert status["symbol_count"] > 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_can_query_classes_after_index(service: SynapseService) -> None:
    results = service.search_symbols("Controller", kind="Class")
    assert len(results) > 0


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_set_and_get_summary(service: SynapseService) -> None:
    # Get any class to summarize
    classes = service.search_symbols("", kind="Class")
    assert classes, "No classes found — run test_index_project_completes first"
    full_name = classes[0]["full_name"]

    service.set_summary(full_name, "Test summary content")
    result = service.get_summary(full_name)
    assert result == "Test summary content"

    listed = service.list_summarized()
    names = [n.get("full_name") for n in listed]
    assert full_name in names


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_execute_readonly_query(service: SynapseService) -> None:
    rows = service.execute_query("MATCH (n:Class) RETURN n.name LIMIT 5")
    assert isinstance(rows, list)


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_mutating_query_raises(service: SynapseService) -> None:
    with pytest.raises(ValueError):
        service.execute_query("CREATE (n:Fake) RETURN n")
