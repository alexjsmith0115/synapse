# Requirements: Synapse

**Defined:** 2026-03-23
**Core Value:** AI coding agents can instantly understand code structure and relationships across an entire codebase without reading every file.

## v1 Requirements

Requirements for the verify-install / doctor feature. Each maps to roadmap phases.

### Core Infrastructure

- [x] **CORE-01**: CheckResult data model captures name, status (pass/warn/fail), detail message, and fix instruction per check
- [x] **CORE-02**: DoctorCheck protocol defines interface for individual dependency checks
- [x] **CORE-03**: DoctorService runs all registered checks and returns collected results
- [x] **CORE-04**: All checks use subprocess invocation with timeout, not just PATH lookup

### Docker & Memgraph

- [x] **DOCK-01**: Docker check verifies daemon is reachable via ping (not just binary on PATH)
- [x] **DOCK-02**: Memgraph check verifies container is running and reachable via Bolt protocol

### Language Servers

- [x] **LANG-01**: .NET SDK check verifies `dotnet` is callable and runtime is present
- [x] **LANG-02**: C# language server check verifies OmniSharp or csharp-ls is available
- [x] **LANG-03**: Node.js check verifies `node` is callable
- [x] **LANG-04**: TypeScript language server check verifies `typescript-language-server` is available
- [x] **LANG-05**: Python check verifies `python3` is callable
- [x] **LANG-06**: Python language server check verifies `pylsp` is available
- [x] **LANG-07**: Java runtime check verifies `java` is callable
- [x] **LANG-08**: Java language server check verifies Eclipse JDT LS is available

### CLI Interface

- [x] **CLI-01**: `synapse doctor` command displays Rich table with color-coded pass/warn/fail results
- [x] **CLI-02**: Command exits with non-zero code when any check fails
- [x] **CLI-03**: Each failing check shows actionable fix instruction inline

### MCP Interface

- [ ] **MCP-01**: `check_environment` MCP tool returns structured results for agent self-diagnosis

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### CLI Enhancements

- **CLIV2-01**: `--json` flag for machine-readable output
- **CLIV2-02**: `--group` filter to check specific language groups only
- **CLIV2-03**: Version checking with minimum version thresholds per dependency

### MCP Enhancements

- **MCPV2-01**: Group/language filtering parameter on `check_environment` tool

## Out of Scope

| Feature | Reason |
|---------|--------|
| Auto-installation of dependencies | User preference for transparency — report + instructions only |
| Internal state checks (indexing, graph data) | Keep focused on external environment, not Synapse internals |
| GUI / web setup wizard | CLI and MCP are the interfaces |
| Platform-specific package manager detection | Too many edge cases for v1; provide generic install instructions |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| CORE-01 | Phase 1 | Complete |
| CORE-02 | Phase 1 | Complete |
| CORE-03 | Phase 1 | Complete |
| CORE-04 | Phase 2 | Complete |
| DOCK-01 | Phase 2 | Complete |
| DOCK-02 | Phase 2 | Complete |
| CLI-01 | Phase 2 | Complete |
| CLI-02 | Phase 2 | Complete |
| CLI-03 | Phase 2 | Complete |
| LANG-01 | Phase 3 | Complete |
| LANG-02 | Phase 3 | Complete |
| LANG-03 | Phase 3 | Complete |
| LANG-04 | Phase 3 | Complete |
| LANG-05 | Phase 3 | Complete |
| LANG-06 | Phase 3 | Complete |
| LANG-07 | Phase 3 | Complete |
| LANG-08 | Phase 3 | Complete |
| MCP-01 | Phase 4 | Pending |

**Coverage:**
- v1 requirements: 18 total
- Mapped to phases: 18
- Unmapped: 0

---
*Requirements defined: 2026-03-23*
*Last updated: 2026-03-23 — CORE-04 reclassified from Phase 1 to Phase 2 (subprocess pattern belongs to check implementations, not data model scaffold)*
