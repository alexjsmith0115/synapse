from __future__ import annotations

import logging

from synapps.graph.connection import GraphConnection
from synapps.graph.nodes import upsert_method

log = logging.getLogger(__name__)

EXTERNAL_FRAMEWORK_METHODS: dict[str, tuple[str, ...]] = {
    "RestTemplate": (
        "exchange", "getForObject", "getForEntity", "postForObject", "postForEntity",
        "put", "delete", "patchForObject", "execute", "headForHeaders", "optionsForAllow",
    ),
    "MongoTemplate": (
        "save", "insert", "find", "findById", "findOne", "findAll", "count",
        "remove", "update", "updateFirst", "updateMulti", "upsert", "exists",
        "aggregate", "query",
    ),
    "JdbcTemplate": (
        "query", "queryForObject", "queryForList", "queryForMap", "queryForRowSet",
        "update", "batchUpdate", "execute",
    ),
    "KafkaTemplate": (
        "send", "sendDefault", "flush", "executeInTransaction",
    ),
    "RabbitTemplate": (
        "send", "convertAndSend", "convertSendAndReceive", "receiveAndConvert",
        "receive", "execute", "invoke",
    ),
    "ObjectMapper": (
        "writeValueAsString", "writeValueAsBytes", "readValue", "readTree",
        "convertValue", "treeToValue", "valueToTree",
    ),
    "WebClient": (
        "get", "post", "put", "delete", "patch", "head", "options",
        "method", "mutate", "build",
    ),
    "DiscoveryClient": (
        "getInstances", "getServices", "description",
    ),
}


class ExternalCallStubber:
    """
    Creates synthetic Method stub nodes for calls to external framework types
    (RestTemplate, MongoTemplate, etc.) so CALLS edges can be recorded.

    Receiver type is resolved via a graph query on Field nodes; results are
    cached per enclosing class to avoid redundant round-trips.
    """

    def __init__(self, conn: GraphConnection, language: str = "java") -> None:
        self._conn = conn
        self._language = language
        self._field_type_cache: dict[str, dict[str, str]] = {}

    def maybe_stub(
        self,
        caller_full_name: str,
        receiver_name: str | None,
        callee_simple_name: str,
    ) -> str | None:
        """
        If receiver_name's declared type is in the allowlist and callee_simple_name
        is in that type's method list, upsert a stub Method node and return its full_name.
        Returns None if no stub should be created.
        """
        if not receiver_name or not callee_simple_name:
            return None

        dot = caller_full_name.rfind(".")
        if dot < 0:
            return None
        class_prefix = caller_full_name[:dot]

        field_type_map = self._get_field_types(class_prefix)
        receiver_type = field_type_map.get(receiver_name)
        if not receiver_type:
            return None

        allowed_methods = EXTERNAL_FRAMEWORK_METHODS.get(receiver_type)
        if not allowed_methods or callee_simple_name not in allowed_methods:
            return None

        stub_full_name = f"{class_prefix}.{receiver_name}.{callee_simple_name}"
        upsert_method(
            self._conn,
            full_name=stub_full_name,
            name=callee_simple_name,
            signature=callee_simple_name,
            is_abstract=False,
            is_static=False,
            file_path="",
            line=None,
            end_line=0,
            language=self._language,
            stub=True,
        )
        log.debug("External stub created: %s", stub_full_name)
        return stub_full_name

    def _get_field_types(self, class_prefix: str) -> dict[str, str]:
        """Query graph for Field nodes on the class and return {field_name: type_name}."""
        cached = self._field_type_cache.get(class_prefix)
        if cached is not None:
            return cached
        rows = self._conn.query(
            "MATCH (f:Field) WHERE f.full_name STARTS WITH $prefix "
            "AND f.type_name IS NOT NULL AND f.type_name <> '' "
            "RETURN f.name, f.type_name",
            {"prefix": class_prefix + "."},
        )
        result = {name: type_name for name, type_name in rows}
        self._field_type_cache[class_prefix] = result
        return result
