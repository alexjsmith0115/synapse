from __future__ import annotations

_DARK = "#2D6A4F"
_LIGHT = "#74C69D"

_BANNER_LINES: list[tuple[str, str]] = [
    ("   ███████╗██╗   ██╗███╗   ██╗ █████╗ ██████╗ ███████╗███████╗", _DARK),
    ("   ██╔════╝╚██╗ ██╔╝████╗  ██║██╔══██╗██╔══██╗██╔════╝██╔════╝", _DARK),
    ("   ███████╗ ╚████╔╝ ██╔██╗ ██║███████║██████╔╝███████╗█████╗  ", _LIGHT),
    ("   ╚════██║  ╚██╔╝  ██║╚██╗██║██╔══██║██╔═══╝ ╚════██║██╔══╝  ", _LIGHT),
    ("   ███████║   ██║   ██║ ╚████║██║  ██║██║     ███████║███████╗", _DARK),
    ("   ╚══════╝   ╚═╝   ╚═╝  ╚═══╝╚═╝  ╚═╝╚═╝     ╚══════╝╚══════╝", _DARK),
]

_ACCENT = f"[{_LIGHT}]   ○─────────────────────────────────────────────────────────○[/{_LIGHT}]"


def print_banner(console: "Console | None" = None) -> None:
    if console is None:
        from rich.console import Console

        console = Console()

    console.print()
    for text, color in _BANNER_LINES:
        console.print(f"[{color}]{text}[/{color}]")
    console.print(_ACCENT)
    console.print()
