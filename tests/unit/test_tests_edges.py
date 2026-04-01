from __future__ import annotations

import re
from unittest.mock import MagicMock

from synapps.graph.edges import delete_outgoing_edges_for_file
from synapps.graph.lookups import _TEST_PATH_PATTERN
from synapps.indexer.tests_phase import TestsPhase


def _mock_conn():
    """Return a mock GraphConnection with execute and query available."""
    conn = MagicMock()
    return conn


# ---------------------------------------------------------------------------
# _TEST_PATH_PATTERN: Maven/Gradle path matching (D-08)
# ---------------------------------------------------------------------------


def test_maven_src_test_java_path_matches_pattern():
    assert re.fullmatch(_TEST_PATH_PATTERN, "src/test/java/com/foo/BarTest.java")


def test_gradle_src_test_resources_matches_pattern():
    assert re.fullmatch(_TEST_PATH_PATTERN, "src/test/resources/data.xml")


def test_existing_csharp_test_path_still_matches():
    # Pattern requires a directory separator before Tests/ — use a realistic absolute path
    assert re.fullmatch(_TEST_PATH_PATTERN, "/repo/MyApp.Tests/Foo.cs")


def test_existing_jest_test_path_still_matches():
    assert re.fullmatch(_TEST_PATH_PATTERN, "src/__tests__/foo.test.ts")


def test_existing_python_test_path_still_matches():
    # Pattern requires a directory separator before tests/ — use a realistic absolute path
    assert re.fullmatch(_TEST_PATH_PATTERN, "/repo/tests/test_foo.py")


def test_test_utils_directory_matches_pattern():
    assert re.fullmatch(_TEST_PATH_PATTERN, "frontend/src/test-utils/test-wrapper.tsx")


def test_test_helpers_directory_matches_pattern():
    assert re.fullmatch(_TEST_PATH_PATTERN, "src/test-helpers/mock-data.ts")


def test_production_path_does_not_match():
    assert re.fullmatch(_TEST_PATH_PATTERN, "src/main/java/com/foo/Bar.java") is None


# ---------------------------------------------------------------------------
# delete_outgoing_edges_for_file: TESTS must be in edge type list (D-09)
# ---------------------------------------------------------------------------


def test_tests_in_delete_outgoing_edges_edge_types():
    conn = _mock_conn()
    delete_outgoing_edges_for_file(conn, "/foo.py")
    first_call_cypher = conn.execute.call_args_list[0].args[0]
    assert "'TESTS'" in first_call_cypher


# ---------------------------------------------------------------------------
# TestsPhase: repo-scoped edge clearing (D-10)
# ---------------------------------------------------------------------------


def test_tests_phase_clears_repo_scoped_edges_first():
    conn = _mock_conn()
    conn.query.return_value = [(0,)]
    phase = TestsPhase(conn, "/repo")
    phase.run()
    first_call_cypher = conn.execute.call_args_list[0].args[0]
    assert "DELETE" in first_call_cypher
    assert "TESTS" in first_call_cypher
    # Must be scoped to a specific repo, not a global delete
    first_call_params = conn.execute.call_args_list[0].args[1]
    assert "repo" in first_call_params


# ---------------------------------------------------------------------------
# TestsPhase: derivation Cypher creates TESTS edges (D-02)
# ---------------------------------------------------------------------------


def test_tests_phase_derivation_creates_tests_edges():
    conn = _mock_conn()
    conn.query.return_value = [(0,)]
    phase = TestsPhase(conn, "/repo")
    phase.run()
    derivation_cypher = conn.execute.call_args_list[1].args[0]
    assert "MERGE (caller)-[:TESTS]->(callee)" in derivation_cypher


def test_tests_phase_derivation_uses_variable_length_contains():
    """All three steps must use [:CONTAINS*] to reach methods inside classes."""
    conn = _mock_conn()
    conn.query.return_value = [(0,)]
    phase = TestsPhase(conn, "/repo")
    phase.run()
    # Step 1 (DELETE) and Step 2 (MERGE) both go through execute
    for call_args in conn.execute.call_args_list:
        cypher = call_args.args[0]
        # Must use CONTAINS* (variable-length), not bare CONTAINS (single hop)
        assert "CONTAINS*" in cypher, f"Missing variable-length CONTAINS in: {cypher[:80]}..."
    # Step 3 (COUNT) goes through query
    count_cypher = conn.query.call_args_list[0].args[0]
    assert "CONTAINS*" in count_cypher


