---
phase: 07-mcp-tools-consolidation
plan: 01
subsystem: api
tags: [mcp, fastmcp, tools, consolidation, refactoring]

# Dependency graph
requires: []
provides:
  - "Consolidated MCP tool surface: 20 tools (down from 30)"
  - "summary(action) tool replacing set_summary/get_summary/list_summarized"
  - "find_usages with kind and include_test_breakdown params"
  - "find_callees with depth param subsuming get_call_depth"
  - "list_projects with path param subsuming get_index_status"
affects: [07-02-mcp-tools-consolidation]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Action-dispatch pattern: single tool with Literal action param replaces 3 tools (SummaryActionLiteral)"
    - "Optional-param merge: folding a narrow tool into a broader one via optional param (depth into find_callees, path into list_projects)"

key-files:
  created: []
  modified:
    - src/synapse/mcp/tools.py
    - tests/unit/test_tools.py
  deleted:
    - tests/unit/doctor/test_mcp_doctor.py

key-decisions:
  - "SummaryActionLiteral = Literal['get', 'set', 'list'] — mirrors existing SymbolKindLiteral pattern for constrained string params"
  - "find_usages kind/include_test_breakdown delegate directly to service.find_type_references/find_type_impact — no new service layer needed"
  - "find_callees depth path bypasses include_interface_dispatch and limit — both irrelevant to the call-tree path via get_call_depth"
  - "list_projects path param requires _auto_sync_check only when path is provided — list-all path needs no sync"

patterns-established:
  - "Action-dispatch pattern for merging related tools: single tool, Literal action param, branch on action"
  - "Optional-param merge for extending a tool: existing tool gains optional param that redirects to a related service method"

requirements-completed:
  - CONSOL-01
  - CONSOL-02
  - CONSOL-03
  - CONSOL-04
  - CONSOL-05
  - CONSOL-06
  - CONSOL-07

# Metrics
duration: 4min
completed: 2026-03-26
---

# Phase 07 Plan 01: MCP Tools Consolidation Summary

**MCP tool count reduced from 30 to 20 by merging 3 summary tools, folding get_call_depth/find_type_references/find_type_impact into existing tools, removing find_interface_contract and audit_architecture, and demoting check_environment/delete_project to CLI-only**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-26T02:11:25Z
- **Completed:** 2026-03-26T02:15:42Z
- **Tasks:** 2
- **Files modified:** 2 (+ 1 deleted)

## Accomplishments

- Merged 11 tool removals and 1 new `summary` tool to land at exactly 20 registered MCP tools
- All merged tools dispatch correctly to the existing service layer with no service-level changes required
- Deleted all dead doctor imports and `AuditRuleLiteral` type alias from tools.py
- Added 13 new unit tests covering merged tool dispatch paths and verified all 11 removed tools are absent
- Deleted `tests/unit/doctor/test_mcp_doctor.py` (tested `check_environment` which no longer exists as MCP tool)

## Task Commits

Each task was committed atomically:

1. **Task 1: Merge, remove, and demote tools in tools.py** - `dbdc260` (refactor)
2. **Task 2: Update unit tests for merged tools and delete test_mcp_doctor.py** - `d7b8358` (test)

## Files Created/Modified

- `src/synapse/mcp/tools.py` - Consolidated MCP tool registrations: 11 removed, 1 added, 3 modified, dead imports cleaned
- `tests/unit/test_tools.py` - Added 13 new tests for merged tool behavior + removed tool absence assertion
- `tests/unit/doctor/test_mcp_doctor.py` - Deleted (check_environment MCP tool removed per D-07)

## Decisions Made

- `SummaryActionLiteral = Literal["get", "set", "list"]` uses the existing SymbolKindLiteral pattern for constrained string params
- `find_usages` kind/include_test_breakdown delegate directly to service.find_type_references/find_type_impact — no new service-layer methods needed
- `find_callees` depth path bypasses include_interface_dispatch and limit entirely — both irrelevant to the call-tree traversal via get_call_depth
- `list_projects` only calls `_auto_sync_check()` when path is provided — list-all doesn't need per-project sync

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Tool surface is consolidated; ready for Plan 02 (instructions.py rewrite per D-09 and D-10)
- Integration tests referencing removed tool names (`EXPECTED_TOOLS` set in test_mcp_tools.py) will fail — Plan 02 addresses this

## Self-Check: PASSED

- `src/synapse/mcp/tools.py` exists and contains 20 registered tools
- `tests/unit/test_tools.py` exists and contains all required test functions
- `tests/unit/doctor/test_mcp_doctor.py` does not exist
- Commits dbdc260 and d7b8358 verified via git log

---
*Phase: 07-mcp-tools-consolidation*
*Completed: 2026-03-26*
