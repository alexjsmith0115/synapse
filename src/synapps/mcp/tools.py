from __future__ import annotations

import functools
import json
import logging
import os
import time
from pathlib import Path
from typing import Literal

from synapps.indexer.git import is_git_repo, rev_parse_head
from synapps.graph.nodes import get_last_indexed_commit
from synapps.service import SynappsService

log = logging.getLogger(__name__)

_BENCH_LOG = os.environ.get("SYNAPPS_BENCH_LOG", "")


def _bench_wrap(fn: callable, tool_name: str) -> callable:
    """Wrap a tool function to log response size when SYNAPPS_BENCH_LOG is set."""

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
SummaryActionLiteral = Literal["get", "set", "list"]

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
        "Endpoint": ["route", "http_method", "name"],
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
        "TESTS": "Method → Method (test method directly covers a production method; derived from CALLS where caller is a test function)",
        "SERVES": "Method → Endpoint (controller method handles this HTTP endpoint)",
        "HTTP_CALLS": "Method → Endpoint (frontend method makes HTTP request to this endpoint)",
    },
    "notes": [
        "execute_query(cypher=...) accepts read-only Cypher only (no CREATE/MERGE/SET/DELETE/REMOVE/DROP).",
        "Nodes with summaries also carry the :Summarized label and a 'summary' property.",
        "Class.kind values: 'class', 'abstract_class', 'enum', 'record', 'module', 'function', 'constructor'.",
        "Nodes may have an 'attributes' property (JSON list of decorator/attribute names, e.g. '[\"staticmethod\",\"ApiController\"]').",
        "All symbol nodes (Class, Interface, Method, Property, Field) carry a 'language' property ('csharp', 'python', or 'typescript').",
        "Method nodes may carry boolean flags: is_abstract, is_static, is_classmethod, is_async.",
        "Endpoint nodes and SERVES/HTTP_CALLS edges are populated during indexing when HTTP frameworks are detected. Use find_http_endpoints (and find_http_endpoints with trace=True for full dependency trace) to query them.",
    ],
}


def _check_auto_sync(project_path: str, service: SynappsService) -> None:
    """Core auto-sync logic: git-hash staleness check + sync if needed (D-05, D-06).

    Extracted as module-level function for testability. Called by the closure
    _auto_sync_check() inside register_tools.
    """
    if not project_path:
        return

    # Read config (D-07: default True, opt-out via .synapps/config.json)
    config_path = Path(project_path) / ".synapps" / "config.json"
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