# ---------------------------------------------------------------------------
# TestsPhase: language-specific test method detection (D-06)
# ---------------------------------------------------------------------------


def test_tests_phase_python_detection_in_cypher():
    conn = _mock_conn()
    conn.query.return_value = [(0,)]
    phase = TestsPhase(conn, "/repo")
    phase.run()
    derivation_cypher = conn.execute.call_args_list[1].args[0]
    assert "caller.language = 'python'" in derivation_cypher
    assert "caller.name STARTS WITH 'test_'" in derivation_cypher


def test_tests_phase_typescript_file_level_detection():
    conn = _mock_conn()
    conn.query.return_value = [(0,)]
    phase = TestsPhase(conn, "/repo")
    phase.run()
    derivation_cypher = conn.execute.call_args_list[1].args[0]
    assert "caller.language = 'typescript'" in derivation_cypher
    # TypeScript detection is file-level only — no per-method name check in TS branch
    # The TS branch should be a simple language equality check, not involve caller.name
    # We verify that the language check appears without a name-based sub-condition
    # by checking the string doesn't combine TS with a STARTS WITH caller.name constraint
    assert "caller.language = 'typescript' AND caller.name" not in derivation_cypher


def test_tests_phase_csharp_attribute_detection():
    conn = _mock_conn()
    conn.query.return_value = [(0,)]
    phase = TestsPhase(conn, "/repo")
    phase.run()
    derivation_cypher = conn.execute.call_args_list[1].args[0]
    assert "caller.language = 'csharp'" in derivation_cypher
    # xUnit
    assert '"Fact"' in derivation_cypher
    assert '"Theory"' in derivation_cypher
    # NUnit
    assert '"Test"' in derivation_cypher
    assert '"TestCase"' in derivation_cypher
    assert '"TestCaseSource"' in derivation_cypher


def test_tests_phase_csharp_mstest_testmethod_detection():
    conn = _mock_conn()
    conn.query.return_value = [(0,)]
    phase = TestsPhase(conn, "/repo")
    phase.run()
    derivation_cypher = conn.execute.call_args_list[1].args[0]
    # MSTest
    assert '"TestMethod"' in derivation_cypher


def test_tests_phase_csharp_mstest_datatestmethod_detection():
    conn = _mock_conn()
    conn.query.return_value = [(0,)]
    phase = TestsPhase(conn, "/repo")
    phase.run()
    derivation_cypher = conn.execute.call_args_list[1].args[0]
    # MSTest
    assert '"DataTestMethod"' in derivation_cypher


def test_tests_phase_java_annotation_detection():
    conn = _mock_conn()
    conn.query.return_value = [(0,)]
    phase = TestsPhase(conn, "/repo")
    phase.run()
    derivation_cypher = conn.execute.call_args_list[1].args[0]
    assert "caller.language = 'java'" in derivation_cypher
    assert '"test"' in derivation_cypher


# ---------------------------------------------------------------------------
# TestsPhase: caller and callee file path filters (D-06)
# ---------------------------------------------------------------------------


def test_tests_phase_only_test_callers():
    conn = _mock_conn()
    conn.query.return_value = [(0,)]
    phase = TestsPhase(conn, "/repo")
    phase.run()
    derivation_cypher = conn.execute.call_args_list[1].args[0]
    assert "caller.file_path =~ $test_pattern" in derivation_cypher


def test_tests_phase_only_prod_callees():
    conn = _mock_conn()
    conn.query.return_value = [(0,)]
    phase = TestsPhase(conn, "/repo")
    phase.run()
    derivation_cypher = conn.execute.call_args_list[1].args[0]
    assert "NOT callee.file_path =~ $test_pattern" in derivation_cypher


def test_tests_phase_passes_test_pattern_param():
    conn = _mock_conn()
    conn.query.return_value = [(0,)]
    phase = TestsPhase(conn, "/repo")
    phase.run()
    derivation_params = conn.execute.call_args_list[1].args[1]
    assert derivation_params["test_pattern"] == _TEST_PATH_PATTERN


# ---------------------------------------------------------------------------
# TestsPhase: count logging (D-10)
# ---------------------------------------------------------------------------


def test_tests_phase_logs_count_of_created_edges(caplog):
    import logging
    conn = _mock_conn()
    conn.query.return_value = [(42,)]
    phase = TestsPhase(conn, "/repo")
    with caplog.at_level(logging.INFO):
        phase.run()
    assert any("42" in record.message for record in caplog.records)
