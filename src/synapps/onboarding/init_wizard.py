from __future__ import annotations

import logging
import sys
from pathlib import Path

import typer

import json

import docker
import docker.errors

from synapps.onboarding.language_detector import detect_languages
from synapps.onboarding.mcp_configurator import detect_mcp_clients, write_mcp_config
from synapps.doctor.service import DoctorService
from synapps.container.manager import ConnectionManager, _docker_start_command
from synapps.graph.schema import ensure_schema
from synapps.service import SynappsService

log = logging.getLogger(__name__)

# Maps language names (as returned by detect_languages) to their doctor check group
_LANGUAGE_TO_GROUP: dict[str, str] = {
    "csharp": "csharp",
    "typescript": "typescript",
    "python": "python",
    "java": "java",
}

_ALL_HARNESSES: list[tuple[str, str]] = [
    ("claude", "Claude Code"),
    ("cursor", "Cursor"),
    ("copilot", "GitHub Copilot"),
]


def _checks_for_languages(languages: list[str]) -> list:
    """Return doctor check instances for the given languages only.

    Docker and Memgraph are handled separately by run_init (Docker is
    verified early, Memgraph is auto-started via ConnectionManager), so
    they are not included here.
    """
    from synapps.doctor.checks.dotnet import DotNetCheck
    from synapps.doctor.checks.csharp_ls import CSharpLSCheck
    from synapps.doctor.checks.node import NodeCheck
    from synapps.doctor.checks.typescript_ls import TypeScriptLSCheck
    from synapps.doctor.checks.python3 import PythonCheck
    from synapps.doctor.checks.pylsp import PylspCheck
    from synapps.doctor.checks.java import JavaCheck
    from synapps.doctor.checks.jdtls import JdtlsCheck

    _LANGUAGE_CHECKS: dict[str, list] = {
        "csharp": [DotNetCheck(), CSharpLSCheck()],
        "typescript": [NodeCheck(), TypeScriptLSCheck()],
        "python": [PythonCheck(), PylspCheck()],
        "java": [JavaCheck(), JdtlsCheck()],
    }

    checks: list = []
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


def _has_existing_db_config(project_path: str) -> bool:
    """Check if the project already has a database configuration."""
    config_path = Path(project_path) / ".synapps" / "config.json"
    if not config_path.exists():
        return False
    try:
        config = json.loads(config_path.read_text())
        return "dedicated_instance" in config
    except (json.JSONDecodeError, OSError):
        return False


def _write_db_config(project_path: str, dedicated: bool) -> None:
    """Write the dedicated_instance flag to the project's .synapps/config.json."""
    config_path = Path(project_path) / ".synapps" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config: dict = {}
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    config["dedicated_instance"] = dedicated
    config_path.write_text(json.dumps(config, indent=2))


def _prompt_db_mode(console, project_path: str) -> None:
    """Ask the user whether to use shared or dedicated Memgraph and persist the choice."""
    console.print("\n[bold]Database mode:[/bold]")
    console.print("  [bold]Shared[/bold]   — one Memgraph instance for all projects (recommended)")
    console.print("  [bold]Dedicated[/bold] — separate Memgraph container for this project\n")

    dedicated = not typer.confirm("Use shared database?", default=True)
    _write_db_config(project_path, dedicated)

    if dedicated:
        console.print("[dim]This project will use its own Memgraph container.[/dim]")
    else:
        console.print("[dim]This project will share the global Memgraph instance.[/dim]")


def _prompt_multiselect(
    console,
    items: list[tuple[str, str]],
    pre_checked: set[str],
    prompt_label: str,
) -> list[str]:
    """Interactive list menu — enter toggles items, 'Continue' advances."""
    import sys
    from InquirerPy import inquirer
    from InquirerPy.separator import Separator

    enabled = set(pre_checked)
    _CONTINUE = "__continue__"

    while True:
        choices = []
        for name, display in items:
            marker = "x" if name in enabled else " "
            choices.append({"name": f"[{marker}] {display}", "value": name})
        choices.append(Separator())
        choices.append({"name": "Continue", "value": _CONTINUE})

        picked = inquirer.select(
            message=prompt_label,
            choices=choices,
            instruction="(enter to toggle, select Continue when done)",
        ).execute()

        if picked == _CONTINUE:
            break
        if picked in enabled:
            enabled.discard(picked)
        else:
            enabled.add(picked)
        # Erase the "? prompt: answer" line InquirerPy prints after selection
        sys.stdout.write("\033[A\033[2K")
        sys.stdout.flush()

    return [name for name, _ in items if name in enabled]


