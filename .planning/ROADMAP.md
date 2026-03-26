# Roadmap: Synapse

## Overview

Build the `synapse doctor` / `check_environment` feature from the ground up: a typed data model first, then Docker/Memgraph checks with a working CLI output surface, then all eight language server checks, then the MCP tool that exposes the same results to AI agents. Each phase delivers a coherent, independently testable capability before the next begins.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Core Data Model** - Define CheckResult, DoctorCheck protocol, and DoctorService with full unit test coverage using stub checks (completed 2026-03-23)
- [ ] **Phase 2: Infrastructure Checks and CLI** - Docker and Memgraph health checks wired to `synapse doctor` Rich table output with exit code discipline
- [x] **Phase 3: Language Server Checks** - Eight checks covering .NET, C#, Node.js, TypeScript, Python, pylsp, Java runtime, and Java LS with inline fix instructions (completed 2026-03-23)
- [x] **Phase 4: MCP Tool** - `check_environment` MCP tool exposing DoctorService results as a structured dict for agent self-diagnosis (completed 2026-03-23)

## Phase Details

### Phase 1: Core Data Model
**Goal**: The shared data model and service scaffold that every subsequent component depends on exists and is fully unit-tested with stub checks
**Depends on**: Nothing (first phase)
**Requirements**: CORE-01, CORE-02, CORE-03
**Success Criteria** (what must be TRUE):
  1. A CheckResult object can be constructed with name, status (pass/warn/fail), detail message, and fix instruction, and all fields are readable
  2. A stub class implementing the DoctorCheck protocol passes isinstance checks and can be executed by DoctorService
  3. DoctorService runs all registered checks, collects results, and returns a DoctorReport without raising exceptions even when individual checks fail
**Plans**: 2 plans

Plans:
- [x] 01-01-PLAN.md — Implement synapse.doctor package (base.py, service.py, __init__.py) with TDD unit tests
- [x] 01-02-PLAN.md — Reclassify CORE-04 from Phase 1 to Phase 2 (gap closure)

### Phase 2: Infrastructure Checks and CLI
**Goal**: Users can run `synapse doctor` and see a color-coded table showing Docker daemon and Memgraph reachability, with actionable fix instructions and a non-zero exit code on failure
**Depends on**: Phase 1
**Requirements**: CORE-04, DOCK-01, DOCK-02, CLI-01, CLI-02, CLI-03
**Success Criteria** (what must be TRUE):
  1. `synapse doctor` prints a Rich table with one row per check showing name, status color (green/yellow/red), and detail message
  2. When Docker daemon is unreachable, the table row shows FAIL status and the fix instruction column contains an actionable install/start command
  3. When Memgraph container is not running, the table row shows FAIL and the fix instruction references how to start the container
  4. `synapse doctor` exits with code 1 when any check fails and code 0 when all checks pass
  5. Each failing row displays its fix instruction inline — no separate output section required
**Plans**: 2 plans

Plans:
- [x] 02-01-PLAN.md — Implement DockerDaemonCheck and MemgraphBoltCheck with TDD unit tests
- [x] 02-02-PLAN.md — Implement synapse doctor CLI command with Rich table output