def register_tools(mcp: object, service: SynappsService, project_path: str = "") -> None:
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
                "Your synapps installation may be incomplete. "
                "Reinstall with:  pip install -e ."
            )
        return f"Indexed {path}"

    @mcp.tool()
    def list_projects(path: str | None = None) -> list[dict] | dict | None:
        """List all indexed projects. Returns path, languages (list), and last-indexed timestamp for each.

        path: if provided, returns detailed index status for that specific project
        (file count, symbol count, per-label breakdown) instead of the project list.
        """
        from synapps import __version__
        if path:
            _auto_sync_check()
            result = service.get_index_status(path)
            if result is not None:
                result["synapps_mcp_version"] = __version__
            return result
        projects = service.list_projects()
        return {"synapps_mcp_version": __version__, "projects": projects}

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
            if service.get_index_status(path) is None:
                return (
                    f"Error: Project not indexed: {path}\n"
                    f"Index it first: run index_project(path='{path}')"
                )
            return f"Error: {e}"
        return f"Synced: {result.updated} updated, {result.deleted} deleted, {result.unchanged} unchanged"

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
    def find_callees(
        method_full_name: str,
        include_interface_dispatch: bool = True,
        limit: int = 50,
        depth: int | None = None,
    ) -> list[dict] | dict:
        """Find methods called by the given method.

        By default, includes concrete implementations when the call site targets an
        interface method (common in C# DI codebases). Set include_interface_dispatch=False
        for direct CALLS edges only.

        depth: if provided, returns all methods reachable up to N levels deep (like a call tree).
        When depth is set, include_interface_dispatch and limit are ignored.
        Returns {root, callees: [{full_name, file_path, depth}], depth_limit}.

        Known graph boundary:
        - Calls to external framework types (Spring Data repositories, RestTemplate, JDK stdlib,
          .NET BCL, Entity Framework) are not indexed because external type sources are not parsed.
          Only calls to project-defined methods on project-defined types appear in the graph.
          Inspect call sites directly (via get_context_for) when framework method calls are needed.
        """
        _auto_sync_check()
        try:
            if depth is not None:
                return service.get_call_depth(method_full_name, depth)
            return service.find_callees(method_full_name, include_interface_dispatch, limit=limit)
        except ValueError as e:
            return {"error": str(e)}

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
    def summary(
        action: SummaryActionLiteral,
        full_name: str | None = None,
        content: str | None = None,
        project_path: str | None = None,
    ) -> str | list[dict] | None:
        """Persist non-derivable context on a symbol — design rationale, constraints, ownership, deprecation plans.

        Do NOT store structural descriptions (interfaces, method counts, dependencies) — those are
        already queryable live via get_context_for, find_dependencies, etc.

        Actions: 'set' (persist summary on a symbol), 'get' (retrieve summary), 'list' (list all summarized symbols).
        set: requires full_name and content.
        get: requires full_name.
        list: optional project_path to filter by project.
        """
        _auto_sync_check()
        if action == "set":
            if not full_name or not content:
                return "Error: 'set' requires both full_name and content"
            service.set_summary(full_name, content)
            return f"Summary saved for {full_name}"
        elif action == "get":
            if not full_name:
                return "Error: 'get' requires full_name"
            return service.get_summary(full_name)
        elif action == "list":
            return service.list_summarized(project_path)

    @mcp.tool()
    def get_schema() -> dict:
        """Return the full graph schema: node labels with properties, relationship types, and usage notes.

        Use this before writing raw Cypher for execute_query.
        """
        return _GRAPH_SCHEMA

    @mcp.tool()
    def execute_query(cypher: str) -> list[dict]:
        """Last resort — use dedicated tools (find_usages, find_callees, search_symbols, etc.) when possible.

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
    def find_usages(
        full_name: str,
        exclude_test_callers: bool = True,
        limit: int = 20,
        kind: str | None = None,
    ) -> str | list[dict]:
        """Find all code that uses a symbol — returns a compact text summary.

        For methods/properties/fields: lists callers with file locations.
        For classes/interfaces: shows type reference count, method callers grouped by method with top callers, and affected file count.
        Test usages are excluded by default. Set exclude_test_callers=False to include them.

        kind: optional filter for type references — one of 'parameter', 'return_type', 'property_type'.
        When kind is set, returns structured type reference list instead of text summary.
        """
        _auto_sync_check()
        try:
            if kind is not None:
                return service.find_type_references(full_name, kind=kind, limit=limit)
            return service.find_usages(full_name, exclude_test_callers, limit=limit)
        except ValueError as e:
            return str(e)

    @mcp.tool()
    def find_dependencies(full_name: str, depth: int = 1, limit: int = 50) -> list[dict] | dict:
        """Find field-type dependencies for the given symbol.

        depth: how many hops to traverse (default 1 = direct deps only, max 5).
        Each result includes a 'depth' field indicating how many hops from the root.
        Useful for impact analysis — depth=2 shows transitive dependencies.
        """
        _auto_sync_check()
        try:
            return service.find_dependencies(full_name, depth, limit=limit)
        except ValueError as e:
            return {"error": str(e)}

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
        - "impact": change impact analysis — direct callers, transitive callers (2-4 hops),
          test coverage, and direct callees. Answers: "if I change this, what breaks?"

        max_lines: if source exceeds this many lines, show structure overview instead of full source.
        Set to 0 for structure-only. Set to -1 to disable the limit.
        When a short type name matches both an interface and concrete class, the concrete implementation is preferred. Method-level ambiguity (e.g. CreateAsync on multiple classes) still requires a qualified name.
        """
        _auto_sync_check()
        try:
            result = service.get_context_for(full_name, scope=scope, max_lines=max_lines)
        except ValueError as e:
            return str(e)
        if result:
            warning = service._staleness_warning(full_name)
            if warning:
                result = f"\u26a0\ufe0f {warning}\n\n---\n\n{result}"
        return result or "Symbol not found."

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
        try:
            return service.find_entry_points(method, max_depth, exclude_pattern, exclude_test_callers)
        except ValueError as e:
            return {"error": str(e)}

    @mcp.tool()
    def find_http_endpoints(
        route: str | None = None,
        http_method: str | None = None,
        language: str | None = None,
        limit: int = 50,
        trace: bool = False,
    ) -> list[dict] | dict:
        """Search for HTTP endpoints by route pattern, HTTP method, or language.

        route: substring match on endpoint route (e.g. 'items' matches '/api/items', '/api/items/{id}').
        http_method: filter by HTTP method (GET, POST, PUT, DELETE, etc.).
        language: filter to endpoints served by handlers in this language (e.g. 'csharp', 'python').
        Endpoints without a server handler are excluded when language is specified.
        Returns list of dicts: route, http_method, handler_full_name, file_path, line, language, has_server_handler.

        trace: if True, requires both route and http_method. Returns the server handler and all
        client call sites for the exact endpoint instead of a list. Use this after discovering
        routes to get the full dependency picture.
        """
        _auto_sync_check()
        if trace:
            if not route or not http_method:
                return {"error": "trace=True requires both route and http_method"}
            return service.trace_http_dependency(route, http_method)
        return service.find_http_endpoints(route, http_method, language, limit=limit)

    @mcp.tool()
    def get_architecture(path: str, limit: int = 10) -> dict:
        """Get a single-call architecture overview of an indexed project.

        Returns a structured overview with four sections:
        - packages: package/namespace breakdown with file and symbol counts (most meaningful for C# projects)
        - hotspots: top N methods by inbound caller count (test methods excluded)
        - http_service_map: HTTP endpoints served by and called from this codebase
        - stats: total files, symbols, packages, endpoints, and per-language file counts

        path: project root path (must be indexed)
        limit: max number of hotspot methods to return (default 10)
        """
        _auto_sync_check()
        return service.get_architecture_overview(limit=limit)

    @mcp.tool()
    def find_dead_code(
        path: str,
        exclude_pattern: str = "",
        limit: int = 200,
    ) -> dict:
        """[Experimental] Find methods with zero inbound callers (dead code candidates) in an indexed project.

        Excludes test methods, HTTP handlers, interface implementations,
        interface dispatch targets, interface/protocol definition methods,
        constructor methods, overriding methods, EF Core migration methods,
        main() entry points, and framework-registered entry points
        (@command, @tool, @callback, @Bean, @PostConstruct, @RequestMapping,
        @GetMapping, @PostMapping, @Scheduled, etc.).

        Known false positive patterns (use exclude_pattern to filter):
        - Methods called via closures/callbacks passed as arguments
        - Methods invoked through dict-based dispatch
        - Some self.method() calls where LSP resolution is incomplete

        path: project root path (must be indexed)
        exclude_pattern: optional regex applied to full_name to filter additional methods
          (e.g. 'MyApp\\.Generated\\..*' excludes generated code namespaces).
          Use alternation for multiple patterns: 'pattern1|pattern2'.
          Empty string means no additional filtering.
        limit: max number of dead methods to return (default 200). Stats always reflect full count.
        Returns {methods: [{full_name, file_path, line, inbound_call_count}], stats: {total_methods, dead_count, dead_ratio, truncated, limit}}.
        """
        _auto_sync_check()
        return service.find_dead_code(exclude_pattern=exclude_pattern, limit=limit)

    @mcp.tool()
    def find_tests_for(
        path: str,
        method_full_name: str,
    ) -> list[dict]:
        """[Experimental] Find test methods that directly cover a production method via TESTS edges.

        Returns test methods that have a direct TESTS relationship to the target method.
        TESTS edges are derived from CALLS edges where the caller is a test method
        and the callee is a production method.

        path: project root path (must be indexed)
        method_full_name: fully qualified name of the production method (short names supported via resolution)
        Returns [{full_name, file_path, line}] — one entry per test method covering the target.
        """
        _auto_sync_check()
        try:
            return service.find_tests_for(method_full_name=method_full_name)
        except ValueError as e:
            return {"error": str(e)}

    @mcp.tool()
    def find_untested(
        path: str,
        exclude_pattern: str = "",
        limit: int = 200,
    ) -> dict:
        """[Experimental] Find production methods with no inbound TESTS edges (not directly covered by any test).

        Excludes test methods, HTTP handlers, interface implementations,
        interface dispatch targets, interface/protocol definition methods,
        constructor methods, overriding methods, EF Core migration methods,
        main() entry points, and framework-registered entry points
        (@command, @tool, @callback, @Bean, @PostConstruct, @RequestMapping,
        @GetMapping, @PostMapping, @Scheduled, etc.).

        Known false positive patterns (use exclude_pattern to filter):
        - Methods tested only through string-based dispatch (MCP call_tool, mocks)
        - Private methods tested indirectly through public API (transitive coverage)
        - Some self.method() calls where LSP resolution is incomplete

        path: project root path (must be indexed)
        exclude_pattern: optional regex applied to full_name to filter additional methods
          (e.g. 'MyApp\\.Generated\\..*' excludes generated code namespaces).
          Use alternation for multiple patterns: 'pattern1|pattern2'.
          Empty string means no additional filtering.
        limit: max number of untested methods to return (default 200). Stats always reflect full count.
        Returns {methods: [{full_name, file_path, line}], stats: {total_methods, untested_count, untested_ratio, truncated, limit}}.
        """
        _auto_sync_check()
        return service.find_untested(exclude_pattern=exclude_pattern, limit=limit)


