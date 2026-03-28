from __future__ import annotations

import logging
import sys
from pathlib import Path

import typer

from synapse.onboarding.language_detector import detect_languages
from synapse.onboarding.mcp_configurator import detect_mcp_clients, write_mcp_config
from synapse.doctor.service import DoctorService
from synapse.container.manager import ConnectionManager
from synapse.graph.schema import ensure_schema
from synapse.service import SynapseService

log = logging.getLogger(__name__)

# Maps language names (as returned by detect_languages) to their doctor check group
_LANGUAGE_TO_GROUP: dict[str, str] = {
    "csharp": "csharp",
    "typescript": "typescript",
    "python": "python",
    "java": "java",
}


def _checks_for_languages(languages: list[str]) -> list:
    """Return doctor check instances for core + the given languages only."""
    from synapse.doctor.checks.docker_daemon import DockerDaemonCheck
    from synapse.doctor.checks.memgraph_bolt import MemgraphBoltCheck
    from synapse.doctor.checks.dotnet import DotNetCheck
    from synapse.doctor.checks.csharp_ls import CSharpLSCheck
    from synapse.doctor.checks.node import NodeCheck
    from synapse.doctor.checks.typescript_ls import TypeScriptLSCheck
    from synapse.doctor.checks.python3 import PythonCheck
    from synapse.doctor.checks.pylsp import PylspCheck
    from synapse.doctor.checks.java import JavaCheck
    from synapse.doctor.checks.jdtls import JdtlsCheck

    _LANGUAGE_CHECKS: dict[str, list] = {
        "csharp": [DotNetCheck(), CSharpLSCheck()],
        "typescript": [NodeCheck(), TypeScriptLSCheck()],
        "python": [PythonCheck(), PylspCheck()],
        "java": [JavaCheck(), JdtlsCheck()],
    }

    checks = [DockerDaemonCheck(), MemgraphBoltCheck()]
    for lang in languages:
        key = lang.lower()
        if key in _LANGUAGE_CHECKS:
            checks.extend(_LANGUAGE_CHECKS[key])
    return checks


def _prompt_language_confirmation(console, detected: list[tuple[str, int]]) -> list[str]:
    """Show detected languages with file counts and ask user to confirm each."""
    confirmed = []
    for name, count in detected:
        if typer.confirm(f"Include {name}? ({count} files)", default=True):
            confirmed.append(name)
    return confirmed


def _show_failures(console, report) -> None:
    """Print each failed check name and fix string."""
    for result in report.checks:
        if result.status == "fail":
            console.print(f"[red]FAIL[/red] {result.name}")
            if result.fix:
                console.print(f"  [dim]Fix:[/dim] {result.fix}")


def _offer_mcp_config(console, project_path: str) -> list[str]:
    """Detect MCP clients and offer to write config for each. Returns configured client names."""
    clients = detect_mcp_clients(project_path)
    configured: list[str] = []
    for client in clients:
        if typer.confirm(f"Configure {client.name}?", default=True):
            write_mcp_config(client.config_path, client.servers_key)
            configured.append(client.name)
    return configured


def _print_summary(console, languages: list[str], report, mcp_clients: list[str]) -> None:
    """Print a Rich table summarizing all wizard actions."""
    from rich.table import Table

    console.print("\n[bold green]Setup complete![/bold green]")

    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
    table.add_column("Item", min_width=24)
    table.add_column("Result", min_width=20)

    if languages:
        table.add_row("Languages detected", ", ".join(languages))
    else:
        table.add_row("Languages detected", "(none)")

    passed = sum(1 for r in report.checks if r.status == "pass")
    failed = sum(1 for r in report.checks if r.status == "fail")
    check_summary = f"{passed} passed"
    if failed:
        check_summary += f", {failed} failed"
    table.add_row("Prerequisite checks", check_summary)

    table.add_row("Project indexed", "yes")

    if mcp_clients:
        table.add_row("MCP clients configured", ", ".join(mcp_clients))
    else:
        table.add_row("MCP clients configured", "(none)")

    console.print(table)


def run_init(project_path: str, verbose: bool = False) -> None:
    """Orchestrate interactive setup: detect languages, check prerequisites, index, configure MCP."""
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

    if not sys.stdin.isatty():
        typer.echo("Error: synapse init requires an interactive terminal (stdin is not a TTY).", err=True)
        raise typer.Exit(1)

    console = Console()
    console.print("[bold]Synapse Init Wizard[/bold]")
    console.print(f"Setting up project: {project_path}\n")

    # Step 1: Detect languages
    detected = detect_languages(project_path)
    if not detected:
        console.print("[yellow]No supported languages detected in this directory.[/yellow]")
        raise typer.Exit(1)

    console.print("[bold]Detected languages:[/bold]")
    for name, count in detected:
        console.print(f"  {name}: {count} files")
    console.print()

    # Step 2: Confirm languages
    confirmed_languages = _prompt_language_confirmation(console, detected)
    if not confirmed_languages:
        console.print("[yellow]No languages selected. Exiting.[/yellow]")
        raise typer.Exit(1)

    # Step 3: Run prerequisite checks
    console.print("\n[bold]Running prerequisite checks...[/bold]")
    checks = _checks_for_languages(confirmed_languages)
    report = DoctorService(checks).run()

    passed = sum(1 for r in report.checks if r.status == "pass")
    failed = sum(1 for r in report.checks if r.status == "fail")
    status_style = "red" if failed else "green"
    console.print(f"[{status_style}]{passed} passed, {failed} failed[/{status_style}]")

    if report.has_failures:
        _show_failures(console, report)
        if not typer.confirm("\nContinue with missing prerequisites?", default=False):
            raise typer.Exit(1)

    # Step 4: Index the project
    console.print("\n[bold]Indexing project...[/bold]")
    conn = ConnectionManager(project_path).get_connection()
    ensure_schema(conn)
    svc = SynapseService(conn)

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), TimeElapsedColumn()) as progress:
        task = progress.add_task("Indexing...", total=None)

        def _on_progress(msg: str) -> None:
            progress.update(task, description=msg)

        index_result = svc.smart_index(project_path, on_progress=_on_progress)

    console.print(f"[green]Indexing complete:[/green] {index_result}")

    # Step 5: Configure MCP clients
    console.print("\n[bold]MCP client configuration:[/bold]")
    configured_clients = _offer_mcp_config(console, project_path)

    # Step 6: Summary
    _print_summary(console, confirmed_languages, report, configured_clients)
