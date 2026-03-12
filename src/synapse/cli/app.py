from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import typer

# Suppress INFO/WARNING chatter from the language server process — only surface errors.
logging.getLogger("solidlsp").setLevel(logging.ERROR)

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
    fn = sym.get("full_name", "?")
    sig = sym.get("signature")
    return f"{fn} — {sig}" if sig else fn


def _require_label(svc: SynapseService, full_name: str, required: str, hint: str) -> bool:
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


@app.command()
def index(path: str, language: str = "csharp") -> None:
    """Index a project into the graph."""
    abs_path = str(Path(path).resolve())
    _get_service().index_project(abs_path, language, on_progress=typer.echo)
    typer.echo(f"Done. Indexed {abs_path}")


@app.command()
def watch(path: str) -> None:
    """Watch a project for changes and keep the graph updated."""
    abs_path = str(Path(path).resolve())
    _get_service().watch_project(abs_path)
    typer.echo(f"Watching {abs_path}. Press Ctrl+C to stop.")
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        _get_service().unwatch_project(abs_path)


@app.command()
def delete(path: str) -> None:
    """Remove a project from the graph."""
    abs_path = str(Path(path).resolve())
    _get_service().delete_project(abs_path)
    typer.echo(f"Deleted {abs_path}")


@app.command()
def status(path: Optional[str] = None) -> None:
    """Show index status for a project or all projects."""
    svc = _get_service()
    if path:
        result = svc.get_index_status(str(Path(path).resolve()))
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
    svc = _get_service()
    if not _require_label(
        svc, method_full_name, "Method",
        "'{name}' is a {actual}, not a Method. Try a specific method like '{name}.MethodName'.",
    ):
        raise typer.Exit(1)
    results = svc.find_callers(method_full_name)
    if not results:
        typer.echo("No results.")
        return
    for item in results:
        typer.echo(_fmt(item))


@app.command()
def callees(method_full_name: str) -> None:
    """Find all methods called by a given method."""
    svc = _get_service()
    if not _require_label(
        svc, method_full_name, "Method",
        "'{name}' is a {actual}, not a Method. Try a specific method like '{name}.MethodName'.",
    ):
        raise typer.Exit(1)
    results = svc.find_callees(method_full_name)
    if not results:
        typer.echo("No results.")
        return
    for item in results:
        typer.echo(_fmt(item))


@app.command()
def implementations(interface_name: str) -> None:
    """Find all concrete implementations of an interface."""
    svc = _get_service()
    if not _require_label(
        svc, interface_name, "Interface",
        "'{name}' is a {actual}. To find what interfaces it implements, use: synapse hierarchy {name}",
    ):
        raise typer.Exit(1)
    results = svc.find_implementations(interface_name)
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
        depth = item.get("depth", "?")
        typer.echo(f"{fn} (depth {depth})")


@app.command()
def context(full_name: str) -> None:
    """Get the full context needed to understand or modify a symbol."""
    result = _get_service().get_context_for(full_name)
    typer.echo(result or "Not found")


@app.command("trace")
def trace_chain(
    start: str = typer.Argument(help="Starting method"),
    end: str = typer.Argument(help="Ending method"),
    max_depth: int = typer.Option(6, "--depth", "-d"),
) -> None:
    """Trace call paths between two methods."""
    svc = _get_service()
    result = svc.trace_call_chain(start, end, max_depth)
    if not result["paths"]:
        typer.echo("No paths found.")
        return
    for i, path in enumerate(result["paths"], 1):
        typer.echo(f"Path {i}: {' → '.join(path)}")


@app.command("entry-points")
def entry_points(
    method: str = typer.Argument(help="Target method"),
    max_depth: int = typer.Option(8, "--depth", "-d"),
) -> None:
    """Find all entry points that eventually call a method."""
    svc = _get_service()
    result = svc.find_entry_points(method, max_depth)
    if not result["entry_points"]:
        typer.echo("No entry points found.")
        return
    for ep in result["entry_points"]:
        typer.echo(f"{ep['entry']} → {' → '.join(ep['path'][1:])}")


@app.command("call-depth")
def call_depth(
    method: str = typer.Argument(help="Starting method"),
    depth: int = typer.Option(3, "--depth", "-d"),
) -> None:
    """Show all methods reachable from a method up to N levels."""
    svc = _get_service()
    result = svc.get_call_depth(method, depth)
    if not result["callees"]:
        typer.echo("No callees found.")
        return
    for c in result["callees"]:
        indent = "  " * c["depth"]
        typer.echo(f"{indent}[depth {c['depth']}] {c['full_name']}")


@app.command("impact")
def impact(
    method: str = typer.Argument(help="Method to analyze"),
) -> None:
    """Analyze the blast radius of changing a method."""
    svc = _get_service()
    result = svc.analyze_change_impact(method)
    typer.echo(f"Impact analysis for: {result['target']}")
    typer.echo(f"  Direct callers: {len(result['direct_callers'])}")
    typer.echo(f"  Transitive callers: {len(result['transitive_callers'])}")
    typer.echo(f"  Test coverage: {len(result['test_coverage'])}")
    typer.echo(f"  Total affected: {result['total_affected']}")
    for c in result["direct_callers"]:
        typer.echo(f"    [direct] {c['full_name']}")
    for c in result["transitive_callers"]:
        typer.echo(f"    [transitive] {c['full_name']}")
    for t in result["test_coverage"]:
        typer.echo(f"    [test] {t['full_name']}")


@app.command("contract")
def contract(
    method: str = typer.Argument(help="Implementation method"),
) -> None:
    """Find the interface contract and sibling implementations for a method."""
    svc = _get_service()
    result = svc.find_interface_contract(method)
    if not result["interface"]:
        typer.echo("No interface contract found.")
        return
    typer.echo(f"Interface: {result['interface']}")
    typer.echo(f"Contract: {result['contract_method']}")
    for s in result["sibling_implementations"]:
        typer.echo(f"  Sibling: {s['class_name']} ({s['file_path']})")


@app.command("type-impact")
def type_impact(
    type_name: str = typer.Argument(help="Type to analyze"),
) -> None:
    """Find all code affected if a type changes shape."""
    svc = _get_service()
    result = svc.find_type_impact(type_name)
    typer.echo(f"Type impact for: {result['type']}")
    typer.echo(f"  Prod references: {result['prod_count']}")
    typer.echo(f"  Test references: {result['test_count']}")
    for r in result["references"]:
        typer.echo(f"    [{r['context']}] {r['full_name']}")


@app.command("audit")
def audit(
    rule: str = typer.Argument(help="Rule: layering_violations, untested_services, repeated_db_writes"),
) -> None:
    """Run an architectural audit rule."""
    svc = _get_service()
    try:
        result = svc.audit_architecture(rule)
    except ValueError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)
    typer.echo(f"Rule: {result['rule']} — {result['description']}")
    typer.echo(f"Violations: {result['count']}")
    for v in result["violations"]:
        typer.echo(f"  {v}")


@app.command("summarize")
def summarize(
    class_name: str = typer.Argument(help="Class to summarize"),
) -> None:
    """Auto-generate a structural summary of a class from graph data."""
    svc = _get_service()
    result = svc.summarize_from_graph(class_name)
    if not result:
        typer.echo("Symbol not found.")
        raise typer.Exit(1)
    typer.echo(result["summary"])
    typer.echo(f"\nTo persist: synapse summary set '{result['full_name']}' '<content>'")


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
