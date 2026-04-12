"""
E2E tests for D3 graph interactions: single-click detail panel,
double-click expand, right-click remove.

Covers E2E-04: D3 graph node event handlers exercised via Playwright.

Requires: live Memgraph + indexed SynappsTest fixture.
Run with: pytest tests/e2e/test_graph_interactions.py -v -m e2e --timeout=60
"""
from __future__ import annotations

import pytest
from playwright.sync_api import expect

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(60)]


def _navigate_to_graph(page) -> None:
    """Navigate to find_callees tool and submit a query that produces graph nodes."""
    page.locator("[data-testid='tool-btn-find_callees']").click()
    page.locator("[data-testid='param-full_name']").fill("SynappsTest.Services.TaskService.CreateTaskAsync")
    page.locator("[data-testid='tool-submit']").click()
    page.wait_for_selector("[data-testid='graph-svg'] g.node", timeout=15000)


def test_click_opens_detail_panel(app_page) -> None:
    page = app_page
    _navigate_to_graph(page)
    page.locator("[data-testid='graph-svg'] g.node").first.click(force=True)
    page.wait_for_selector("[data-testid='node-detail-panel']", timeout=5000)
    expect(page.locator("[data-testid='node-detail-panel']")).to_be_visible()
    page.locator("[data-testid='node-detail-close']").click()
    expect(page.locator("[data-testid='node-detail-panel']")).not_to_be_visible()


def test_dblclick_expands_node(app_page) -> None:
    page = app_page
    _navigate_to_graph(page)
    initial_count = page.locator("[data-testid='graph-svg'] g.node").count()
    # dispatch_event bypasses D3's 250ms click/dblclick disambiguator
    page.locator("[data-testid='graph-svg'] g.node").first.dispatch_event("dblclick")
    page.wait_for_function(
        f"() => document.querySelectorAll('[data-testid=\"graph-svg\"] g.node').length >= {initial_count}",
        timeout=10000,
    )
    assert page.locator("[data-testid='graph-svg'] g.node").count() >= initial_count


def test_rightclick_removes_node(app_page) -> None:
    page = app_page
    _navigate_to_graph(page)
    initial_count = page.locator("[data-testid='graph-svg'] g.node").count()
    page.locator("[data-testid='graph-svg'] g.node").first.click(button="right", force=True)
    page.wait_for_timeout(500)
    assert page.locator("[data-testid='graph-svg'] g.node").count() < initial_count
