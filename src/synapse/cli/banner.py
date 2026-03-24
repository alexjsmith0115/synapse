from __future__ import annotations

_DARK = "#2D6A4F"
_LIGHT = "#74C69D"

# B2 block-letter ASCII art: chunky full-block characters spelling "SYNAPSE"
# Alternating dark/light green on each line for a two-tone striped effect
_BANNER_LINES = [
    f"[{_DARK}]███[/{_DARK}][{_LIGHT}]█[/{_LIGHT}][{_DARK}]█[/{_DARK}]  [{_LIGHT}]█[/{_LIGHT}][{_DARK}]█  █[/{_DARK}][{_LIGHT}]█[/{_LIGHT}]  [{_DARK}]██[/{_DARK}][{_LIGHT}]█[/{_LIGHT}][{_DARK}]█[/{_DARK}][{_LIGHT}]█[/{_LIGHT}]  [{_DARK}]███[/{_DARK}][{_LIGHT}]██[/{_LIGHT}]  [{_DARK}]███[/{_DARK}][{_LIGHT}]█[/{_LIGHT}][{_DARK}]█[/{_DARK}]  [{_LIGHT}]███[/{_LIGHT}][{_DARK}]█[/{_DARK}][{_LIGHT}]█[/{_LIGHT}]",
    f"[{_DARK}]█[/{_DARK}]      [{_LIGHT}]█[/{_LIGHT}][{_DARK}]█ █[/{_DARK}][{_LIGHT}]█[/{_LIGHT}]  [{_DARK}]██ █[/{_DARK}][{_LIGHT}]█[/{_LIGHT}]  [{_DARK}]█[/{_DARK}][{_LIGHT}]█  █[/{_LIGHT}][{_DARK}]█[/{_DARK}]  [{_LIGHT}]█[/{_LIGHT}]       [{_DARK}]█[/{_DARK}]    ",
    f"[{_LIGHT}] ███[/{_LIGHT}]   [{_DARK}]██[/{_DARK}][{_LIGHT}]█[/{_LIGHT}][{_DARK}]█[/{_DARK}]   [{_LIGHT}]█[/{_LIGHT}][{_DARK}]█[/{_DARK}][{_LIGHT}]██[/{_LIGHT}][{_DARK}]█[/{_DARK}]  [{_LIGHT}]████[/{_LIGHT}][{_DARK}]█[/{_DARK}]   [{_LIGHT}]███[/{_LIGHT}][{_DARK}]█[/{_DARK}]    [{_LIGHT}]███[/{_LIGHT}][{_DARK}]█[/{_DARK}] ",
    f"[{_DARK}]    █[/{_DARK}]  [{_LIGHT}] █[/{_LIGHT}][{_DARK}]█[/{_DARK}]    [{_LIGHT}]██  █[/{_LIGHT}][{_DARK}]█[/{_DARK}]  [{_LIGHT}]█[/{_LIGHT}][{_DARK}]█[/{_DARK}]       [{_LIGHT}]█[/{_LIGHT}]       [{_DARK}]█[/{_DARK}]    ",
    f"[{_LIGHT}]████[/{_LIGHT}]   [{_DARK}] █[/{_DARK}]    [{_LIGHT}]█[/{_LIGHT}][{_DARK}]█  █[/{_DARK}][{_LIGHT}]█[/{_LIGHT}]  [{_DARK}]█[/{_DARK}][{_LIGHT}]█[/{_LIGHT}]      [{_DARK}]████[/{_DARK}][{_LIGHT}]█[/{_LIGHT}]  [{_DARK}]███[/{_DARK}][{_LIGHT}]█[/{_LIGHT}][{_DARK}]█[/{_DARK}]",
]

_ACCENT_LINE = f"[{_LIGHT}]\u25cb\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u25cb[/{_LIGHT}]"


def print_banner(console: "Console | None" = None) -> None:
    if console is None:
        from rich.console import Console

        console = Console()

    console.print()
    for line in _BANNER_LINES:
        console.print(line)
    console.print(_ACCENT_LINE)
    console.print()
