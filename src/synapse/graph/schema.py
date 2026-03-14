from __future__ import annotations

from typing import Literal

from synapse.graph.connection import GraphConnection

# (label, property) pairs — source of truth for all index definitions
_INDEX_DEFS = [
    ("Repository", "path"),
    ("Directory", "path"),
    ("File", "path"),
    ("Package", "full_name"),
    ("Class", "full_name"),
    ("Interface", "full_name"),
    ("Method", "full_name"),
    ("Property", "full_name"),
    ("Field", "full_name"),
]


def _make_index_statement(label: str, prop: str, dialect: Literal["memgraph", "neo4j"]) -> str:
    if dialect == "neo4j":
        return f"CREATE INDEX FOR (n:{label}) ON (n.{prop})"
    return f"CREATE INDEX ON :{label}({prop})"


def ensure_schema(conn: GraphConnection) -> None:
    """Create graph indices. Idempotent on Memgraph; safe to re-run."""
    for label, prop in _INDEX_DEFS:
        conn.execute_implicit(_make_index_statement(label, prop, conn.dialect))
