from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from synapps.indexer.java.external_call_stubs import (
    EXTERNAL_FRAMEWORK_METHODS,
    ExternalCallStubber,
)


# ---------------------------------------------------------------------------
# Allowlist structure tests
# ---------------------------------------------------------------------------


def test_allowlist_has_exactly_8_keys():
    assert len(EXTERNAL_FRAMEWORK_METHODS) == 8


def test_allowlist_contains_expected_types():
    expected = {
        "RestTemplate",
        "MongoTemplate",
        "JdbcTemplate",
        "KafkaTemplate",
        "RabbitTemplate",
        "ObjectMapper",
        "WebClient",
        "DiscoveryClient",
    }
    assert set(EXTERNAL_FRAMEWORK_METHODS.keys()) == expected


def test_each_type_has_at_least_2_methods():
    for type_name, methods in EXTERNAL_FRAMEWORK_METHODS.items():
        assert len(methods) >= 2, f"{type_name} has fewer than 2 methods"


def test_method_lists_are_non_empty_strings():
    for type_name, methods in EXTERNAL_FRAMEWORK_METHODS.items():
        for method in methods:
            assert isinstance(method, str) and method, f"Empty method in {type_name}"


# ---------------------------------------------------------------------------
# ExternalCallStubber.maybe_stub — happy path
# ---------------------------------------------------------------------------


def _make_conn(field_rows: list[list]) -> MagicMock:
    """Return a mock conn whose query() returns field_rows."""
    conn = MagicMock()
    conn.query.return_value = field_rows
    return conn


def test_maybe_stub_returns_full_name_for_allowlisted_hit():
    conn = _make_conn([["restTemplate", "RestTemplate"]])
    stubber = ExternalCallStubber(conn)
    with patch("synapps.indexer.java.external_call_stubs.upsert_method") as mock_upsert:
        result = stubber.maybe_stub(
            caller_full_name="com.example.OrderService.createOrder",
            receiver_name="restTemplate",
            callee_simple_name="exchange",
        )
    assert result == "com.example.OrderService.restTemplate.exchange"
    mock_upsert.assert_called_once()


def test_maybe_stub_calls_upsert_method_with_stub_true():
    conn = _make_conn([["restTemplate", "RestTemplate"]])
    stubber = ExternalCallStubber(conn)
    with patch("synapps.indexer.java.external_call_stubs.upsert_method") as mock_upsert:
        stubber.maybe_stub(
            caller_full_name="com.example.OrderService.createOrder",
            receiver_name="restTemplate",
            callee_simple_name="exchange",
        )
    kwargs = mock_upsert.call_args.kwargs
    assert kwargs.get("stub") is True


def test_stub_full_name_format():
    """Format: {class_prefix}.{receiver_name}.{callee_simple_name}"""
    conn = _make_conn([["mongoOps", "MongoTemplate"]])
    stubber = ExternalCallStubber(conn)
    with patch("synapps.indexer.java.external_call_stubs.upsert_method"):
        result = stubber.maybe_stub(
            caller_full_name="com.example.service.ReportService.generate",
            receiver_name="mongoOps",
            callee_simple_name="find",
        )
    assert result == "com.example.service.ReportService.mongoOps.find"


# ---------------------------------------------------------------------------
# ExternalCallStubber.maybe_stub — None return cases
# ---------------------------------------------------------------------------


def test_maybe_stub_returns_none_for_none_receiver():
    conn = _make_conn([])
    stubber = ExternalCallStubber(conn)
    result = stubber.maybe_stub(
        caller_full_name="com.example.OrderService.createOrder",
        receiver_name=None,
        callee_simple_name="exchange",
    )
    assert result is None


def test_maybe_stub_returns_none_for_non_allowlisted_type():
    conn = _make_conn([["orderRepository", "OrderRepository"]])
    stubber = ExternalCallStubber(conn)
    with patch("synapps.indexer.java.external_call_stubs.upsert_method") as mock_upsert:
        result = stubber.maybe_stub(
            caller_full_name="com.example.OrderService.createOrder",
            receiver_name="orderRepository",
            callee_simple_name="save",
        )
    assert result is None
    mock_upsert.assert_not_called()


def test_maybe_stub_returns_none_for_unknown_method():
    conn = _make_conn([["restTemplate", "RestTemplate"]])
    stubber = ExternalCallStubber(conn)
    with patch("synapps.indexer.java.external_call_stubs.upsert_method") as mock_upsert:
        result = stubber.maybe_stub(
            caller_full_name="com.example.OrderService.createOrder",
            receiver_name="restTemplate",
            callee_simple_name="unknownMethod",
        )
    assert result is None
    mock_upsert.assert_not_called()


def test_maybe_stub_returns_none_when_receiver_not_in_field_map():
    """Receiver name does not appear in the class's field map at all."""
    conn = _make_conn([])  # no fields returned
    stubber = ExternalCallStubber(conn)
    with patch("synapps.indexer.java.external_call_stubs.upsert_method") as mock_upsert:
        result = stubber.maybe_stub(
            caller_full_name="com.example.OrderService.createOrder",
            receiver_name="restTemplate",
            callee_simple_name="exchange",
        )
    assert result is None
    mock_upsert.assert_not_called()


def test_maybe_stub_returns_none_for_caller_with_no_dot():
    """caller_full_name without a dot cannot yield a class prefix — return None."""
    conn = _make_conn([["restTemplate", "RestTemplate"]])
    stubber = ExternalCallStubber(conn)
    result = stubber.maybe_stub(
        caller_full_name="toplevel",
        receiver_name="restTemplate",
        callee_simple_name="exchange",
    )
    assert result is None


# ---------------------------------------------------------------------------
# Field-type caching
# ---------------------------------------------------------------------------


def test_field_type_map_is_cached():
    """Second call for same class should NOT re-query the graph."""
    conn = _make_conn([["restTemplate", "RestTemplate"]])
    stubber = ExternalCallStubber(conn)
    with patch("synapps.indexer.java.external_call_stubs.upsert_method"):
        stubber.maybe_stub(
            caller_full_name="com.example.OrderService.createOrder",
            receiver_name="restTemplate",
            callee_simple_name="exchange",
        )
        stubber.maybe_stub(
            caller_full_name="com.example.OrderService.deleteOrder",
            receiver_name="restTemplate",
            callee_simple_name="delete",
        )
    # Both calls share the same class prefix "com.example.OrderService"
    assert conn.query.call_count == 1