def _configure_agents(console, project_path: str) -> tuple[list[str], list[str], list[str]]:
    """Unified agent configuration: harness selection + global install options.

    Returns (configured_mcp_clients, hook_agents, agent_files).
    """
    from synapps.hooks.detector import detect_agents
    from synapps.hooks.installer import install_scripts
    from synapps.hooks.config_upsert import (
        upsert_claude_hook,
        upsert_cursor_hook,
        upsert_copilot_hook,
    )
    from synapps.onboarding.agent_instructions import install_agent_instructions

    agents = detect_agents(project_path=Path(project_path))
    detected_names = {a.name for a in agents}
    agent_by_name = {a.name: a for a in agents}

    clients = detect_mcp_clients(project_path)
    client_by_name: dict[str, object] = {}
    for c in clients:
        lower = c.name.lower()
        if "claude" in lower:
            client_by_name["claude"] = c
        elif "cursor" in lower:
            client_by_name["cursor"] = c
        elif "copilot" in lower:
            client_by_name["copilot"] = c

    pre_checked = detected_names | set(client_by_name.keys())
    selected_harnesses = _prompt_multiselect(
        console, _ALL_HARNESSES, pre_checked, "AI agent harnesses:"
    )

    if not selected_harnesses:
        return [], [], []

    console.print("\n[bold]What to install for selected harnesses:[/bold]")
    install_mcp = typer.confirm("  MCP configuration?", default=True)
    install_hooks = typer.confirm("  Pre-tool hooks?", default=True)
    install_instructions = typer.confirm("  Agent instruction files?", default=True)

    _UPSERT = {
        "claude": upsert_claude_hook,
        "cursor": upsert_cursor_hook,
        "copilot": upsert_copilot_hook,
    }
    _SCRIPT_NAME = {
        "claude": "claude-gate.sh",
        "cursor": "cursor-gate.sh",
        "copilot": "copilot-gate.sh",
    }

    hooks_dir = Path.home() / ".synapps" / "hooks"
    configured_clients: list[str] = []
    hook_agents: list[str] = []

    for harness_name in selected_harnesses:
        if install_mcp and harness_name in client_by_name:
            client = client_by_name[harness_name]
            write_mcp_config(client.config_path, client.servers_key)
            configured_clients.append(client.name)

        if install_hooks and harness_name in agent_by_name and harness_name in _UPSERT:
            agent = agent_by_name[harness_name]
            install_scripts(hooks_dir)
            script_path = f"~/.synapps/hooks/{_SCRIPT_NAME[harness_name]}"
            _UPSERT[harness_name](agent.config_path, script_path)
            hook_agents.append(agent.display_name)

    agent_files: list[str] = []
    if install_instructions:
        agent_files = install_agent_instructions(Path(project_path), harnesses=selected_harnesses)

    return configured_clients, hook_agents, agent_files


def _print_summary(console, languages: list[str], report, mcp_clients: list[str], project_path: str, hook_agents: list[str] | None = None, agent_files: list[str] | None = None, indexed: bool = True) -> None:
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

    from synapps.config import is_dedicated_instance
    db_mode = "dedicated" if is_dedicated_instance(project_path) else "shared"
    table.add_row("Database mode", db_mode)

    if report is not None:
        passed = sum(1 for r in report.checks if r.status == "pass")
        failed = sum(1 for r in report.checks if r.status == "fail")
        check_summary = f"{passed} passed"
        if failed:
            check_summary += f", {failed} failed"
        table.add_row("Prerequisite checks", check_summary)

    if indexed:
        table.add_row("Project indexed", "yes")
    else:
        table.add_row("Project indexed", "skipped (run `synapps index <path>` to index)")

    if mcp_clients:
        table.add_row("MCP clients configured", ", ".join(mcp_clients))
    else:
        table.add_row("MCP clients configured", "(none)")

    if hook_agents:
        table.add_row("Agent hooks installed", ", ".join(hook_agents))

    if agent_files:
        table.add_row("Agent instructions", ", ".join(agent_files))

    console.print(table)


def run_init(project_path: str, verbose: bool = False) -> None:
    """Orchestrate interactive setup: detect languages, check prerequisites, index, configure MCP."""
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

    if not sys.stdin.isatty():
        typer.echo("Error: synapps init requires an interactive terminal (stdin is not a TTY).", err=True)
        raise typer.Exit(1)

    console = Console()
    console.print("[bold]Synapps Init Wizard[/bold]")
    console.print(f"Setting up project: {project_path}\n")

    # Step 0: Verify Docker is running (hard requirement)
    console.print("[bold]Checking Docker...[/bold]")
    try:
        docker.from_env().ping()
        console.print("[green]Docker is running[/green]\n")
    except docker.errors.DockerException:
        console.print(
            f"[red]Docker is not running.[/red]\n"
            f"  Start it: {_docker_start_command()}\n"
            f"  Then re-run: synapps init {project_path}",
        )
        raise typer.Exit(1)

    # Step 0.5: Ask whether to index
    want_index = typer.confirm("Index this project now?", default=True)

    if not want_index:
        # Persist DB config even when skipping indexing
        if not _has_existing_db_config(project_path):
            _prompt_db_mode(console, project_path)
        # Skip to agent configuration
        console.print("\n[bold]Agent configuration:[/bold]")
        configured_clients, hook_agents, agent_files = _configure_agents(console, project_path)
        _print_summary(console, [], None, configured_clients, project_path, hook_agents, agent_files, indexed=False)
        return

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

    # Step 3.5: Ask shared vs dedicated database (only on first init)
    if not _has_existing_db_config(project_path):
        _prompt_db_mode(console, project_path)

    # Step 4: Start Memgraph and index the project
    console.print("\n[bold]Starting Memgraph...[/bold]")
    conn = ConnectionManager(project_path).get_connection()
    console.print("[green]Memgraph is ready[/green]")
    console.print("\n[bold]Indexing project...[/bold]")
    ensure_schema(conn)
    svc = SynappsService(conn)

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), TimeElapsedColumn()) as progress:
        task = progress.add_task("Indexing...", total=None)

        def _on_progress(msg: str) -> None:
            progress.update(task, description=msg)

        index_result = svc.smart_index(project_path, on_progress=_on_progress, allowed_languages=confirmed_languages)

    console.print(f"[green]Indexing complete:[/green] {index_result}")

    # Step 5: Unified agent configuration
    console.print("\n[bold]Agent configuration:[/bold]")
    configured_clients, hook_agents, agent_files = _configure_agents(console, project_path)

    # Step 6: Summary
    _print_summary(console, confirmed_languages, report, configured_clients, project_path, hook_agents, agent_files)
