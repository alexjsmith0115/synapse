from __future__ import annotations

from typing import Optional

import typer

from synapse.graph.connection import GraphConnection
from synapse.graph.schema import ensure_schema
from synapse.service import SynapseService

app = typer.Typer(name="synapse", help="LSP-powered codebase graph tool")
summary_app = typer.Typer(name="summary")
app.add_typer(summary_app, name="summary")

_svc: SynapseService | None = None


def _get_service() -> SynapseService:
    global _svc
    if _svc is None:
        conn = GraphConnection.create()
        ensure_schema(conn)
        _svc = SynapseService(conn)
    return _svc


def _fmt(sym: dict) -> str:
    """Format a symbol dict as 'full_name — signature' for methods, or just 'full_name' for types."""
    fn = sym.get("full_name", "?")
    sig = sym.get("signature")
    return f"{fn} — {sig}" if sig else fn


@app.command()
def index(path: str, language: str = "csharp") -> None:
    """Index a project into the graph."""
    _get_service().index_project(path, language)
    typer.echo(f"Indexed {path}")



@app.command()
def watch(path: str) -> None:
    """Watch a project for changes and keep the graph updated."""
    _get_service().watch_project(path)
    typer.echo(f"Watching {path}. Press Ctrl+C to stop.")
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        _get_service().unwatch_project(path)


@app.command()
def delete(path: str) -> None:
    """Remove a project from the graph."""
    _get_service().delete_project(path)
    typer.echo(f"Deleted {path}")


@app.command()
def status(path: Optional[str] = None) -> None:
    """Show index status for a project or all projects."""
    svc = _get_service()
    if path:
        result = svc.get_index_status(path)
        typer.echo(result or "Not indexed")
    else:
        for proj in svc.list_projects():
            typer.echo(proj)


@app.command()
def symbol(full_name: str) -> None:
    """Get a symbol's node and relationships."""
    result = _get_service().get_symbol(full_name)
    typer.echo(result or "Not found")


@app.command()
def source(full_name: str, include_class: bool = False) -> None:
    """Print the source code of a symbol."""
    result = _get_service().get_symbol_source(full_name, include_class_signature=include_class)
    typer.echo(result or "Not found")


@app.command()
def callers(method_full_name: str) -> None:
    """Find all methods that call a given method."""
    results = _get_service().find_callers(method_full_name)
    if not results:
        typer.echo("No results.")
        return
    for item in results:
        typer.echo(_fmt(item))


@app.command()
def callees(method_full_name: str) -> None:
    """Find all methods called by a given method."""
    results = _get_service().find_callees(method_full_name)
    if not results:
        typer.echo("No results.")
        return
    for item in results:
        typer.echo(_fmt(item))


@app.command()
def implementations(interface_name: str) -> None:
    """Find all concrete implementations of an interface."""
    results = _get_service().find_implementations(interface_name)
    if not results:
        typer.echo("No results.")
        return
    for item in results:
        typer.echo(_fmt(item))


@app.command()
def hierarchy(class_name: str) -> None:
    """Show the full inheritance chain for a class."""
    result = _get_service().get_hierarchy(class_name)
    parents = result["parents"]
    children = result["children"]
    typer.echo("Parents:")
    for p in parents:
        typer.echo(f"  {p.get('full_name', '?')}")
    if not parents:
        typer.echo("  (none)")
    typer.echo("Children:")
    for c in children:
        typer.echo(f"  {c.get('full_name', '?')}")
    if not children:
        typer.echo("  (none)")


@app.command()
def search(query: str, kind: Optional[str] = None) -> None:
    """Search symbols by name."""
    results = _get_service().search_symbols(query, kind)
    if not results:
        typer.echo("No results.")
        return
    for item in results:
        typer.echo(_fmt(item))


@app.command()
def query(cypher: str) -> None:
    """Execute a raw read-only Cypher query."""
    for row in _get_service().execute_query(cypher):
        typer.echo(row)


@app.command("type-refs")
def type_refs(full_name: str) -> None:
    """Find all symbols that reference a type."""
    results = _get_service().find_type_references(full_name)
    if not results:
        typer.echo("No results.")
        return
    for item in results:
        fn = item["symbol"].get("full_name", "?")
        kind = item.get("kind", "")
        typer.echo(f"{fn} ({kind})")


@app.command()
def dependencies(full_name: str) -> None:
    """Find all types referenced by a symbol."""
    results = _get_service().find_dependencies(full_name)
    if not results:
        typer.echo("No results.")
        return
    for item in results:
        fn = item["type"].get("full_name", "?")
        kind = item.get("kind", "")
        typer.echo(f"{fn} ({kind})")


@app.command()
def context(full_name: str) -> None:
    """Get the full context needed to understand or modify a symbol."""
    result = _get_service().get_context_for(full_name)
    typer.echo(result or "Not found")


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
