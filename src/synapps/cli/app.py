from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated, Optional

import typer

# Suppress INFO/WARNING chatter from the language server process — only surface errors.
logging.getLogger("solidlsp").setLevel(logging.ERROR)

from synapps.container import ConnectionManager
from synapps.doctor.checks.docker_daemon import DockerDaemonCheck
from synapps.doctor.checks.memgraph_bolt import MemgraphBoltCheck
from synapps.doctor.checks.dotnet import DotNetCheck
from synapps.doctor.checks.csharp_ls import CSharpLSCheck
from synapps.doctor.checks.node import NodeCheck
from synapps.doctor.checks.typescript_ls import TypeScriptLSCheck
from synapps.doctor.checks.python3 import PythonCheck
from synapps.doctor.checks.pylsp import PylspCheck
from synapps.doctor.checks.java import JavaCheck
from synapps.doctor.checks.jdtls import JdtlsCheck
from synapps.doctor.service import DoctorService
from synapps.cli.banner import print_banner
from synapps.graph.schema import ensure_schema
from synapps.service import SynappsService
from synapps.cli.tree import (
    render_tree,
    callers_tree,
    callees_tree,
    hierarchy_tree,
    trace_tree,
    entry_points_tree,
    dependencies_tree,
)

def _verbose_callback(verbose: bool) -> None:
    if verbose:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


app = typer.Typer(name="synapps", help="LSP-powered codebase graph tool")


@app.callback()
def main(
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable debug logging")] = False,
) -> None:
    _verbose_callback(verbose)
summary_app = typer.Typer(name="summary", help="Get, set, or list symbol summaries.")
app.add_typer(summary_app, name="summary", rich_help_panel="Symbol Queries")

_svc: SynappsService | None = None
_svc_path: str | None = None


def _get_service(project_path: str | None = None) -> SynappsService:
    global _svc, _svc_path
    resolved = project_path or str(Path.cwd())
    if _svc is not None and resolved != _svc_path:
        _svc = None
    if _svc is None:
        conn = ConnectionManager(resolved).get_connection()
        ensure_schema(conn)
        _svc = SynappsService(conn)
        _svc_path = resolved
    return _svc


def _fmt(sym: dict) -> str:
    fn = sym.get("full_name", "?")
    sig = sym.get("signature")
    return f"{fn} — {sig}" if sig else fn


def _unwrap_truncated(results: list | dict) -> tuple[list, str | None]:
    if isinstance(results, dict) and "_truncated" in results:
        items = results["results"]
        return items, f"showing {len(items)} of {results['_total']}"
    return results, None


def _require_label(svc: SynappsService, full_name: str, required: str, hint: str) -> bool:
    # Caller raises Exit so that commands control their own exit code.
    sym = svc.get_symbol(full_name)
    if sym is None:
        typer.echo(f"Symbol not found: {full_name}", err=True)
        return False
    labels = sym.get("_labels", [])
    if required not in labels:
        actual = labels[0] if labels else "Unknown"
        typer.echo(hint.format(name=full_name, actual=actual), err=True)
        return False
    return True


_STATUS_STYLE: dict[str, str] = {"pass": "green", "warn": "yellow", "fail": "red"}


def _render_report(console: object, report: object) -> None:
    from rich.table import Table

    groups: dict[str, list] = {}
    for result in report.checks:  # type: ignore[attr-defined]
        groups.setdefault(result.group, []).append(result)

    for group_name, results in groups.items():
        console.print(f"\n[bold]{group_name}[/bold]")  # type: ignore[attr-defined]
        table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
        table.add_column("Check", min_width=24)
        table.add_column("Status", min_width=6)
        for r in results:
            style = _STATUS_STYLE.get(r.status, "white")
            table.add_row(r.name, f"[{style}]{r.status}[/{style}]")
        console.print(table)  # type: ignore[attr-defined]
        for r in results:
            if r.status != "pass" and r.fix:
                console.print(f"  [dim]Fix ({r.name}):[/dim] {r.fix}")  # type: ignore[attr-defined]

    passed = sum(1 for r in report.checks if r.status == "pass")  # type: ignore[attr-defined]
    warned = sum(1 for r in report.checks if r.status == "warn")  # type: ignore[attr-defined]
    failed = sum(1 for r in report.checks if r.status == "fail")  # type: ignore[attr-defined]
    summary_style = "red" if failed else ("yellow" if warned else "green")
    console.print(f"\n[{summary_style}]{passed} passed, {warned} warnings, {failed} failed[/{summary_style}]")  # type: ignore[attr-defined]


