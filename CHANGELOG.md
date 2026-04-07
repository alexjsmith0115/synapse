# Changelog

All notable changes to Synapps will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- **LSPResolverBackend protocol** — extended with `request_references` and `set_request_timeout` method stubs, matching the concrete implementations in solidlsp; required by the v2.1 ReferencesResolver
- **`find_enclosing_method_ast`** — new AST-based scope attribution function in `tree_sitter_util` using tree-sitter parent-chain traversal; correctly handles nested functions and lambdas where line-based bisect cannot distinguish scope boundaries; `_METHOD_NODE_TYPES` frozenset covers all 4 language grammars (14 node types)

- **`ReferencesResolver`** — new class in `src/synapps/indexer/references_resolver.py` implementing LSP references-based CALLS edge resolution; iterates all indexed method symbols, calls `request_references` per method with a 30s per-request timeout, attributes each reference to its enclosing method via `find_enclosing_method_ast`, discards declaration-line self-references, skips module-level code (None scope), deduplicates (caller, callee) pairs, and writes CALLS edges via `batch_upsert_calls`; activated by the indexer when `create_call_extractor()` returns None
- **Indexer dispatch branch for ReferencesResolver** — `_resolve_calls_and_refs` in `indexer.py` now dispatches to `ReferencesResolver` when `call_ext is None and parsed_cache is not None`; SymbolResolver still runs first for REFERENCES (type-ref) edges

### Removed
- **Dead tree-sitter CallExtractor files deleted** — `CSharpCallExtractor`, `PythonCallExtractor`, and `TypeScriptCallExtractor` source files and their unit tests removed; all three were retired in favour of `ReferencesResolver` during the v2.1 migration; `JavaCallExtractor` preserved for the Java post-pass in `indexer.py`
- **`CallIndexer` deleted** — dead class (imported `CSharpCallExtractor`, only referenced by its own test) removed along with `tests/unit/indexer/test_call_indexer.py`

### Changed
- **Java call indexing migrated to ReferencesResolver** -- `JavaPlugin.create_call_extractor()` now returns `None`, retiring the tree-sitter `JavaCallExtractor` from the primary indexing path; Java CALLS edges are now produced by `ReferencesResolver` using LSP `textDocument/references`; a dedicated Java-only post-pass preserves ExternalCallStubber and Spring Data stub CALLS edges (LANG-03)
- **Java method reference fixture** -- `AnimalService.greetAllFunctional` added to the Java integration fixture using `IAnimal::speak` method reference syntax; exercises `ReferencesResolver`'s ability to produce CALLS edges from method references; covered by `test_method_reference_produces_calls_edge` integration test
- **C# call indexing migrated to ReferencesResolver** -- `CSharpPlugin.create_call_extractor()` now returns `None`, retiring the tree-sitter `CSharpCallExtractor` from the active indexing path; C# CALLS edges are now produced by `ReferencesResolver` using LSP `textDocument/references` (LANG-04)
- **Python call indexing migrated to ReferencesResolver** -- `PythonPlugin.create_call_extractor()` now returns `None`, retiring the tree-sitter `PythonCallExtractor` from the active indexing path; Python CALLS edges are now produced by `ReferencesResolver` using LSP `textDocument/references` via Pyright; no post-pass needed (unlike Java) (LANG-02)
- **TypeScript call indexing migrated to ReferencesResolver** -- `TypeScriptPlugin.create_call_extractor()` now returns `None`, retiring the tree-sitter `TypeScriptCallExtractor` from the active indexing path; TypeScript CALLS edges are now produced by `ReferencesResolver` using LSP `textDocument/references`; TypeScript is now the fourth and final language on the LSP references-based call indexing path (LANG-01)

