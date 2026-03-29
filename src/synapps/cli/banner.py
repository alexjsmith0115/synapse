from __future__ import annotations

_SYN_COLOR = "#2D6A4F"
_APPS_COLOR = "#74C69D"

# Each tuple is (SYN portion, APPS portion) — split between the N and A letters
_BANNER_LINES: list[tuple[str, str]] = [
    ("   ███████╗██╗   ██╗███╗   ██╗", " █████╗ ██████╗ ██████╗ ███████╗"),
    ("   ██╔════╝╚██╗ ██╔╝████╗  ██║", "██╔══██╗██╔══██╗██╔══██╗██╔════╝"),
    ("   ███████╗ ╚████╔╝ ██╔██╗ ██║", "███████║██████╔╝██████╔╝███████╗"),
    ("   ╚════██║  ╚██╔╝  ██║╚██╗██║", "██╔══██║██╔═══╝ ██╔═══╝ ╚════██║"),
    ("   ███████║   ██║   ██║ ╚████║", "██║  ██║██║     ██║     ███████║"),
    ("   ╚══════╝   ╚═╝   ╚═╝  ╚═══╝", "╚═╝  ╚═╝╚═╝     ╚═╝     ╚══════╝"),
]

_ACCENT = f"[{_APPS_COLOR}]   ○─────────────────────────────────────────────────────────○[/{_APPS_COLOR}]"


def print_banner(console: "Console | None" = None) -> None:
    if console is None:
        from rich.console import Console

        console = Console()

    console.print()
    for syn, apps in _BANNER_LINES:
        console.print(f"[{_SYN_COLOR}]{syn}[/{_SYN_COLOR}][{_APPS_COLOR}]{apps}[/{_APPS_COLOR}]")
    console.print(_ACCENT)
    console.print()