@app.command("doctor", rich_help_panel="Setup & Diagnostics")
def doctor() -> None:
    """Check environment: Docker, Memgraph, and all language server dependencies."""
    from rich.console import Console

    checks = [
        DockerDaemonCheck(),
        MemgraphBoltCheck(),
        DotNetCheck(),
        CSharpLSCheck(),
        NodeCheck(),
        TypeScriptLSCheck(),
        PythonCheck(),
        PylspCheck(),
        JavaCheck(),
        JdtlsCheck(),
    ]
    report = DoctorService(checks).run()

    console = Console()
    _render_report(console, report)

    if report.has_failures:
        raise typer.Exit(1)


@app.command(rich_help_panel="Setup & Diagnostics")
def init(
    path: str = typer.Argument(default=".", help="Project path to initialise"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
) -> None:
    """Walk me through setting up Synapps for this project."""
    from synapps.onboarding.init_wizard import run_init
    print_banner()
    abs_path = str(Path(path).resolve())
    run_init(abs_path, verbose=verbose)


@app.command(rich_help_panel="Indexing")
def index(path: str, language: str = "csharp") -> None:
    """Index a project. Smart: full index if new, git sync if git project, mtime sync otherwise."""
    abs_path = str(Path(path).resolve())
    svc = _get_service(abs_path)
    try:
        result = svc.smart_index(abs_path, language, on_progress=typer.echo)
    except ModuleNotFoundError as e:
        typer.echo(
            f"Error: Missing dependency — {e}\n"
            "Your synapps installation may be incomplete. "
            "Reinstall with:  pip install -e '.[dev]'",
            err=True,
        )
        raise typer.Exit(1)
    typer.echo(f"Done ({result})")


@app.command(rich_help_panel="Indexing")
def watch(path: str) -> None:
    """Watch a project for changes and keep the graph updated."""
    abs_path = str(Path(path).resolve())

    def _log_file_event(event: str, file_path: str) -> None:
        typer.echo(f"  [{event}] {file_path}")

    _get_service(abs_path).watch_project(abs_path, on_file_event=_log_file_event)
    typer.echo(f"Watching {abs_path}. Press Ctrl+C to stop.")
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        _get_service(abs_path).unwatch_project(abs_path)


@app.command(rich_help_panel="Indexing")
def sync(path: str) -> None:
    """Sync the graph with the current filesystem — re-indexes only changed files."""
    abs_path = str(Path(path).resolve())
    try:
        result = _get_service(abs_path).sync_project(abs_path)
    except ModuleNotFoundError as e:
        typer.echo(
            f"Error: Missing dependency — {e}\n"
            "Your synapps installation may be incomplete. "
            "Reinstall with:  pip install -e '.[dev]'",
            err=True,
        )
        raise typer.Exit(1)
    except ValueError as e:
        svc = _get_service(abs_path)
        if svc.get_index_status(abs_path) is None:
            typer.echo(
                f"Project not indexed: {abs_path}\n"
                f"  Index it first: synapps index {abs_path}",
                err=True,
            )
            raise typer.Exit(1)
        typer.echo(str(e), err=True)
        raise typer.Exit(1)
    typer.echo(f"Synced: {result.updated} updated, {result.deleted} deleted, {result.unchanged} unchanged")


@app.command(rich_help_panel="Indexing")
def delete(path: str) -> None:
    """Remove a project from the graph."""
    abs_path = str(Path(path).resolve())
    _get_service(abs_path).delete_project(abs_path)
    typer.echo(f"Deleted {abs_path}")


@app.command(rich_help_panel="Indexing")
def status(path: Optional[str] = None) -> None:
    """Show index status for a project or all projects."""
    from synapps import __version__
    typer.echo(f"synapps-cli v{__version__}")
    svc = _get_service(str(Path(path).resolve()) if path else None)
    if path:
        result = svc.get_index_status(str(Path(path).resolve()))
        typer.echo(result or "Not indexed")
    else:
        for proj in svc.list_projects():
            typer.echo(proj)


@app.command(rich_help_panel="Symbol Queries")
def symbol(full_name: str) -> None:
    """Get a symbol's node and relationships."""
    result = _get_service().get_symbol(full_name)
    typer.echo(result or "Not found")


@app.command(rich_help_panel="Symbol Queries")
def source(full_name: str, include_class: bool = False) -> None:
    """Print the source code of a symbol."""
    result = _get_service().get_symbol_source(full_name, include_class_signature=include_class)
    typer.echo(result or "Not found")


@app.command(rich_help_panel="Relationships & Traversal")
def callers(
    full_name: str,
    include_tests: bool = typer.Option(False, "--include-tests", help="Include test callers"),
    tree: bool = typer.Option(False, "--tree", "-t", help="Display as ASCII tree"),
) -> None:
    """Find all methods that call a given method.

    When a short type name matches both an interface and concrete class, the concrete implementation is preferred. Method-level ambiguity still requires a qualified name."""
    svc = _get_service()
    if not _require_label(
        svc, full_name, "Method",
        "'{name}' is a {actual}, not a Method. Try a specific method like '{name}.MethodName'.",
    ):
        raise typer.Exit(1)
    results = svc.find_callers(full_name, exclude_test_callers=not include_tests)
    if not results:
        typer.echo("No results.")
        return
    if tree:
        items, annotation = _unwrap_truncated(results)
        typer.echo(render_tree(callers_tree(full_name, items, annotation=annotation)))
    else:
        # NOTE: if _apply_limit truncates, `results` is a dict and this iterates keys.
        # Pre-existing issue — fixing it is out of scope for --tree (see spec: Future Direction).
        for item in results:
            typer.echo(_fmt(item))


@app.command(rich_help_panel="Relationships & Traversal")
def callees(
    full_name: str,
    tree: bool = typer.Option(False, "--tree", "-t", help="Display as ASCII tree"),
) -> None:
    """Find all methods called by a given method."""
    svc = _get_service()
    if not _require_label(
        svc, full_name, "Method",
        "'{name}' is a {actual}, not a Method. Try a specific method like '{name}.MethodName'.",
    ):
        raise typer.Exit(1)
    results = svc.find_callees(full_name)
    if not results:
        typer.echo("No results.")
        return
    if tree:
        items, annotation = _unwrap_truncated(results)
        typer.echo(render_tree(callees_tree(full_name, items, annotation=annotation)))
    else:
        for item in results:
            typer.echo(_fmt(item))


@app.command(rich_help_panel="Relationships & Traversal")
def implementations(full_name: str) -> None:
    """Find all concrete implementations of an interface or abstract class.

    When a short type name matches both an interface and concrete class, the interface is preferred. Method-level ambiguity still requires a qualified name."""
    svc = _get_service()
    sym = svc.get_symbol(full_name)
    if sym is None:
        typer.echo(f"Symbol not found: {full_name}", err=True)
        raise typer.Exit(1)
    labels = sym.get("_labels", [])
    is_abstract_class = "Class" in labels and sym.get("is_abstract") is True
    if "Interface" not in labels and not is_abstract_class:
        actual = labels[0] if labels else "Unknown"
        typer.echo(
            f"'{full_name}' is a {actual}. To find what interfaces it implements, "
            f"use: synapps hierarchy {full_name}",
            err=True,
        )
        raise typer.Exit(1)
    results = svc.find_implementations(full_name)
    if not results:
        typer.echo("No results.")
        return
    for item in results:
        typer.echo(_fmt(item))


@app.command(rich_help_panel="Relationships & Traversal")
def hierarchy(
    full_name: str,
    tree: bool = typer.Option(False, "--tree", "-t", help="Display as ASCII tree"),
) -> None:
    """Show the full inheritance chain for a class."""
    result = _get_service().get_hierarchy(full_name)
    if tree:
        typer.echo(render_tree(hierarchy_tree(full_name, result)))
    else:
        parents = result["parents"]
        children = result["children"]
        implements = result.get("implements", [])
        typer.echo("Parents:")
        if parents:
            for p in parents:
                typer.echo(f"  {p.get('full_name', '?')}")
        else:
            typer.echo("  (none)")
        typer.echo("Children:")
        if children:
            for c in children:
                typer.echo(f"  {c.get('full_name', '?')}")
        else:
            typer.echo("  (none)")
        typer.echo("Implements:")
        if implements:
            for i in implements:
                typer.echo(f"  {i.get('full_name', '?')}")
        else:
            typer.echo("  (none)")


@app.command(rich_help_panel="Symbol Queries")
def search(
    query: str,
    kind: Optional[str] = None,
    language: Annotated[str | None, typer.Option("--language", "-l", help="Filter by language (python, csharp)")] = None,
) -> None:
    """Search symbols by name."""
    results = _get_service().search_symbols(query, kind, language=language)
    if not results:
        typer.echo("No results.")
        return
    for item in results:
        typer.echo(_fmt(item))


@app.command(rich_help_panel="Advanced")
def query(cypher: str) -> None:
    """Execute a raw read-only Cypher query."""
    for row in _get_service().execute_query(cypher):
        typer.echo(row)



@app.command("usages", rich_help_panel="Relationships & Traversal")
def usages(
    full_name: str = typer.Argument(help="Symbol to find usages of"),
    include_tests: bool = typer.Option(False, "--include-tests", help="Include test usages"),
) -> None:
    """Find all code that uses a symbol (callers + type references)."""
    svc = _get_service()
    result = svc.find_usages(full_name, exclude_test_callers=not include_tests)
    typer.echo(result)


@app.command(rich_help_panel="Relationships & Traversal")
def dependencies(
    full_name: str,
    tree: bool = typer.Option(False, "--tree", "-t", help="Display as ASCII tree"),
) -> None:
    """Find all types referenced by a symbol."""
    results = _get_service().find_dependencies(full_name)
    if not results:
        typer.echo("No results.")
        return
    if tree:
        items, annotation = _unwrap_truncated(results)
        typer.echo(render_tree(dependencies_tree(full_name, items, annotation=annotation)))
    else:
        for item in results:
            fn = item["type"].get("full_name", "?")
            depth = item.get("depth", "?")
            typer.echo(f"{fn} (depth {depth})")


@app.command(rich_help_panel="Symbol Queries")
def context(
    full_name: str,
    scope: Annotated[str | None, typer.Option(help="Scope: 'structure', 'method', 'edit', or omit for full")] = None,
    max_lines: int = typer.Option(200, "--max-lines", help="Auto-fallback to structure if source exceeds this many lines (-1 = unlimited)"),
) -> None:
    """Get the full context needed to understand or modify a symbol.

    When a short type name matches both an interface and concrete class, the concrete implementation is preferred. Method-level ambiguity still requires a qualified name."""
    result = _get_service().get_context_for(full_name, scope=scope, max_lines=max_lines)
    typer.echo(result or "Not found")


@app.command("trace", rich_help_panel="Relationships & Traversal")
def trace_chain(
    start: str = typer.Argument(help="Starting method"),
    end: str = typer.Argument(help="Ending method"),
    max_depth: int = typer.Option(6, "--depth", "-d"),
    tree: bool = typer.Option(False, "--tree", "-t", help="Display as ASCII tree"),
) -> None:
    """Trace call paths between two methods."""
    svc = _get_service()
    result = svc.trace_call_chain(start, end, max_depth)
    if not result["paths"]:
        typer.echo("No paths found.")
        return
    if tree:
        typer.echo(render_tree(trace_tree(result)))
    else:
        for i, path in enumerate(result["paths"], 1):
            typer.echo(f"Path {i}: {' → '.join(path)}")


@app.command("entry-points", rich_help_panel="Relationships & Traversal")
def entry_points(
    method: str = typer.Argument(help="Target method"),
    max_depth: int = typer.Option(8, "--depth", "-d"),
    include_tests: bool = typer.Option(False, "--include-tests", help="Include test entry points"),
    tree: bool = typer.Option(False, "--tree", "-t", help="Display as ASCII tree"),
) -> None:
    """Find all entry points that eventually call a method.

    When a short type name matches both an interface and concrete class, the concrete implementation is preferred. Method-level ambiguity still requires a qualified name."""
    svc = _get_service()
    result = svc.find_entry_points(method, max_depth, exclude_test_callers=not include_tests)
    if not result["entry_points"]:
        typer.echo("No entry points found.")
        return
    if tree:
        typer.echo(render_tree(entry_points_tree(result)))
    else:
        for ep in result["entry_points"]:
            typer.echo(f"{ep['entry']} → {' → '.join(ep['path'][1:])}")



@summary_app.command("get")
def summary_get(full_name: str) -> None:
    """Get the summary for a symbol."""
    result = _get_service().get_summary(full_name)
    typer.echo(result or "No summary")


@summary_app.command("set")
def summary_set(full_name: str, content: str) -> None:
    """Set the summary for a symbol."""
    _get_service().set_summary(full_name, content)
    typer.echo(f"Summary saved for {full_name}")


@summary_app.command("list")
def summary_list(project: Optional[str] = None) -> None:
    """List all summarized symbols."""
    for item in _get_service().list_summarized(project):
        typer.echo(item)


@app.command(rich_help_panel="Setup & Diagnostics")
def serve(
    port: Annotated[int, typer.Option("--port", "-p", help="Port to listen on")] = 7433,
    host: Annotated[str, typer.Option("--host", help="Host to bind to")] = "127.0.0.1",
    open_browser: Annotated[bool, typer.Option("--open/--no-open", help="Open browser on start")] = True,
) -> None:
    """Start the Synapps web UI at localhost."""
    import uvicorn
    from synapps.web.app import create_app

    path = str(Path.cwd())
    conn = ConnectionManager(path).get_connection()
    ensure_schema(conn)
    svc = SynappsService(conn)
    web_app = create_app(svc)

    if open_browser:
        import threading
        import webbrowser
        threading.Timer(1.0, lambda: webbrowser.open(f"http://{host}:{port}")).start()

    typer.echo(f"Synapps UI at http://{host}:{port}")
    uvicorn.run(web_app, host=host, port=port)
