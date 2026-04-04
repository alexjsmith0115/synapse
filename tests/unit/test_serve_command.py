from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from synapps.cli.app import app


runner = CliRunner()


def test_serve_command_is_registered() -> None:
    result = runner.invoke(app, ["serve", "--help"])
    assert result.exit_code == 0
    assert "serve" in result.output or "Start" in result.output


def test_serve_calls_uvicorn_run() -> None:
    mock_conn = MagicMock()
    mock_svc = MagicMock()
    mock_web_app = MagicMock()

    with (
        patch("synapps.cli.app.ConnectionManager") as mock_cm,
        patch("synapps.cli.app.ensure_schema") as mock_schema,
        patch("synapps.cli.app.SynappsService", return_value=mock_svc) as mock_svc_cls,
        patch("synapps.web.app.create_app", return_value=mock_web_app),
        patch("uvicorn.run") as mock_uvicorn,
    ):
        mock_cm.return_value.get_connection.return_value = mock_conn

        result = runner.invoke(app, ["serve", "--port", "9999", "--no-open"])

    assert result.exit_code == 0
    mock_uvicorn.assert_called_once()
    call_kwargs = mock_uvicorn.call_args
    assert call_kwargs.kwargs.get("host") == "127.0.0.1" or call_kwargs.args[1] == "127.0.0.1"
    assert call_kwargs.kwargs.get("port") == 9999 or call_kwargs.args[2] == 9999


def test_serve_no_open_does_not_open_browser() -> None:
    mock_conn = MagicMock()
    mock_svc = MagicMock()
    mock_web_app = MagicMock()

    with (
        patch("synapps.cli.app.ConnectionManager") as mock_cm,
        patch("synapps.cli.app.ensure_schema"),
        patch("synapps.cli.app.SynappsService", return_value=mock_svc),
        patch("synapps.web.app.create_app", return_value=mock_web_app),
        patch("uvicorn.run"),
        patch("webbrowser.open") as mock_browser,
    ):
        mock_cm.return_value.get_connection.return_value = mock_conn

        result = runner.invoke(app, ["serve", "--no-open"])

    assert result.exit_code == 0
    mock_browser.assert_not_called()
