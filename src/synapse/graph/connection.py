from __future__ import annotations

import concurrent.futures
from typing import Literal

from neo4j import GraphDatabase


class GraphConnection:
    """Wraps a neo4j Driver, providing query and execute operations."""

    def __init__(
        self,
        driver,
        database: str = "memgraph",
        dialect: Literal["memgraph", "neo4j"] = "memgraph",
    ) -> None:
        self._driver = driver
        self._database = database
        self._dialect = dialect

    @property
    def dialect(self) -> str:
        return self._dialect

    @classmethod
    def create(
        cls,
        host: str = "localhost",
        port: int = 7687,
        database: str = "memgraph",
        dialect: Literal["memgraph", "neo4j"] = "memgraph",
    ) -> GraphConnection:
        driver = GraphDatabase.driver(f"bolt://{host}:{port}", auth=("", ""))
        return cls(driver, database=database, dialect=dialect)

    def query(self, cypher: str, params: dict | None = None) -> list:
        records, _, _ = self._driver.execute_query(
            cypher, params or {}, database_=self._database
        )
        return records

    def execute(self, cypher: str, params: dict | None = None) -> None:
        self._driver.execute_query(
            cypher, params or {}, database_=self._database
        )

    def execute_implicit(self, cypher: str, params: dict | None = None) -> None:
        """Run a statement in an implicit (auto-commit) transaction.

        Required for DDL statements (e.g. CREATE INDEX) on Memgraph, which
        rejects index manipulation inside explicit multi-command transactions.
        """
        with self._driver.session(database=self._database) as session:
            session.run(cypher, params or {})

    def query_with_timeout(self, cypher: str, params: dict | None = None, timeout_s: float = 10.0) -> list:
        """Run a read query with a client-side timeout.

        Uses a background thread so the calling thread returns promptly on timeout.
        The background database query is not cancelled — it runs to completion
        independently. Raises TimeoutError if the query exceeds timeout_s seconds.
        """
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(self.query, cypher, params)
        try:
            result = future.result(timeout=timeout_s)
        except concurrent.futures.TimeoutError:
            executor.shutdown(wait=False)
            raise TimeoutError(
                f"Query exceeded {timeout_s:.0f}s timeout. Add filters or a LIMIT clause."
            )
        else:
            executor.shutdown(wait=True)
            return result

    def close(self) -> None:
        self._driver.close()
