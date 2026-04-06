from __future__ import annotations

from typing import Literal

from synapps.graph.connection import GraphConnection

# (label, property) pairs — source of truth for all index definitions
_INDEX_DEFS = [
    ("Repository", "path"),
    ("Directory", "path"),
    ("File", "path"),
    ("Package", "full_name"),
    ("Class", "full_name"),
    ("Class", "name"),
    ("Interface", "full_name"),
    ("Interface", "name"),
    ("Method", "full_name"),
    ("Method", "name"),
    ("Method", "file_path"),
    ("Property", "full_name"),
    ("Field", "full_name"),
    ("Endpoint", "route"),
]

# Label-only indexes speed up label-filtered scans (Memgraph only)
_LABEL_INDEX_LABELS = ["Method", "Class", "Interface"]


def _make_index_statement(label: str, prop: str, dialect: Literal["memgraph", "neo4j"]) -> str:
    if dialect == "neo4j":
        return f"CREATE INDEX FOR (n:{label}) ON (n.{prop})"
    return f"CREATE INDEX ON :{label}({prop})"


def _make_label_index_statement(label: str, dialect: Literal["memgraph", "neo4j"]) -> str:
    if dialect == "neo4j":
        return f"CREATE INDEX FOR (n:{label}) ON (n.__placeholder__)"
    return f"CREATE INDEX ON :{label}"


def ensure_schema(conn: GraphConnection) -> None:
    """Create graph indices. Idempotent on Memgraph; safe to re-run."""
    for label, prop in _INDEX_DEFS:
        conn.execute_implicit(_make_index_statement(label, prop, conn.dialect))
    if conn.dialect == "memgraph":
        for label in _LABEL_INDEX_LABELS:
            conn.execute_implicit(_make_label_index_statement(label, conn.dialect))
