from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def test_create_app_returns_fastapi_instance() -> None:
    from fastapi import FastAPI
    from synapps.web.app import create_app

    mock_service = MagicMock()
    app = create_app(mock_service)

    assert isinstance(app, FastAPI)


def test_create_app_docs_url_is_none() -> None:
    from synapps.web.app import create_app

    mock_service = MagicMock()
    app = create_app(mock_service)

    assert app.docs_url is None
