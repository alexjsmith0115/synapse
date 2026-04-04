from __future__ import annotations

from io import StringIO

from rich.console import Console

from synapps.cli.banner import print_banner, _BANNER_LINES, _ACCENT, _SYN_COLOR, _APPS_COLOR


def _capture_banner() -> str:
    """Render banner to a string via a Console writing to StringIO (truecolor)."""
    buf = StringIO()
    console = Console(file=buf, force_terminal=True, color_system="truecolor")
    print_banner(console=console)
    return buf.getvalue()


def test_banner_contains_block_characters():
    output = _capture_banner()
    assert "\u2588" in output  # █ full block character present


def test_banner_lines_spell_synapps():
    joined = " ".join(text for text, _ in _BANNER_LINES)
    assert "\u2588" in joined


def test_banner_contains_accent_line_circles():
    output = _capture_banner()
    assert "\u25cb" in output  # ○ circle character


def test_banner_uses_rich_console_di():
    """print_banner() accepts an injected Console and renders to it."""
    buf = StringIO()
    console = Console(file=buf, force_terminal=True, color_system="truecolor")
    print_banner(console=console)
    assert len(buf.getvalue()) > 0


def test_banner_contains_dark_green_color():
    output = _capture_banner()
    # #2D6A4F = RGB(45, 106, 79) -- appears in ANSI escape as 45;106;79
    assert "45;106;79" in output


def test_banner_contains_light_green_color():
    output = _capture_banner()
    # #74C69D = RGB(116, 198, 157) -- appears in ANSI escape as 116;198;157
    assert "116;198;157" in output


def test_banner_accent_line_uses_light_green():
    assert "#74C69D" in _ACCENT or "#74c69d" in _ACCENT