### Phase 3: Language Server Checks
**Goal**: `synapse doctor` reports accurate pass/warn/fail status for all four language stacks (C#, TypeScript, Python, Java), using functional subprocess invocation rather than PATH-only presence detection
**Depends on**: Phase 2
**Requirements**: LANG-01, LANG-02, LANG-03, LANG-04, LANG-05, LANG-06, LANG-07, LANG-08
**Success Criteria** (what must be TRUE):
  1. `synapse doctor` shows a row for each of the eight language checks: dotnet runtime, csharp-ls/OmniSharp, node, typescript-language-server, python3, pylsp, java, and Eclipse JDT LS
  2. Each check reports the resolved absolute binary path in its detail message, not just pass/fail
  3. A binary installed via nvm or pyenv that is on PATH but not functionally invocable produces a FAIL result, not a false PASS
  4. Each failing language check shows an actionable install instruction (docs link or install command) in the fix column
  5. All subprocess calls complete within 10 seconds or produce a FAIL result with a timeout message instead of hanging
**Plans**: 5 plans

Plans:
- [x] 03-01-PLAN.md — Implement DotNetCheck + CSharpLSCheck with TDD unit tests (C# stack)
- [x] 03-02-PLAN.md — Implement NodeCheck + TypeScriptLSCheck with TDD unit tests (TypeScript stack)
- [x] 03-03-PLAN.md — Implement PythonCheck + PylspCheck with TDD unit tests (Python stack)
- [x] 03-04-PLAN.md — Implement JavaCheck + JdtlsCheck with TDD unit tests (Java stack)
- [x] 03-05-PLAN.md — Wire all 8 new checks into app.py and update test_cli_doctor.py

### Phase 4: MCP Tool
**Goal**: AI agents can call `check_environment` via MCP and receive a structured result they can reason about, with the same underlying data as `synapse doctor`
**Depends on**: Phase 3
**Requirements**: MCP-01
**Success Criteria** (what must be TRUE):
  1. Calling `check_environment` via MCP returns a dict (not formatted text) with a list of check results each containing name, status, detail, and fix fields
  2. The MCP tool result and the `synapse doctor` table are driven by the same DoctorService call — no divergent logic
  3. An agent can parse the structured return value to determine which dependencies are missing without scraping human-readable text
**Plans**: 1 plan

Plans:
- [x] 04-01-PLAN.md — Implement check_environment MCP tool with TDD unit tests

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Core Data Model | 1/1 | Complete   | 2026-03-23 |
| 2. Infrastructure Checks and CLI | 1/2 | In Progress|  |
| 3. Language Server Checks | 5/5 | Complete   | 2026-03-23 |
| 4. MCP Tool | 1/1 | Complete   | 2026-03-23 |

### Phase 5: Expand HTTP endpoint mapping to all languages

**Goal:** Every supported language (C#, TypeScript, Python, Java) has both server-side (SERVES) and client-side (HTTP_CALLS) HTTP extraction, with one-hop constant resolution and cross-language integration testing
**Requirements**: HTTP-PY-01, HTTP-PY-02, HTTP-TS-01, HTTP-JAVA-01, HTTP-JAVA-02, HTTP-CS-01, HTTP-INFRA-01
**Depends on:** Phase 4
**Success Criteria** (what must be TRUE):
  1. Python extractor produces SERVES edges for FastAPI, Flask, and Django REST endpoints and HTTP_CALLS edges for requests library calls
  2. TypeScript extractor produces SERVES edges for Express, Fastify, and Hono route handlers
  3. Java extractor produces SERVES edges for Spring @RequestMapping/@GetMapping annotations and HTTP_CALLS edges for RestTemplate, WebClient, and java.net.http calls
  4. C# extractor produces HTTP_CALLS edges for HttpClient and RestSharp calls (SERVES already exists)
  5. One-hop imported constant resolution resolves URL strings stored in constants files when used in HTTP calls
  6. Cross-language integration test verifies endpoint matching between at least two different language pairs
**Plans:** 5/5 plans complete

Plans:
- [x] 05-01-PLAN.md — Python HTTP extractor (FastAPI/Flask/Django SERVES + requests HTTP_CALLS) with plugin wiring
- [x] 05-02-PLAN.md — TypeScript server-side extension (Express/Fastify/Hono SERVES added to existing extractor)
- [x] 05-03-PLAN.md — Java HTTP extractor (Spring SERVES + RestTemplate/WebClient/java.net.http HTTP_CALLS) with plugin wiring
- [x] 05-04-PLAN.md — C# client-side extension (HttpClient/RestSharp HTTP_CALLS added to existing extractor)
- [x] 05-05-PLAN.md — Plugin wiring test updates, cross-file constant resolution, cross-language integration test

### Phase 6: HTTP Endpoint Extraction Fixes — JAX-RS support and route normalization improvements

**Goal:** [To be planned]
**Requirements**: TBD
**Depends on:** Phase 5
**Plans:** 0 plans

Plans:
- [ ] TBD (run /gsd:plan-phase 6 to break down)

### Phase 7: MCP Tools Consolidation

**Goal:** Reduce MCP tool count from 30 to ~20 by merging overlapping tools, removing redundant ones, and demoting admin/diagnostic tools to CLI-only
**Requirements**: CONSOL-01, CONSOL-02, CONSOL-03, CONSOL-04, CONSOL-05, CONSOL-06, CONSOL-07, CONSOL-08, CONSOL-09
**Depends on:** Phase 6
**Success Criteria** (what must be TRUE):
  1. MCP server registers exactly ~20 tools (down from 30)
  2. `summary` tool with action param replaces separate set_summary/get_summary/list_summarized tools
  3. `find_callees` with depth param replaces standalone get_call_depth tool
  4. `find_usages` with kind and include_test_breakdown params replaces find_type_references and find_type_impact tools
  5. `list_projects` with path param replaces standalone get_index_status tool
  6. check_environment, delete_project, find_interface_contract, and audit_architecture are not registered as MCP tools
  7. MCP instructions document consolidated tools and list CLI-only capabilities
**Plans:** 1/2 plans executed

Plans:
- [x] 07-01-PLAN.md — Merge, remove, and demote tools in tools.py with unit test updates
- [ ] 07-02-PLAN.md — Rewrite MCP instructions and update all integration tests