### Fixed
- **SymbolResolver fallback to CSharpCallExtractor when call_extractor=None** — `SymbolResolver.__init__` no longer defaults `call_extractor=None` to `CSharpCallExtractor()`; passing `None` now correctly skips call extraction while type-ref extraction continues normally; required for languages that delegate CALLS resolution to `ReferencesResolver`
- **VALID-02 validation fixture** — added `DelegateHost.cs` C# fixture with `CallWithMethodGroup` method that passes `_service.GetTaskAsync` as a method group delegate argument; integration test `test_delegate_argument_produces_calls_edge` asserts a CALLS edge is produced via `ReferencesResolver`
- **VALID-03 constructor kind mapping audit** — added `tests/unit/lsp/test_constructor_kind_mapping.py` with 8 parametrized cases confirming LSP kind 9 (Constructor) maps to `SymbolKind.METHOD` in all 4 language adapters (C#, Java, Python, TypeScript)

## [1.8.4] - 2026-04-06

### Fixed
- **SPA missing from wheel on CI publish** — added Node.js setup and `build_spa.sh` step to publish workflow so SPA assets are compiled before `uv build`; replaced custom build hook with static `force-include` entries in `pyproject.toml` (per-file to avoid duplicate ZIP entries); added smoke test assertion that `index.html` exists in the installed package

## [1.8.2] - 2026-04-06

### Fixed
- **PyPI publish rejected wheel with duplicate ZIP entries** — replaced static `force-include` with a custom hatch build hook (`hatch_build.py`) that conditionally includes gitignored SPA files only when they exist on disk; fixes both the duplicate ZIP entries that PyPI rejects and the `FileNotFoundError` on editable installs in CI

## [1.8.1] - 2026-04-06

### Fixed
- **SPA static files missing from wheel** — added `[tool.hatch.build.targets.wheel.force-include]` mapping so `src/synapps/web/static` is packaged despite being gitignored; fixes `synapps serve` returning 404 when installed via pipx
- **CI editable install failure from force-include** — tracked `src/synapps/web/static/` directory via `.gitkeep` so the directory exists on fresh checkouts; hatch `force-include` no longer raises `FileNotFoundError` during `pip install -e`

## [1.8.0] - 2026-04-06

### Added
- **Auto-sync detects uncommitted working tree changes** — pre-query auto-sync now checks dirty tracked files (via `git diff --name-only`) when HEAD SHA matches the stored SHA; if any dirty file has mtime > `File.last_indexed` in the graph, `smart_index` runs to pick up the changes; subsequent queries skip re-sync because `last_indexed` advances past mtime after reindexing
- **Watcher callback error handling** — `on_change` and `on_delete` callbacks in `watch_project` are now wrapped in `try/except` so that exceptions (LSP crash, graph disconnection) are logged and don't silently kill the timer thread
- **`unwatch_project` updates stored commit SHA** — stopping a watch session now stores current HEAD as `last_indexed_commit` so the next auto-sync doesn't redundantly re-sync files the watcher already handled
- **Debounce timer cleanup** — fired timers are now removed from the internal dict, preventing unbounded growth during long watch sessions
- **Comprehensive auto-update integration tests** — 18 new integration tests covering committed changes, uncommitted changes, watcher reindex, cross-file edge consistency, staleness detection, unwatch SHA update, and smart_index strategy selection

## [1.7.3] - 2026-04-06

### Added
- **Webviewer section in README** — documents the built-in web UI with an Explore tab screenshot; highlights that the webviewer exposes the same tools available to AI agents via MCP
- **Pagination controls for Dead Code and Untested Methods** — `find_dead_code` and `find_untested` tools now show Previous/Next pagination controls below the results table instead of raw Limit/Offset number inputs; page indicator shows current page, total pages, and total item count; filter params (subdirectory, exclude_pattern) are preserved across page changes
- **`/explore` API endpoint for graph neighborhood traversal** — `GET /explore?full_name=X&depth=N` returns all nodes and edges reachable within N hops from a symbol as `{root, nodes, links}`, powered by two variable-length Cypher path queries (outgoing + incoming) with CONTAINS exclusion, link deduplication, and a safety ceiling at depth 50 to prevent runaway queries
- **Explore tab frontend integration** — new Explore tool in the Query sidebar category; `exploreToElements` transform converts `/explore` API response to D3 graph format with root node marked `isRoot=true` (yellow border), typed edge labels, and link deduplication; depth warning shown for depth >= 3; Explore added as first context menu item with Compass icon (depth=1 default via toolConfig)
- **CONTAINS edges in Explore traversal** — `_EXPLORE_EDGE_FILTER` now includes `CONTAINS` so Directory and Repository structural neighbors appear in explore results; `_KIND_LABELS` extended with `Directory` and `Repository` so `_extract_kind` recognizes those node types; frontend `getNodeColor` returns teal-family colors for Directory and Repository nodes

### Changed
- **Cypher query results now render in D3Graph with expand/remove/accumulation** — `execute_query` graph results (Cypher queries returning nodes with `full_name`) now flow through the same `accumulatedGraphElements` path as Find Usages and Find Callees, so double-click expand and right-click remove work correctly; non-graph Cypher results (scalars/tabular) automatically fall back to a DataTable; the `raw` resultType rendering path has been removed
- **Server-side pagination for find_dead_code and find_untested** — pagination now uses Cypher `SKIP`/`LIMIT` with a separate count query instead of fetching all rows and slicing in Python; `EXISTS { MATCH ... }` subqueries replaced with `size([...])` pattern for Memgraph compatibility
- **Additional graph indexes** — added indexes on `Class.name`, `Interface.name`, `Method.name`, `Method.file_path`, and label-only indexes on `Method`, `Class`, `Interface` (Memgraph only) for faster filtered scans

### Fixed
- **Broken source retrieval and scope resolution after 1-based line fix** — commits 1010bde/ea17df0 converted adapter line numbers to 1-based but `get_symbol_source` still used 1-based values as 0-based array indices (skipping first line of every symbol), all 8 call/type-ref extractors compared 1-based `symbol_map` lines against 0-based tree-sitter lines in `find_enclosing_scope`, and `class_lines` for assignment/type-ref extractors were not converted; all consumers now correctly convert 1-based graph lines to 0-based where needed
- **Missing INHERITS/IMPLEMENTS/CALLS edges after 1-based line fix** — commit 1010bde converted adapter line numbers to 1-based but three `symbol_map` lookups in `_index_base_types` and `_resolve_call` still used raw 0-based `def_line` from `request_definition` responses, causing silent resolution failures; `def_line + 1` conversion added to all three sites
- **Off-by-one line numbers in all LSP adapters** — `IndexSymbol.line` and `end_line` were 0-based (raw LSP protocol values) instead of 1-based (human-readable); all four adapters (Python, C#, TypeScript, Java) now add `+1` when converting from LSP coordinates, so webviewer code links and any other consumers of `IndexSymbol.line` point to the correct source line
- **`_p()` crashes on neo4j Relationship objects** — `execute_query` results containing Relationship objects (e.g., `MATCH ()-[r]->() RETURN r`) previously raised `AttributeError: object has no attribute 'labels'`; `_p()` now detects Relationships via duck-typing (`hasattr type, not hasattr labels`) and serializes them as `{"_type": "REFERENCES", ...props}` instead of crashing
- **Cypher query graph edge labels missing** — `cypherToElements` now detects relationship cells (objects with `_type` but no `full_name`) and passes `_type` as the edge label; clicking an edge in the D3 graph shows the relationship type (e.g., CALLS, REFERENCES); duplicate links are also deduplicated

## [1.7.2] - 2026-04-05

### Added
- **Rich context tab display** — `get_context_for` and `analyze_change_impact` now support `structured=True`, returning scope-appropriate dicts instead of markdown; the web route uses this for all context scopes
- **Impact scope as default in web UI** — the Context tab scope selector now defaults to `impact` (stats grid + DataTable sections); the empty `(full)` option is removed
- **`context` result type in `ResultPanel`** — renders structured context data with stats cards (impact scope) and labeled DataTable sections per array field (callers, callees, members, tests, dependencies, etc.)

### Fixed
- **Context tab scope default** — scope select now initializes to `impact` (was empty string, causing backend to fall through to full scope)
- **`constructor` field collision** — renamed structured JSON key from `constructor` to `constructor_source` to avoid JavaScript `Object.prototype.constructor` shadowing

## [1.7.1] - 2026-04-05

### Fixed
- **`_apply_limit` breaking MCP `find_usages` with `kind` param** — `limit=0` (the MCP default, meaning "no limit") was treated as "limit to zero items", causing `_apply_limit` to return a truncation dict instead of a plain list; pydantic validation then rejected the dict since the return type was `str | list[dict]`
- **`find_usages` MCP return type** — added `dict` to the union (`str | list[dict] | dict`) so explicit non-zero limits that trigger truncation pass pydantic validation

## [1.7.0] - 2026-04-05

### Added
- **D3 force-directed graph visualization** — new SVG-based graph renderer (`D3Graph.svelte`) using D3 force simulation replacing Cytoscape.js; draggable nodes with zoom/pan; hover tooltips; click/dblclick disambiguation (single-click=select, double-click=expand); right-click removes node with orphan cascade
- **Node detail panel** — `NodeDetailPanel.svelte` right-side overlay showing full_name, kind, file location (as `vscode://` link), signature; action buttons for Get Context, Find Usages, Find Callees, Get Hierarchy
- **`GET /api/expand_node` endpoint** — returns all directly connected neighbors for any symbol via `find_neighborhood()` graph query; deduplicates by `(full_name, rel_type, direction)` tuple
- **Color-coded circle nodes** — uniform circle shapes with distinct color palette per kind (Class=blue, Interface=purple, Method=green, Field/Property=orange, Package=teal, File=grey); CSS custom properties for light and dark themes
- **Edge selection with relationship label** — clicking an edge highlights it and shows a floating label at the midpoint with the relationship type (CALLS, INHERITS, etc.)
- **Neighbor highlighting on node select** — selecting a node dims non-neighbor nodes/edges to 0.2 opacity
- **Physics controls panel** — collapsible settings with sliders for Link Distance, Repel Force, and Collision Radius; physics disabled by default with static 300-tick pre-computation
- **Root node yellow border** — the queried symbol renders with a `#F0E68C` yellow stroke to distinguish it from expanded neighbors
- **`get_symbol_kind()` on `SynappsService`** — returns the primary label (Class, Method, etc.) for a resolved symbol
- **`_extract_kind()` helper in `lookups.py`** — extracts kind from neo4j node labels with fallback to `kind` property for plain dicts

### Changed
- **`find_usages` returns all results by default** — default `limit` changed from 20 to 0 (unlimited) across MCP tool, service layer, and web route; explicit `limit > 0` still truncates
- **`find_usages` and `find_callees` web routes return `queried_kind`** — response includes the queried symbol's kind so the frontend can color the center node correctly
- **`find_neighborhood` returns center node kind** — response includes `kind` field for the queried symbol alongside neighbors

### Fixed
- **Node kind extraction from neo4j labels** — `find_neighborhood` now reads kind from node labels instead of a non-existent `kind` property
- **Edge arrow scaling on selection** — SVG marker uses `markerUnits="userSpaceOnUse"` so arrowheads don't scale with stroke-width changes
- **Center node kind no longer hardcoded to Method** — transforms accept `queriedKind` parameter from API; `neighborhoodToElements` uses `data.kind || 'Method'`
- **`find_neighborhood` with neo4j Node objects** — `_extract()` uses `isinstance(node, Mapping)` instead of `isinstance(node, dict)` for neo4j compatibility
- **Drag teleport when physics is off** — drag handler syncs `d.x`/`d.y` directly; nodes stay pinned via `fx`/`fy` between drags
- **Layout stability on graph changes** — center force removed after initial layout; nodes pinned after positioning; `$effect` only re-simulates when new nodes exist

### Removed
- **Cytoscape.js dependencies** — `cytoscape`, `cytoscape-dagre`, `cytoscape-cose-bilkent` removed; `CytoscapeGraph.svelte`, `graphDiff.js`, `layouts.js` deleted

## [1.6.0] - 2026-04-04

### Added
- **`synapps serve` CLI subcommand** — starts a local FastAPI web server at `http://127.0.0.1:7433` with configurable `--host`, `--port`, and `--open/--no-open` browser launch options
- **FastAPI web package** — new `synapps.web` package with `create_app(service)` factory returning a FastAPI app with `/api` route prefix, disabled docs UI, and conditional SPA static file serving
- **neo4j serialization utility** — `serialize_result()` in `synapps.web.serialization` converts neo4j `Node`/`Relationship` objects to plain dicts suitable for FastAPI JSON responses
- **`fastapi>=0.115.0` dependency** — added to project dependencies for the web UI backend
- **Localhost web UI — SPA scaffold** — new `spa/` directory at repo root with Svelte 5 + Vite build tooling; builds to `src/synapps/web/static/`; includes full CSS design system (green palette, light/dark themes), app shell layout (48px header, 240px sidebar, flex content area), dark mode toggle with `localStorage` persistence, and sidebar with 9 curated tools in 4 categories
- **REST API route modules** — 9 JSON endpoints across 4 route modules (`search`, `navigate`, `analysis`, `query`) wrapping curated `SynappsService` methods; `ValueError` from service returns HTTP 400; all results pass through `serialize_result()` for neo4j type safety; `execute_query` uses POST with Pydantic `CypherRequest` body validation
- **Localhost web UI — tool interaction layer** — API client (`api.js`) for all 9 tool endpoints; `toolConfig.js` with per-tool endpoint, method, params, and result type; `SymbolLink` component with clickable names and `vscode://file/` editor links; `DataTable` reusable table renderer; `ToolForm` dynamic parameter form per tool; `ResultPanel` adaptive renderer (table/text/mixed/graph/raw); graph data transforms (`calleesToElements`, `hierarchyToElements`, `cypherToElements`, `isGraphResult`) for Cytoscape; vitest unit tests for `toolConfig.js` and `transforms.js`
- **Cytoscape.js graph layer** — `spa/src/lib/graph/` module with `transforms.js` (API→Cytoscape element converters for callees, hierarchy, and Cypher results), `layouts.js` (dagre for call graphs/hierarchy, cose-bilkent for architecture/Cypher), `nodeStyles.js` (theme-aware green palette node colors per symbol kind via CSS custom properties), and `CytoscapeGraph.svelte` (interactive graph component with click-to-expand, double-click-to-editor, hover tooltip, zoom/pan, and MutationObserver-based theme switching)
- **Graph visualization wired into ResultPanel** — `ResultPanel` now renders `CytoscapeGraph` for `graph` resultType tools (`find_callees`, `get_hierarchy`) with accumulated graph state; clicking a node expands its callees and merges new nodes/edges into the visible graph (deduplicated by id); Cypher `raw` results auto-detect graph shape via `isGraphResult` and render interactively with a raw JSON toggle
- **SPA build script** — `scripts/build_spa.sh` runs `npm ci && npm run build` from the `spa/` directory for reproducible production builds
- **Static file serving test** — `tests/unit/web/test_static.py` verifies that API routes are not shadowed by the SPA static file catch-all, and that `index.html` is served when the static directory exists

- **find_usages graph rendering** — `find_usages` now renders as an interactive graph with star layout (queried symbol at center, callers radiating outward) instead of plain text; includes click-to-expand node exploration
- **get_architecture auto-fire** — `get_architecture` now auto-fires on tab select with cached results; shows a Refresh button instead of a form with required path input
- **Analysis tool path removal** — `find_dead_code` and `find_untested` no longer require a `path` input; replaced with optional `subdirectory` filter
- **Location column** — table results now combine `file_path` and `line` into a single clickable Location column with `vscode://file/` links; display text shows relative paths (e.g. `src/MyService.cs:42`) instead of absolute paths
- **`/api/config` endpoint** — new backend endpoint returning `project_root` for frontend path relativization
- **`usagesToElements` graph transform** — new transform function converting `find_usages` API responses to Cytoscape graph elements with star topology

- **Context menu popover** — clicking a symbol name now shows a context menu with Find Usages, Find Callees, Get Hierarchy (Class/Interface only per D-05), and Open in Editor; replaces the broken handleSymbolClick -> empty search tab behavior
- **Incremental graph updates** — node expansion now adds new nodes without repositioning existing ones (D-11); new top-level queries fully reset the graph (D-12); uses graphKey prop to distinguish reset vs incremental paths
- **`GET /api/get_context_for` endpoint** — new backend route in `navigate.py` returning the full context string for a symbol; accepts `full_name` and optional `scope` params; `max_lines=-1` (unlimited); returns 400 on ambiguous name, 404 when symbol not found
- **Context tool in sidebar and context menu** — `get_context_for` registered in `toolConfig.js` with `text` resultType and scope dropdown; appears as fourth item in Navigate sidebar; "Get Context" is the first item in the context menu for all symbol kinds (no kind guard)
- **Scope dropdown `(full)` label** — `ToolForm.svelte` select option now renders `param.defaultLabel || '(any)'` so the `get_context_for` scope dropdown shows "(full)" for the empty option while all other selects continue showing "(any)"
- **Text result styling** — `.text-result` CSS updated to `font-size: 14px`, `line-height: 1.6`, and explicit `font-family: monospace` per UI-SPEC
- **Context menu auto-fetch** — selecting any action from the context menu (Find Usages, Find Callees, Get Hierarchy, Get Context) now prefills the symbol name and immediately fetches results; `ToolForm` accepts an `initialValues` prop that triggers auto-submit via `untrack()`; fixes the prior behavior where context menu navigated to an empty tab

### Fixed
- **SPA static file resolution** — `create_app()` now checks package dir, explicit override, and `CWD/src/synapps/web/static/` for the built SPA, fixing 404s when running via editable install or pipx
- **Analysis routes required path param** — `get_architecture`, `find_dead_code`, and `find_untested` web routes now accept `path` as optional (`str | None = None`) so the SPA can call them without a vestigial path parameter
- **Analysis routes missing subdirectory param** — all three analysis routes now accept an optional `subdirectory` query parameter for future directory-scoped analysis
- **find_usages web route returned markdown** — web route now passes `structured=True` to the service method, returning a JSON list of `{full_name, kind, file_path, line}` dicts suitable for graph rendering
- **Svelte effect_update_depth_exceeded on find_usages** — `graphKey` mutation inside `$effect` caused infinite reactive loop; wrapped in `untrack()` to break the dependency cycle

### Changed
- **Unit test cleanup** — removed ~19 redundant, tautological, and brittle tests; merged duplicate doctor pass/fix assertions; replaced fragile Cypher brace-counting parser and exact-count schema assertions; renamed 5 misleading test names

## [1.5.1] - 2026-04-03

### Fixed
- **C#/TypeScript/Python indexing crash** — `CSharpTypeRefExtractor`, `TypeScriptTypeRefExtractor`, and `PythonTypeRefExtractor` now accept the `field_symbol_map` keyword argument added in 1.5.0 for Java field-level REFERENCES; previously indexing any non-Java project raised `TypeError: extract() got an unexpected keyword argument 'field_symbol_map'`

## [1.5.0] - 2026-04-03

### Added
- **Dead code exclusions for ASP.NET Core Startup/Program conventions** — `find_dead_code` and `find_untested` now exclude `Configure` and `ConfigureServices` in `Startup` and `Program` classes; `ConfigureWebHost`, `CreateHostBuilder`, and `CreateWebHostBuilder` are excluded by name; `Authorize`, `AllowAnonymous`, `GlobalSetup`, and `GlobalCleanup` attributes are excluded as framework entry points
- **External framework call stub recording** — new `ExternalCallStubber` class and `EXTERNAL_FRAMEWORK_METHODS` allowlist (8 types: RestTemplate, MongoTemplate, JdbcTemplate, KafkaTemplate, RabbitTemplate, ObjectMapper, WebClient, DiscoveryClient) create synthetic stub `Method` nodes so CALLS edges can be recorded for framework method invocations; stubs are excluded from dead code detection via a new `stub` property on `Method` nodes
- **End-to-end external framework call recording for Java** — `SymbolResolver` now accepts an `ExternalCallStubber` and invokes it at all unresolved call-site exit points; both full-index and file-reindex paths record `RestTemplate`, `MongoTemplate`, and other allowlisted framework calls as `CALLS` edges to synthetic stub nodes
- **`JavaCallExtractor` returns 5-tuples with receiver variable name** — `extract()` now returns `(caller, callee, line, col, receiver_name)` where `receiver_name` is the variable identifier before the dot for `receiver.method()` calls, or `None` for bare calls and constructors
- **Spring Data repository stub injection** — Spring Data interfaces (extending `CrudRepository`, `JpaRepository`, etc.) now get synthetic stub `Method` nodes for common CRUD operations (`save`, `findById`, `delete`, etc.), allowing CALLS edges from service classes to repository methods
- **Java field type extraction and `find_dependencies` fields section** — `JavaFieldTypeExtractor` extracts declared types from Java fields; `find_dependencies` now returns a `"fields"` section for classes with typed `Field` nodes (backward-compatible: classes without typed fields return a plain list)
- **`stub` field on `Method` nodes** — `upsert_method` now accepts a `stub=False` parameter; stub methods are written with `n.stub = true` in the graph and excluded from dead code queries via `coalesce(m.stub, false)`
- **Dead code `main(String[])` exclusion** — JDT LS stores Java main methods as `main(String[])` not `main`; `_build_base_exclusion_where` now handles both forms

### Fixed
- **Dead code false positives for Java `main()`, `configure()`, and `@Override`** — extended exclusion patterns for Spring Security adapters/configurers and Java `@Override` annotation
- **Dead code false positives for lifecycle methods** — `Dispose`, `DisposeAsync`, `Close`, `Finalize`, `OnNavigatedTo`, `OnInitialized`, and `OnInitializedAsync` excluded
- **C# null-conditional calls not indexed** — `obj?.Method()` patterns now produce CALLS edges
- **Mutation guard false positives in `execute_query`** — string literals and dotted property access stripped before keyword checking
- **Architecture stats accuracy** — Package and Endpoint nodes added to `total_symbols` count; HTTP client calls removed from architecture overview to reduce noise
- **Dead code pagination** — `find_dead_code` and `find_untested` use Python-level offset slicing instead of Cypher SKIP
- **C# generic IMPLEMENTS/INHERITS edges** — restored edges for generic C# types like `Repository<T>`

### Changed
- **`find_callees` and server instructions** — document known graph boundary: calls to external framework types are not indexed; agents should use `get_context_for` for framework call sites

## [1.4.14] - 2026-04-02

### Added
- **Indexing opt-out in init wizard** — users can skip Memgraph startup and indexing during `synapps init` while still persisting DB mode config
- **Unified agent configuration** — init wizard now presents a single multi-select for all AI harnesses (Claude Code, Cursor, Copilot, etc.) with auto-detected ones pre-checked
- **Java call resolution diagnostics** — `_resolve_file` now logs skipped call/type-ref counts on failure and emits a resolution summary when >30% of calls are unresolved

### Fixed
- **Init wizard language filter bug** — `smart_index` now respects `allowed_languages` parameter; previously all detected languages were indexed regardless of user selection
- **`SynappsService.smart_index` facade** — `allowed_languages` parameter is now forwarded through the service facade (was silently dropped, causing the wizard's language filter to be unreachable)
- **`get_context_for` TypeError regression** — `suggest_similar_names` query now guards against `None` `full_name` values; returns clean "Symbol not found" instead of raw TypeError
- **Dead code inflation** — `_FRAMEWORK_ATTRIBUTES` now includes lowercase Java Spring/JPA annotations (`@bean`, `@getmapping`, etc.) matching `JavaAttributeExtractor`'s `.lower()` storage
- **Architecture hotspots skewed by vendored JS** — `_VENDORED_PATH_PATTERN` extended to match `static/js/` directories and named CDN library files (angular.js, vue.js, jquery.js, etc.)
- **Duplicate package names in `get_architecture`** — package query now returns `p.full_name` instead of `p.name` for fully-qualified package names
- **Package `file_count: 0` in `get_architecture`** — replaced unreliable `STARTS WITH` string matching with `CONTAINS` edge traversal for accurate file counts

## [1.4.13] - 2026-04-01

### Added
- **C# ASP.NET Core Minimal API endpoint detection** — `MapGet`, `MapPost`, `MapPut`, `MapDelete`, and `MapPatch` calls now produce HTTP_ENDPOINT nodes in the graph
- **`RestTemplate.exchange()` detection** — Java HTTP extractor now recognizes `RestTemplate.exchange()` calls with `HttpMethod.X` verb arguments
- **MSTest attribute support** — `[TestMethod]` and `[DataTestMethod]` attributes now produce TESTS edges

### Fixed
- **7 Java tool issues** — import routing, `_clean_java_full_name`, per-file source root detection, anonymous class filter, `kind=4` NAMESPACE mapping, and accurate line numbers via `selectionRange.start.line`
- **`scope=edit` empty-state visibility** — `get_context_for` with `scope=edit` now shows a clearer message when no callers/callees exist
- **HTTP endpoint section in `get_context_for`** — edit scope now includes HTTP endpoints associated with the symbol
- **Result limits** — `find_dead_code` and `find_untested` now accept a `limit` parameter to cap output size
- **`_get_service` singleton invalidation** — CLI service cache now invalidates when the target project path changes
- **`Repository.name`** — `upsert_repository` now derives `Repository.name` from `os.path.basename(path)` instead of storing the full path

## [1.4.12] - 2026-04-01

### Added
- **Java package extraction** — package declarations are now extracted via tree-sitter and wired as Package CONTAINS edges in the graph

### Fixed
- **NUnit attribute support** — `[Test]` and `[TestCase]` attributes now produce TESTS edges (previously only `[Fact]`/`[Theory]` from xUnit were recognized)
- **Java method attribute lookup** — parameter signatures are now stripped before matching attribute names, fixing false negatives on annotated methods

## [1.4.11] - 2026-03-31

### Fixed
- **Cursor MCP config detection** — `synapps init` no longer requires `.cursor/` directory to pre-exist; the directory is created if needed

## [1.4.10] - 2026-03-31

### Added
- **Agent instruction file installation** — `synapps init` now installs agent instruction files (CLAUDE.md, AGENTS.md, GEMINI.md, etc.) into projects for immediate AI agent context

## [1.4.8] - 2026-03-31

### Fixed
- **`find_usages` parameter cleanup** — removed misleading `include_test_breakdown` parameter that was accepted but silently ignored

## [1.4.7] - 2026-03-31

### Added
- **Version display** — `synapps status` CLI command and `list_projects` MCP tool now include the Synapps version in their output
- **Cross-language integration tests** — 30+ new integration tests ensuring MCP and CLI tool parity across all 4 language suites (C#, Python, TypeScript, Java)

## [1.4.6] - 2026-03-31

### Fixed
- **DISPATCHES_TO callers included in caller lookups** — `find_callers` and `find_callers_with_sites` now include callers that reach a method via interface dispatch (DISPATCHES_TO edges), which were previously excluded

## [1.4.5] - 2026-03-31

### Fixed
- **C# generic method call extraction** — generic invocations like `_service.Method<T>()` and `new List<string>()` now correctly produce CALLS edges; previously the `generic_name` AST node in `invocation_expression` and `object_creation_expression` was not matched by the tree-sitter query, silently dropping all generic method calls from the graph

## [1.4.4] - 2026-03-30

### Fixed
- **Cross-file edges preserved during incremental reindex** — `reindex_file` no longer drops CALLS and DISPATCHES_TO edges to symbols defined in other files

## [1.4.3] - 2026-03-30

### Fixed
- **Declaring-type lookup scoped to current file** — `_index_base_types()` now restricts declaring-type resolution to the current file, preventing cross-file false-positive base type matches

## [1.4.2] - 2026-03-30

### Changed
- **LSP-based base type resolution** — `_index_base_types()` now uses Language Server Protocol for base type resolution instead of namespace disambiguation; all 4 language extractors return 5-tuples with position data; dead namespace disambiguation functions removed

## [1.4.1] - 2026-03-30

### Fixed
- **C# generic HTTP method extraction** — `GetFromJsonAsync<T>`, `PostAsJsonAsync<T>`, and other generic `System.Net.Http.Json` methods now correctly produce HTTP_CALLS edges; previously the `generic_name` AST node caused the method name to be missed
- **False-positive IMPLEMENTS edges across projects** — structural protocol dispatch (matching classes to interfaces by method names) is now restricted to Python only; C#, Java, and TypeScript use nominal typing where IMPLEMENTS edges come from LSP declarations
- **Cursor hooks installed at user-level instead of project-level** — `synapps init` now writes Cursor hooks to `<project>/.cursor/hooks.json` instead of `~/.cursor/hooks.json`

## [1.4.0] - 2026-03-30

### Added
- **Pre-tool hooks for agent nudging** — gate scripts that remind AI agents (Claude Code, Cursor, Copilot) to query the Synapps graph before reading or editing files; installed via `synapps init`
- **`find_dead_code` MCP tool** *(experimental)* — find methods with zero callers, excluding tests, HTTP handlers, interface implementations, dispatch targets, constructors, and overrides
- **`find_tests_for` MCP tool** *(experimental)* — find which tests cover a given method via direct TESTS edge lookup
- **`find_untested` MCP tool** *(experimental)* — find production methods with no test coverage (same exclusions as `find_dead_code`)
- **`get_architecture` MCP tool** — single-call architecture overview returning packages, hotspots, HTTP endpoint map, and project stats
- **Import-based call resolution fallback** — tree-sitter-based `build_import_map` provides call resolution when the language server misses untyped symbols (TypeScript)
- **`@/` path alias resolution** — `tsconfig.json` path aliases (e.g., `@/*`) are resolved during TypeScript import mapping
- **Hook installer framework** — agent detector, per-agent config upsert/removal, gate script content constants, and force/skip logic
- **Shared vs dedicated database prompt** — `synapps init` now asks whether to use a shared or dedicated Memgraph instance
- **CI integration test job** — GitHub Actions workflow with Memgraph, .NET SDK, Node.js, and Java

### Changed
- **MCP tools consolidated from 21 to 15** — removed `get_symbol`, `get_symbol_source`, `find_callers`, `trace_call_chain`; merged `analyze_change_impact` into `get_context_for(scope='impact')` and `trace_http_dependency` into `find_http_endpoints(trace=True)`
- Removed standalone `synapps install` / `synapps uninstall` CLI commands — hooks are now offered during `synapps init`
- Removed CLI commands redundant with MCP tools
- Two-tone ASCII banner — SYN in dark green, APPS in light green
- Removed obsolete docs (demo, HTTP strategy, distribution, MCP consolidation)

### Fixed
- Strip JSONC comments from `tsconfig.json` before parsing path aliases
- `get_context_for` now resolves impact scope before symbol lookup
- `synapps init` auto-starts Memgraph instead of failing when the container is not running
- CI per-test timeout no longer bounds fixture setup (`timeout_func_only`)

## [1.3.0] - 2026-03-28

### Changed
- **Renamed project from Synapse to Synapps** — repository moved to SynappsCodeComprehension org
- Streamlined README from 777 to 449 lines
- Fixed HTTP client libraries table — added C#/Java, removed unsupported Python libs

## [1.2.0] - 2026-03-28

### Added
- **PyPI distribution** — install via `pip install synapps-mcp` (package renamed from `synapps` to `synapps-mcp`)
- **`synapps init` command** — interactive setup wizard that detects project languages, checks prerequisites, indexes the project, and configures MCP clients (Claude Desktop, Claude Code, Cursor, Copilot)
- **`__version__` attribute** — `synapps.__version__` returns the installed version at runtime via `importlib.metadata`
- **CI/CD publish workflow** — `.github/workflows/publish.yml` builds, smoke-tests, and publishes to PyPI on `v*` tags via OIDC trusted publishing
- **Wheel smoke test** — CI verifies `solidlsp` and all 4 tree-sitter grammars are included in the published wheel
- **Platform-aware doctor fix strings** — every failed check shows exact install commands for macOS (`brew`) or Linux (`apt-get`)
- **Actionable error messages** — Docker-not-running, Memgraph connection lost, project-not-indexed, and language server timeout errors all show recovery commands
- **MCP client auto-detection** — `synapps init` finds installed MCP clients and offers to write config with atomic merge (preserves existing server entries)

### Changed
- Package distribution name changed from `synapps` to `synapps-mcp` (Python import paths unchanged)
- `synapps doctor` now exits with code 1 when any check fails (enables use in scripts and CI)
- SYNAPPS logo banner moved from `synapps index` (first run) to `synapps init`
- Version bumped from 1.0.0 to 1.2.0

### Fixed
- Language server timeout no longer aborts the entire indexing pass — timed-out files are skipped with a warning naming the file

## [1.1.0] - 2026-03-28

### Added
- `find_http_endpoints` MCP tool — search endpoints by route pattern, HTTP method, or language
- `trace_http_dependency` MCP tool — find server handler and all client call sites for an endpoint
- Route conflict detection — indexer warns when multiple methods serve the same (HTTP method, route) pair
- JAX-RS annotation support (`@Path`, `@GET`, `@POST`, etc.) in Java server-side extraction
- README HTTP Endpoint Tracing section with supported frameworks table, tool examples, and known limitations

### Fixed
- Nested class HTTP call attribution now uses narrowest-range matching instead of last-match across all 4 extractors
- JAX-RS route constraints (`{param: regex}`) correctly normalized to `{param}` during extraction

### Changed
- HTTP endpoint extraction now runs by default — no longer requires `experimental.http_endpoints` config flag
- MCP tool count increased from 19 to 21
- Removed all "experimental" qualifiers from schema notes, agent instructions, and log messages

## [1.0.0] - 2026-03-26

### Added
- Multi-language indexing: C#, Python, TypeScript/JavaScript, Java
- Graph-based code intelligence via Memgraph
- MCP server with 25+ tools for AI agents
- CLI with full query and management capabilities
- Automatic per-project Docker container management
- Incremental sync via git diff
- Live file watching with `synapps watch`
- Interface dispatch resolution in call graph traversal
- Impact analysis with test coverage detection
- Token-efficient output format for AI consumption
- Scoped context retrieval (`structure`, `method`, `edit`)
- Architectural audit rules
- Symbol summaries (manual and auto-generated)
