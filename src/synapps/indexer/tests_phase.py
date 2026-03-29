from __future__ import annotations

import logging

from synapps.graph.connection import GraphConnection
from synapps.graph.lookups import _TEST_PATH_PATTERN

log = logging.getLogger(__name__)


class TestsPhase:
    """Post-index phase: derive TESTS edges from CALLS edges.

    A test method that CALLS a production method also TESTS it.
    TESTS edges coexist with CALLS edges (D-02) for semantic clarity.
    """

    def __init__(self, conn: GraphConnection, repo_path: str) -> None:
        self._conn = conn
        self._repo_path = repo_path

    def run(self) -> None:
        # Step 1: Clear existing TESTS edges scoped to this repo (D-10)
        self._conn.execute(
            "MATCH (r:Repository {path: $repo})-[:CONTAINS*]->(f:File)"
            "-[:CONTAINS*]->(caller:Method)-[t:TESTS]->() "
            "DELETE t",
            {"repo": self._repo_path},
        )

        # Step 2: Derive TESTS edges from CALLS where caller is test, callee is prod.
        # Language-specific detection per D-06:
        #   Python:     test_ prefix + test file
        #   TypeScript: any method in test file (Jest test()/it() not Method nodes)
        #   C#:         [Fact] or [Theory] attribute + test file
        #   Java:       @Test annotation + test file
        # Attribute detection uses string CONTAINS on JSON (D-07, no APOC in Memgraph).
        self._conn.execute(
            "MATCH (caller:Method)-[:CALLS]->(callee:Method) "
            "WHERE caller.file_path =~ $test_pattern "
            "AND NOT callee.file_path =~ $test_pattern "
            "AND ("
            "  (caller.language = 'python' AND caller.name STARTS WITH 'test_')"
            "  OR caller.language = 'typescript'"
            "  OR (caller.language = 'csharp' AND ("
            "    coalesce(caller.attributes, '[]') CONTAINS '\"Fact\"'"
            "    OR coalesce(caller.attributes, '[]') CONTAINS '\"Theory\"'"
            "  ))"
            "  OR (caller.language = 'java' AND"
            "    coalesce(caller.attributes, '[]') CONTAINS '\"test\"')"
            ") "
            "MERGE (caller)-[:TESTS]->(callee)",
            {"test_pattern": _TEST_PATH_PATTERN},
        )

        # Step 3: Log count of created TESTS edges scoped to this repo
        rows = self._conn.query(
            "MATCH (r:Repository {path: $repo})-[:CONTAINS*]->(f:File)"
            "-[:CONTAINS*]->(caller:Method)-[:TESTS]->() "
            "RETURN count(*)",
            {"repo": self._repo_path},
        )
        count = rows[0][0] if rows else 0
        log.info("TESTS edges created: %d", count)
