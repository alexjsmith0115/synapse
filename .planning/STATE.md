---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: Ready to execute
last_updated: "2026-03-26T02:16:28.632Z"
last_activity: 2026-03-26
progress:
  total_phases: 7
  completed_phases: 5
  total_plans: 17
  completed_plans: 16
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-23)

**Core value:** AI coding agents can instantly understand code structure and relationships across an entire codebase without reading every file.
**Current focus:** Phase 07 — mcp-tools-consolidation

## Current Position

Phase: 07 (mcp-tools-consolidation) — EXECUTING
Plan: 2 of 2

## Performance Metrics

**Velocity:**

- Total plans completed: 0
- Average duration: —
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**

- Last 5 plans: —
- Trend: —

*Updated after each plan completion*
| Phase 01 P01 | 1 | 3 tasks | 6 files |
| Phase 02-infrastructure-checks-and-cli P01 | 8 | 2 tasks | 5 files |
| Phase 02-infrastructure-checks-and-cli P02 | 2 | 2 tasks | 2 files |
| Phase 03-language-server-checks P02 | 8 | 2 tasks | 3 files |
| Phase 03-language-server-checks P04 | 525514min | 2 tasks | 3 files |
| Phase 03-language-server-checks P03 | 15 | 2 tasks | 3 files |
| Phase 03-language-server-checks P01 | 3 | 2 tasks | 3 files |
| Phase 03-language-server-checks P05 | 8 | 2 tasks | 2 files |
| Phase 04-mcp-tool P01 | 1 | 1 tasks | 2 files |
| Phase 05 P02 | 3 | 1 tasks | 2 files |
| Phase 05 P04 | 3 | 1 tasks | 2 files |
| Phase 05 P01 | 4 | 2 tasks | 4 files |
| Phase 05 P03 | 5 | 2 tasks | 4 files |
| Phase 05 P05 | 11 | 2 tasks | 3 files |
| Phase 07 P01 | 4 | 2 tasks | 3 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Init: Report + instructions only — no auto-install; both CLI and MCP interfaces; external deps only, not internal Synapse state
- [Phase 01]: CheckStatus uses Literal alias (not Enum/StrEnum) — mirrors existing SymbolKindLiteral/AuditRuleLiteral patterns
- [Phase 01]: warn status is NOT a failure — has_failures False for warn-only reports (degraded-but-working semantics)
- [Phase 01]: Real stub classes in service tests (not MagicMock) — avoids Protocol isinstance false positives
- [Phase 02]: Bolt probe copied into memgraph_bolt.py (not imported from ContainerManager) — enforces leaf-layer isolation (D-04)
- [Phase 02]: warn (not fail) for Memgraph when Docker is down (D-05) — exits 0, degraded-but-working semantics
- [Phase 02-infrastructure-checks-and-cli]: Module-level imports for DockerDaemonCheck/MemgraphBoltCheck in app.py required for patchable test targets; doctor() does not call _get_service() (D-04)
- [Phase 03-02]: TypeScriptLSCheck returns warn (not fail) when node is absent — consistent with D-05 degraded-but-working semantics; typescript-language-server cannot be meaningfully checked without node
- [Phase 03-02]: capture_output=True without text=True for both NodeCheck and TypeScriptLSCheck — returncode is the only signal, no string parsing needed
- [Phase 03-04]: JavaCheck uses returncode (not stdout) as pass signal — java -version writes to stderr by JVM convention
- [Phase 03-04]: JdtlsCheck warns (not fails) when java absent — degraded-but-working semantics, consistent with other skip-if-prereq-absent checks
- [Phase 03-04]: JdtlsCheck uses Path.home() and glob.glob to probe equinox launcher jar, mirroring eclipse_jdtls.py without importing SolidLSPSettings
- [Phase 03-language-server-checks]: python3.py filename (not python.py) prevents shadowing stdlib; PylspCheck warns when python3 absent (degraded-not-failed semantics)
- [Phase 03-language-server-checks]: DotNetCheck uses --list-runtimes + Microsoft.NETCore.App regex (not --version) to confirm runtime is actually installed (D-03)
- [Phase 03-language-server-checks]: CSharpLSCheck warns (not fails) when dotnet absent — skip-if-runtime-absent pattern (D-04); text=True required for regex stdout parsing
- [Phase 03-language-server-checks]: Module-level imports for all 10 check classes in app.py required for synapse.cli.app.* patch() targets to resolve correctly in tests
- [Phase 03-language-server-checks]: _AllChecksPassingContext helper with _ALL_CHECKS table centralizes 10-check patch setup across all CLI doctor tests
- [Phase 04-mcp-tool]: check_environment instantiates its own check list (not injected) — tool owns its environment check contract independently of SynapseService
- [Phase 04-mcp-tool]: Module-level imports for all 10 check classes in tools.py required for synapse.mcp.tools.* patch targets to resolve correctly in tests — consistent with app.py pattern from Phase 03
- [Phase 05]: TypeScript server route disambiguation: arrow_function/function_expression second arg -> SERVES; identifier/object -> HTTP_CALLS (preserves api.post('/items', data) as client call)
- [Phase 05]: _HTTPCLIENT_VERB_MAP and _RESTSHARP_METHOD_MAP as module-level dicts — mirrors existing _HTTP_VERB_MAP pattern, aligns with D-07
- [Phase 05]: enclosing-symbol lookup uses sorted-range pattern mirrored from TypeScript extractor
- [Phase 05-01]: _FASTAPI_FLASK_VERBS frozenset covers both FastAPI verb decorators and Flask 2.0+ shorthand in a single check — avoids branching on framework type
- [Phase 05-01]: F-string detection uses interpolation child nodes (not prefix check) — works correctly with tree-sitter Python grammar which parses f-strings as string nodes with interpolation children
- [Phase 05-01]: Django ViewSet routes only emitted for methods actually present in class body — prevents phantom routes for inherited methods not overridden
- [Phase 05]: _method_invocation_name() scans backwards from argument_list to find method name — handles chained builder calls where first identifier is the receiver, not the method
- [Phase 05]: WebClient verb detected via object field of .uri() invocation; java.net.http verb detected by parent-chain walk from URI.create() through argument_list and .uri() up to .GET()/.POST()
- [Phase 05]: Cross-language test in tests/integration/ (no @pytest.mark.integration) — spans subsystems but needs no external services
- [Phase 05]: collect_cross_file_constants filters to URL-like values at collection time — reduces noise in resolution maps
- [Phase 07]: summary(action) tool uses SummaryActionLiteral = Literal['get','set','list'] — mirrors existing SymbolKindLiteral pattern
- [Phase 07]: find_callees depth param bypasses include_interface_dispatch and limit — both irrelevant to the call-tree path via get_call_depth

### Pending Todos

None yet.

### Roadmap Evolution

- Phase 5 added: Expand HTTP endpoint mapping to all languages
- Phase 6 added: HTTP Endpoint Extraction Fixes — JAX-RS support and route normalization improvements
- Phase 7 added: MCP Tools Consolidation — reduce from 30 to ~20 tools by merging, removing, and demoting overlapping tools

### Blockers/Concerns

- Research flag: Bolt handshake reuse — whether to call ContainerManager._wait_for_bolt() or extract socket logic into a shared util (resolve during Phase 2 planning)
- Research flag: Platform-specific install instructions scope — data model has `fix` field; confirm whether Phase 3 populates with generic links or platform-keyed commands before Phase 3 planning begins
- Research flag: Java language server (LANG-07, LANG-08) — in scope per REQUIREMENTS.md but omitted from ARCHITECTURE.md file layout; review before Phase 3 planning

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260323-u1a | Add ASCII banner to Synapse CLI on first index | 2026-03-24 | 107590a | [260323-u1a-add-ascii-banner-to-synapse-cli-on-first](./quick/260323-u1a-add-ascii-banner-to-synapse-cli-on-first/) |

## Session Continuity

Last activity: 2026-03-26
Resume file: None
