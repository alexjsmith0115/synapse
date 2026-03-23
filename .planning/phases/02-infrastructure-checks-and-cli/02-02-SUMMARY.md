---
phase: 02-infrastructure-checks-and-cli
plan: 02
subsystem: cli
tags: [typer, rich, doctor, table, exit-code]

# Dependency graph
requires:
  - phase: 02-01
    provides: DockerDaemonCheck, MemgraphBoltCheck, DoctorService, DoctorReport, CheckResult

provides:
  - "@app.command('doctor') in src/synapse/cli/app.py with Rich table output"
  - "_render_report helper with group section headers, inline fix instructions, summary line"
  - "Module-level imports for DockerDaemonCheck, MemgraphBoltCheck, DoctorService in app.py"
  - "10 unit tests for CLI-01, CLI-02, CLI-03 covering exit codes, output content, fix text, group headers"

affects: [phase-03, cli-layer, doctor-command]

# Tech tracking
tech-stack:
  added: [rich.table.Table, rich.console.Console]
  patterns: [TDD red-green for CLI commands using CliRunner, module-level check imports for patchability]

key-files:
  created:
    - tests/unit/doctor/test_cli_doctor.py
  modified:
    - src/synapse/cli/app.py

key-decisions:
  - "Module-level imports for DockerDaemonCheck and MemgraphBoltCheck in app.py required so unittest.mock.patch targets synapse.cli.app.* correctly"
  - "Doctor command constructs DoctorService directly — does NOT call _get_service() to avoid ContainerManager dependency (D-04, anti-pattern 5)"
  - "_render_report extracted as module-level helper (SRP) rather than inlined in doctor()"
  - "Summary line included after table showing N passed / N warnings / N failed for exit-code legibility"

patterns-established:
  - "CLI doctor pattern: module-level check class imports, direct DoctorService construction, Rich Console/Table for output"
  - "CliRunner test pattern: patch at synapse.cli.app.CheckClass level, assert substrings in result.output (not exact match)"

requirements-completed: [CLI-01, CLI-02, CLI-03]

# Metrics
duration: 2min
completed: 2026-03-23
---

# Phase 02 Plan 02: CLI Doctor Command Summary

**`synapse doctor` CLI command with Rich table output, color-coded pass/warn/fail status, per-group section headers, inline fix instructions, summary line, and exit code 1 on any failure**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-23T21:20:50Z
- **Completed:** 2026-03-23T21:22:20Z
- **Tasks:** 2 (TDD: RED + GREEN)
- **Files modified:** 2

## Accomplishments

- Created 10 RED unit tests for CLI doctor command covering exit codes, check name/status in output, fix text, group header, and summary line
- Implemented `@app.command("doctor")` in `app.py` with Rich table rendering grouped by check group
- Full unit suite passes: 1106 tests, zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Write RED test scaffold for the doctor CLI command** - `51630dd` (test)
2. **Task 2: Implement doctor command in app.py with Rich table rendering (GREEN)** - `b0788e3` (feat)

## Files Created/Modified

- `tests/unit/doctor/test_cli_doctor.py` - 10 unit tests for CLI-01, CLI-02, CLI-03 using CliRunner + patch
- `src/synapse/cli/app.py` - Added module-level doctor imports, `_STATUS_STYLE` dict, `_render_report` helper, `doctor()` command

## Decisions Made

- Module-level imports required for `DockerDaemonCheck`, `MemgraphBoltCheck`, and `DoctorService` so test patches work at `synapse.cli.app.*` — placing imports inside `doctor()` would make patching fail
- `_render_report` extracted as module-level helper rather than inlined for SRP compliance per CLAUDE.md
- Summary line included (discretionary from plan): shows "N passed, N warnings, N failed" with color matching overall status

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 02 complete: all checks (DockerDaemonCheck, MemgraphBoltCheck) and the CLI doctor command are fully implemented and tested
- Phase 03 can add more check classes (e.g., language server checks) and register them by extending the list in `doctor()` with zero changes to the rendering/exit-code logic

---
*Phase: 02-infrastructure-checks-and-cli*
*Completed: 2026-03-23*
