from __future__ import annotations

from unittest.mock import MagicMock

from synapps.service.context import ContextBuilder


def test_context_impact_returns_formatted_output():
    """scope='impact' should delegate to analyze_change_impact and return markdown."""
    conn = MagicMock()
    service = MagicMock()
    service.analyze_change_impact.return_value = "## Change Impact: Foo.Bar\n\n2 affected"

    builder = ContextBuilder(conn, service=service)
    result = builder.get_context_for("Foo.Bar", scope="impact")

    service.analyze_change_impact.assert_called_once_with("Foo.Bar", structured=False)
    assert "Change Impact" in result


def test_context_impact_without_service_returns_error():
    """scope='impact' without a service reference should return an error message."""
    conn = MagicMock()
    builder = ContextBuilder(conn)
    result = builder.get_context_for("Foo.Bar", scope="impact")

    assert result == "Impact scope requires service reference"
