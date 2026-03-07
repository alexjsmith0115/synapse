from __future__ import annotations

from typing import Any


class GraphConnection:
    """Wraps a FalkorDB Graph object, providing query and execute operations."""

    def __init__(self, graph: Any) -> None:
        self._graph = graph

    @classmethod
    def create(cls, host: str = "localhost", port: int = 6379, graph_name: str = "synapse") -> GraphConnection:
        from falkordb import FalkorDB

        db = FalkorDB(host=host, port=port)
        return cls(db.select_graph(graph_name))

    def query(self, cypher: str, params: dict | None = None) -> list:
        result = self._graph.query(cypher, params or {})
        return result.result_set

    def execute(self, cypher: str, params: dict | None = None) -> None:
        self._graph.query(cypher, params or {})
