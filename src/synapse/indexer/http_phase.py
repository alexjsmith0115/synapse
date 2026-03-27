from __future__ import annotations

import logging
from collections import defaultdict

from synapse.graph.connection import GraphConnection
from synapse.graph.edges import (
    batch_upsert_http_calls,
    batch_upsert_serves,
    delete_orphan_endpoints,
)
from synapse.graph.nodes import upsert_endpoint
from synapse.indexer.http.interface import HttpExtractionResult
from synapse.indexer.http.matcher import match_endpoints

log = logging.getLogger(__name__)


class HttpPhase:
    """Phase 4: HTTP endpoint extraction, matching, and graph writes."""

    def __init__(self, conn: GraphConnection, repo_path: str) -> None:
        self._conn = conn
        self._repo_path = repo_path

    def run(self, extraction_results: list[HttpExtractionResult]) -> None:
        all_defs = []
        all_calls = []
        for result in extraction_results:
            all_defs.extend(result.endpoint_defs)
            all_calls.extend(result.client_calls)

        if not all_defs and not all_calls:
            return

        # Clear existing HTTP edges before re-creating them to avoid stale
        # edges surviving when route normalization changes (e.g. base URL
        # variable stripping).
        self._conn.execute(
            "MATCH (r:Repository {path: $repo})-[:CONTAINS]->(ep:Endpoint)<-[rel]-(m:Method) "
            "WHERE type(rel) IN ['SERVES', 'HTTP_CALLS'] "
            "DELETE rel",
            {"repo": self._repo_path},
        )

        self._warn_route_conflicts(all_defs)

        matched = match_endpoints(all_defs, all_calls)

        serves_batch: list[dict] = []
        http_calls_batch: list[dict] = []

        for m in matched:
            name = f"{m.http_method} {m.route}"
            upsert_endpoint(self._conn, route=m.route, http_method=m.http_method, name=name)

            self._conn.execute(
                "MATCH (r:Repository {path: $repo}), (ep:Endpoint {route: $route, http_method: $http_method}) "
                "MERGE (r)-[:CONTAINS]->(ep)",
                {"repo": self._repo_path, "route": m.route, "http_method": m.http_method},
            )

            if m.endpoint_def is not None:
                serves_batch.append({
                    "handler": m.endpoint_def.handler_full_name,
                    "route": m.route,
                    "http_method": m.http_method,
                })

            for call in m.client_calls:
                http_calls_batch.append({
                    "caller": call.caller_full_name,
                    "route": m.route,
                    "http_method": m.http_method,
                    "line": call.line,
                    "col": call.col,
                })

        batch_upsert_serves(self._conn, serves_batch)
        batch_upsert_http_calls(self._conn, http_calls_batch)

        log.info(
            "HTTP endpoints: %d server endpoints, %d client calls, %d matched",
            len(all_defs),
            len(all_calls),
            sum(1 for m in matched if m.endpoint_def is not None and m.client_calls),
        )

    def _warn_route_conflicts(self, all_defs: list) -> None:
        groups: dict[tuple[str, str], list] = defaultdict(list)
        for ep in all_defs:
            groups[(ep.http_method, ep.route)].append(ep)
        for (http_method, route), handlers in groups.items():
            if len(handlers) >= 2:
                handler_list = ", ".join(
                    f"{h.handler_full_name} (line {h.line})" for h in handlers
                )
                log.warning(
                    "Route conflict: %s %s is served by multiple handlers: %s",
                    http_method,
                    route,
                    handler_list,
                )

    def rebuild_from_graph(self) -> tuple[list, list]:
        """Reconstruct endpoint defs and client calls from existing graph data.

        Used during sync to get data for unchanged files.
        """
        from synapse.indexer.http.interface import HttpEndpointDef, HttpClientCall

        raw_defs = self._conn.query(
            "MATCH (m:Method)-[:SERVES]->(ep:Endpoint)<-[:CONTAINS]-(r:Repository {path: $repo}) "
            "RETURN ep.route, ep.http_method, m.full_name, m.line",
            {"repo": self._repo_path},
        )
        defs = [
            HttpEndpointDef(route=r[0], http_method=r[1], handler_full_name=r[2], line=r[3] or 0)
            for r in raw_defs
        ]

        raw_calls = self._conn.query(
            "MATCH (m:Method)-[r:HTTP_CALLS]->(ep:Endpoint)<-[:CONTAINS]-(repo:Repository {path: $repo}) "
            "RETURN ep.route, ep.http_method, m.full_name, m.line",
            {"repo": self._repo_path},
        )
        calls = [
            HttpClientCall(route=r[0], http_method=r[1], caller_full_name=r[2], line=r[3] or 0, col=0)
            for r in raw_calls
        ]

        return defs, calls

    def cleanup_orphans(self) -> None:
        delete_orphan_endpoints(self._conn, self._repo_path)
