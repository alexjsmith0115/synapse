from __future__ import annotations

import functools
import json
import logging
import os
import time
from pathlib import Path
from typing import Literal

from synapse.indexer.git import is_git_repo, rev_parse_head
from synapse.graph.nodes import get_last_indexed_commit
from synapse.service import SynapseService

log = logging.getLogger(__name__)

_BENCH_LOG = os.environ.get("SYNAPSE_BENCH_LOG", "")


def _bench_wrap(fn: callable, tool_name: str) -> callable:
    """Wrap a tool function to log response size when SYNAPSE_BENCH_LOG is set."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        t0 = time.monotonic()
        result = fn(*args, **kwargs)
        elapsed_ms = (time.monotonic() - t0) * 1000

        if isinstance(result, str):
            size = len(result.encode("utf-8"))
        elif result is None:
            size = 4  # "null"
        else:
            size = len(json.dumps(result).encode("utf-8"))

        log_path = Path(_BENCH_LOG)
        with log_path.open("a") as f:
            json.dump(
                {
                    "tool": tool_name,
                    "bytes": size,
                    "ms": round(elapsed_ms, 1),
                    "ts": time.time(),
                    "args": {k: v for k, v in kwargs.items() if isinstance(v, (str, int, float, bool))},
                },
                f,
            )
            f.write("\n")

        return result

    return wrapper

SymbolKindLiteral = Literal[
    "Class", "Interface", "Method", "Property", "Field",
    "Namespace", "File", "Directory", "Repository",
]
AuditRuleLiteral = Literal["layering_violations", "untested_services"]

_GRAPH_SCHEMA = {
    "node_labels": {
        "Repository": ["path", "name", "languages", "last_indexed"],
        "Directory": ["path", "name"],
        "File": ["path", "name", "language", "last_indexed"],
        "Package": ["name"],
        "Class": ["full_name", "name", "kind", "file_path", "line", "end_line", "language", "signature", "attributes"],
        "Interface": ["full_name", "name", "kind", "file_path", "line", "end_line", "language", "attributes"],
        "Method": ["full_name", "name", "file_path", "line", "end_line", "language", "signature", "is_abstract", "is_static", "is_classmethod", "is_async", "attributes"],
        "Property": ["full_name", "name", "file_path", "line", "end_line", "language", "type_name", "attributes"],
        "Field": ["full_name", "name", "file_path", "line", "end_line", "language", "type_name", "attributes"],
    },
    "relationship_types": {
        "CONTAINS": "Repository/Directory/File/Class/Interface → any",
        "INHERITS": "Class → Class",
        "IMPLEMENTS": "Class → Interface  |  Method → Method (concrete implements interface method)",
        "DISPATCHES_TO": "Method → Method (interface method → concrete implementation; inverse of method-level IMPLEMENTS, written at index time to enable interface-crossing path traversal)",
        "CALLS": "Method/Class → Method (method or module-scope call)",
        "REFERENCES": "any → Class/Interface (field type, param type, return type)",
        "OVERRIDES": "Method → Method (child class method overrides parent class method by name)",
        "IMPORTS": "File → Package/any (import dependency)",
    },
    "notes": [
        "execute_query(cypher=...) accepts read-only Cypher only (no CREATE/MERGE/SET/DELETE/REMOVE/DROP).",
        "Nodes with summaries also carry the :Summarized label and a 'summary' property.",
        "Class.kind values: 'class', 'abstract_class', 'enum', 'record', 'module', 'function', 'constructor'.",
        "Nodes may have an 'attributes' property (JSON list of decorator/attribute names, e.g. '[\"staticmethod\",\"ApiController\"]').",
        "All symbol nodes (Class, Interface, Method, Property, Field) carry a 'language' property ('csharp', 'python', or 'typescript').",
        "Method nodes may carry boolean flags: is_abstract, is_static, is_classmethod, is_async.",
    ],
}


def _check_auto_sync(project_path: str, service: SynapseService) -> None:
    """Core auto-sync logic: git-hash staleness check + sync if needed (D-05, D-06).

    Extracted as module-level function for testability. Called by the closure
    _auto_sync_check() inside register_tools.
    """
    if not project_path:
        return

    # Read config (D-07: default True, opt-out via .synapse/config.json)
    config_path = Path(project_path) / ".synapse" / "config.json"
    auto_sync = True
    if config_path.exists():
        try:
            with open(config_path) as f:
                config = json.load(f)
            auto_sync = config.get("auto_sync", True)
        except (json.JSONDecodeError, OSError):
            pass
    if not auto_sync:
        return

    if not is_git_repo(project_path):
        return

    stored_sha = get_last_indexed_commit(service._conn, project_path)
    if stored_sha is None:
        return

    current_sha = rev_parse_head(project_path)
    if current_sha and current_sha != stored_sha:
        log.info("Auto-sync: graph stale (stored=%s, current=%s), syncing...", stored_sha[:8], current_sha[:8])
        service.smart_index(project_path)


def register_tools(mcp: object, service: SynapseService, project_path: str = "") -> None:
    """Register all MCP tools on the given MCP server instance."""

    if _BENCH_LOG:
        _orig_tool = mcp.tool

        def _instrumented_tool(*deco_args, **deco_kwargs):
            decorator = _orig_tool(*deco_args, **deco_kwargs)

            def wrapping_decorator(fn):
                wrapped = _bench_wrap(fn, fn.__name__)
                return decorator(wrapped)

            return wrapping_decorator

        mcp.tool = _instrumented_tool
        log.info("Bench logging enabled → %s", _BENCH_LOG)

    def _auto_sync_check() -> None:
        _check_auto_sync(project_path, service)

    @mcp.tool()
    def index_project(path: str, language: str = "csharp") -> str:
        """Index a project's codebase into the graph. Uses MERGE (upsert) so nodes are updated in place rather than deleted and recreated. Summaries and other non-structural properties are preserved.

        Uses LSP for structural analysis (symbols, inheritance, implementations) and tree-sitter for call site detection.
        Supports C# (language='csharp'), Python (language='python'), and TypeScript/JavaScript (language='typescript') projects. Language is auto-detected from file extensions when not specified.
        """
        try:
            service.index_project(path, language)
        except ModuleNotFoundError as e:
            return (
                f"Error: Missing dependency — {e}\n"
                "Your synapse installation may be incomplete. "
                "Reinstall with:  pip install -e ."
            )
        return f"Indexed {path}"

    @mcp.tool()
    def list_projects() -> list[dict]:
        """List all indexed projects. Returns path, languages (list), and last-indexed timestamp for each."""
        return service.list_projects()

    @mcp.tool()
    def delete_project(path: str) -> str:
        """Delete a project and all its graph data (nodes, edges, summaries). This is irreversible."""
        service.delete_project(path)
        return f"Deleted {path}"

    @mcp.tool()
    def sync_project(path: str) -> str:
        """Sync the graph with the current filesystem state.

        Detects files that changed, were added, or were deleted since last indexing
        and re-indexes only what changed. Requires the project to have been fully
        indexed at least once (run index_project first).
        """
        try:
            result = service.sync_project(path)
        except ValueError as e:
            return f"Error: {e}"
        return f"Synced: {result.updated} updated, {result.deleted} deleted, {result.unchanged} unchanged"

    @mcp.tool()
    def get_index_status(path: str) -> dict | None:
        """Return indexing status for a project including file count, symbol count, and per-label symbol breakdown. The path parameter is the project root path, as returned by list_projects."""
        _auto_sync_check()
        return service.get_index_status(path)

    @mcp.tool()
    def get_symbol(full_name: str) -> dict | None:
        """Get a symbol's metadata (file path, line range, kind, full name) by full name or short name. Does not return source code — use get_symbol_source for that. For source code + relationships in one call, use get_context_for."""
        _auto_sync_check()
        result = service.get_symbol(full_name)
        if result:
            warning = service._staleness_warning(full_name)
            if warning:
                result["_staleness_warning"] = warning
        return result

    @mcp.tool()
    def get_symbol_source(full_name: str, include_class_signature: bool = False) -> str:
        """Fetch the source code of a specific symbol by full name. Reads from the file on disk using the line range recorded at index time. Use include_class_signature=True to include the enclosing class declaration."""
        _auto_sync_check()
        result = service.get_symbol_source(full_name, include_class_signature)
        if result is not None:
            return result
        if service.get_symbol(full_name) is not None:
            return f"Source not available for {full_name} — re-index required"
        return f"Symbol not found: {full_name}"

    @mcp.tool()
    def find_implementations(interface_name: str, limit: int = 50) -> list[dict] | dict:
        """Find all classes that implement the given interface.

        Accepts both full names (e.g. "MyNs.IFoo") and short names (e.g. "IFoo").
        Short names use a suffix match when an exact match is not found.
        When a short type name matches both an interface and concrete class, the interface is preferred. Method-level ambiguity (e.g. CreateAsync on multiple classes) still requires a qualified name.
        """
        _auto_sync_check()
        return service.find_implementations(interface_name, limit=limit)

    @mcp.tool()
    def find_callers(
        method_full_name: str,
        include_interface_dispatch: bool = True,
        exclude_test_callers: bool = True,
        limit: int = 50,
    ) -> list[dict] | dict:
        """Find methods that call the given method. Includes interface dispatch by default — no need to manually resolve interface implementations first.

        Callers that invoke this method through an interface are included
        (common in C# DI codebases). Set include_interface_dispatch=False for
        direct CALLS edges only.

        Test callers are excluded by default (files whose path contains a
        directory segment ending in Test, Tests, test, or tests —
        e.g. MyApp.Tests/, tests/, IntegrationTests/). Set
        exclude_test_callers=False to include them.

        When a short type name matches both an interface and concrete class, the concrete implementation is preferred. Method-level ambiguity (e.g. CreateAsync on multiple classes) still requires a qualified name.
        """
        _auto_sync_check()
        return service.find_callers(method_full_name, include_interface_dispatch, exclude_test_callers, limit=limit)

    @mcp.tool()
    def find_callees(
        method_full_name: str,
        include_interface_dispatch: bool = True,
        limit: int = 50,
    ) -> list[dict] | dict:
        """Find methods called by the given method.

        By default, includes concrete implementations when the call site targets an
        interface method (common in C# DI codebases). Set include_interface_dispatch=False
        for direct CALLS edges only.
        """
        _auto_sync_check()
        return service.find_callees(method_full_name, include_interface_dispatch, limit=limit)

    @mcp.tool()
    def get_hierarchy(class_name: str) -> dict:
        """Get the inheritance hierarchy for a class or interface (supports short names)."""
        _auto_sync_check()
        try:
            result = service.get_hierarchy(class_name)
        except ValueError as e:
            return {"error": str(e)}
        warning = service._staleness_warning(class_name)
        if warning:
            result["_staleness_warning"] = warning
        return result

    @mcp.tool()
    def search_symbols(
        query: str,
        kind: SymbolKindLiteral | None = None,
        namespace: str | None = None,
        file_path: str | None = None,
        language: str | None = None,
        limit: int = 50,
    ) -> list[dict] | dict:
        """Search for symbols by name substring. Use this to discover symbol names before passing them to other tools.

        kind: filter by node type.
        namespace: filter to symbols whose full_name starts with this prefix
                   (e.g. "MyNs.Services").
        file_path: filter to symbols defined in this file path.
        language: filter to symbols from a specific language (e.g. "python", "csharp").
        """
        _auto_sync_check()
        return service.search_symbols(query, kind, namespace, file_path, language, limit=limit)

    @mcp.tool()
    def set_summary(full_name: str, content: str) -> str:
        """Persist a human-readable summary string on a symbol node, making it retrievable via get_summary and visible in list_summarized."""
        _auto_sync_check()
        service.set_summary(full_name, content)
        return f"Summary saved for {full_name}"

    @mcp.tool()
    def get_summary(full_name: str) -> str | None:
        """Retrieve a previously stored summary for a symbol. Returns None if no summary has been set."""
        _auto_sync_check()
        return service.get_summary(full_name)

    @mcp.tool()
    def list_summarized(project_path: str | None = None) -> list[dict]:
        """List all symbols that have been annotated with a summary via set_summary."""
        _auto_sync_check()
        return service.list_summarized(project_path)

    @mcp.tool()
    def get_schema() -> dict:
        """Return the full graph schema: node labels with properties, relationship types, and usage notes.

        Use this before writing raw Cypher for execute_query.
        """
        return _GRAPH_SCHEMA

    @mcp.tool()
    def execute_query(cypher: str) -> list[dict]:
        """Last resort — use dedicated tools (find_callers, find_callees, search_symbols, etc.) when possible.

        Execute a read-only Cypher query against the graph.

        Args:
            cypher: The Cypher query string to execute. Must be read-only.

        Read-only: CREATE, MERGE, SET, DELETE, REMOVE, DROP are blocked.

        Schema summary (call get_schema() for full details):
          Nodes: Repository, Directory, File, Package, Class, Interface, Method, Property, Field
          Edges: CONTAINS, INHERITS, IMPLEMENTS, DISPATCHES_TO, CALLS, REFERENCES
          Key properties: full_name, name, file_path, line, end_line, signature, kind

        Example: MATCH (m:Method {full_name: 'MyNs.MyClass.MyMethod'}) RETURN m
        """
        return service.execute_query(cypher)

    @mcp.tool()
    def find_type_references(full_name: str, kind: str | None = None, limit: int = 50) -> list[dict] | dict:
        """Return all symbols that reference the given type as a parameter, return type, or property type.

        kind: optional filter — one of 'parameter', 'return_type', 'property_type'.
        Each result includes a kind field indicating the relationship.
        """
        _auto_sync_check()
        return service.find_type_references(full_name, kind=kind, limit=limit)

    @mcp.tool()
    def find_usages(full_name: str, exclude_test_callers: bool = True, limit: int = 20) -> dict:
        """Unified entry point — auto-selects the right lookup strategy based on symbol kind. Prefer over manually choosing between find_callers and find_type_references.

        For methods/properties/fields: returns callers (CALLS edges).
        For classes/interfaces: returns a tiered summary — type_references (total count + up to `limit` items),
        method_callers (total count + top 5 callers per method), and affected_files count.
        Test usages are excluded by default. Set exclude_test_callers=False to include them.
        """
        _auto_sync_check()
        return service.find_usages(full_name, exclude_test_callers, limit=limit)

    @mcp.tool()
    def find_dependencies(full_name: str, depth: int = 1, limit: int = 50) -> list[dict] | dict:
        """Find field-type dependencies for the given symbol.

        depth: how many hops to traverse (default 1 = direct deps only, max 5).
        Each result includes a 'depth' field indicating how many hops from the root.
        Useful for impact analysis — depth=2 shows transitive dependencies.
        """
        _auto_sync_check()
        return service.find_dependencies(full_name, depth, limit=limit)

    @mcp.tool()
    def get_context_for(full_name: str, scope: str | None = None, max_lines: int = 200) -> str:
        """Recommended starting point for understanding any symbol before reading or editing.

        Returns rich context: source, hierarchy, dependencies, and summaries.

        scope controls detail level:
        - None (default): full context — source, all members, interfaces, callees, dependencies, summaries
        - "structure": type overview — constructor, member signatures, interfaces, summaries (no method bodies)
        - "method": focused method context — source, interface contract, callees, dependencies, summaries
        - "edit": task-oriented edit context — source, interface contract, direct callers with call-site
          lines, constructor dependencies relevant to the symbol, test coverage, summaries.
          Works for methods (filtered deps) and classes/interfaces (all deps, callers grouped by method).

        max_lines: if source exceeds this many lines, show structure overview instead of full source.
        Set to 0 for structure-only. Set to -1 to disable the limit.
        When a short type name matches both an interface and concrete class, the concrete implementation is preferred. Method-level ambiguity (e.g. CreateAsync on multiple classes) still requires a qualified name.
        """
        _auto_sync_check()
        result = service.get_context_for(full_name, scope=scope, max_lines=max_lines)
        if result:
            warning = service._staleness_warning(full_name)
            if warning:
                result = f"\u26a0\ufe0f {warning}\n\n---\n\n{result}"
        return result or "Symbol not found."

    @mcp.tool()
    def trace_call_chain(start: str, end: str, max_depth: int = 6) -> dict:
        """Find all call paths between two methods up to max_depth hops.

        Supports short names (e.g. 'CreateMeeting' instead of full namespace).
        Returns {paths: [[str]], start, end, max_depth}.
        """
        _auto_sync_check()
        return service.trace_call_chain(start, end, max_depth)

    @mcp.tool()
    def find_entry_points(
        method: str,
        max_depth: int = 8,
        exclude_pattern: str = "",
        exclude_test_callers: bool = True,
    ) -> dict:
        """Find all root callers (no incoming CALLS edges) that eventually call a method.

        Useful for finding controller/API entry points that reach a given service method.
        exclude_pattern: optional regex on full_name to filter unwanted entry points
        (e.g. ".*\\.Tests\\..*" excludes test methods, ".*Controller.*" narrows to controllers).
        Test entry points are excluded by default. Set exclude_test_callers=False to include them.
        Returns {entry_points: [{entry, path}], target, max_depth}.
        Each entry point appears once with the shortest path to the target.
        When a short type name matches both an interface and concrete class, the concrete implementation is preferred. Method-level ambiguity (e.g. CreateAsync on multiple classes) still requires a qualified name.
        """
        _auto_sync_check()
        return service.find_entry_points(method, max_depth, exclude_pattern, exclude_test_callers)

    @mcp.tool()
    def get_call_depth(method: str, depth: int = 3) -> dict:
        """Get all methods reachable from a starting method up to N levels deep.

        Returns {root, callees: [{full_name, file_path, depth}], depth_limit}.
        """
        _auto_sync_check()
        return service.get_call_depth(method, depth)

    @mcp.tool()
    def analyze_change_impact(method: str) -> dict:
        """Analyze the impact of changing a method: direct callers, transitive callers, test coverage, and direct callees.

        Returns {target, direct_callers, transitive_callers, test_coverage, direct_callees, total_affected}.
        total_affected counts upstream (callers) only — callees are downstream context.
        When a short type name matches both an interface and concrete class, the concrete implementation is preferred. Method-level ambiguity (e.g. CreateAsync on multiple classes) still requires a qualified name.
        """
        _auto_sync_check()
        return service.analyze_change_impact(method)

    @mcp.tool()
    def find_interface_contract(method: str) -> dict:
        """Find the interface contract a method satisfies and all sibling implementations.

        Returns {method, interface, contract_method, sibling_implementations}.
        When a short type name matches both an interface and concrete class, the interface is preferred. Method-level ambiguity (e.g. CreateAsync on multiple classes) still requires a qualified name.
        """
        _auto_sync_check()
        return service.find_interface_contract(method)

    @mcp.tool()
    def find_type_impact(type_name: str, limit: int = 50) -> dict:
        """Find all code affected if a type's shape changes, categorized as prod or test.

        Returns {type, references: [{full_name, file_path, context}], prod_count, test_count, _total_references}.
        limit: max number of references to return (default 50). When truncated, _truncated=True and _total_references shows the full count.
        """
        _auto_sync_check()
        return service.find_type_impact(type_name, limit=limit)

    @mcp.tool()
    def audit_architecture(rule: AuditRuleLiteral) -> dict:
        """Run an architectural audit rule against the codebase graph.

        Returns {rule, description, violations: [dict], count}.
        These rules are C#/.NET-specific.
        """
        _auto_sync_check()
        return service.audit_architecture(rule)

    @mcp.tool()
    def summarize_from_graph(class_name: str) -> dict:
        """Auto-generate a structural summary of a class from graph data.

        Returns {full_name, summary, data: {kind, interfaces, method_count, dependencies, dependents, test_classes}}.
        The summary is NOT stored automatically — call set_summary to persist after review.
        """
        _auto_sync_check()
        return service.summarize_from_graph(class_name)
