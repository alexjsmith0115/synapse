---
phase: 03-language-server-checks
plan: 05
subsystem: cli
tags: [typer, doctor, checks, language-servers, testing, mocking]

requires:
  - phase: 03-01
    provides: DotNetCheck and CSharpLSCheck classes
  - phase: 03-02
    provides: NodeCheck and TypeScriptLSCheck classes
  - phase: 03-03
    provides: PythonCheck and PylspCheck classes
  - phase: 03-04
    provides: JavaCheck and JdtlsCheck classes
  - phase: 02-infrastructure-checks-and-cli
    provides: DockerDaemonCheck, MemgraphBoltCheck, DoctorService, app.py doctor() command

provides:
  - doctor() command wired with all 10 checks (Docker, Memgraph, .NET SDK, csharp-ls, Node.js, typescript-language-server, Python 3, pylsp, Java, Eclipse JDT LS)
  - test_cli_doctor.py with comprehensive 10-check patching via _AllChecksPassingContext helper
  - test_doctor_runs_all_ten_checks asserting all 8 new language server names appear in output

affects: [04-mcp-doctor-tool]

tech-stack:
  added: []
  patterns:
    - "_ALL_CHECKS table drives both patch targets and result data, eliminating repetition across test cases"
    - "_AllChecksPassingContext class wraps ExitStack to provide a single-line context manager for all 10 check patches"
    - "Failure-specific tests use ExitStack directly with targeted mock overrides rather than composing context managers"

key-files:
  created: []
  modified:
    - src/synapse/cli/app.py
    - tests/unit/doctor/test_cli_doctor.py

key-decisions:
  - "All 8 new check class imports placed at module level in app.py (not inside doctor()) — required for patch() to target synapse.cli.app.ClassName correctly in tests"
  - "_AllChecksPassingContext uses __enter__/__exit__ (not @contextmanager) to allow clean ExitStack integration without yielding — simpler for tests that do not need individual mock handles"
  - "Failure-specific tests use raw ExitStack + override pattern instead of composing _AllChecksPassingContext — gives direct mock handle access without adding complexity to the helper"

patterns-established:
  - "Module-level doctor check imports: all check classes imported at file scope so test patching targets synapse.cli.app.* namespace"
  - "Centralized _ALL_CHECKS table: single source of truth for class names, check names, and groups — drives both patch setup and result construction"

requirements-completed: [LANG-01, LANG-02, LANG-03, LANG-04, LANG-05, LANG-06, LANG-07, LANG-08]

duration: 8min
completed: 2026-03-23
---

# Phase 03 Plan 05: Wire All Language Server Checks into CLI Summary

**`synapse doctor` expanded from 2 to 10 checks: all 8 language server checks wired into app.py and fully covered by patched unit tests**

## Performance

- **Duration:** 8 min
- **Started:** 2026-03-23T22:26:00Z
- **Completed:** 2026-03-23T22:34:01Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Added 8 module-level imports to app.py and expanded doctor() checks list from 2 to 10
- Refactored all existing CLI tests to patch all 10 checks (preventing real checks from running non-deterministically)
- Added `test_doctor_runs_all_ten_checks` asserting all 8 new check names appear in output
- Full unit suite (1154 tests) passes with no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Wire all 8 new checks into app.py doctor() command** - `18cb9c8` (feat)
2. **Task 2: Update test_cli_doctor.py to cover all 10 checks** - `b7d51b7` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `src/synapse/cli/app.py` - Added 8 module-level imports; expanded checks list to 10 entries; updated docstring
- `tests/unit/doctor/test_cli_doctor.py` - Added _ALL_CHECKS table, _AllChecksPassingContext helper; refactored all tests to patch all 10 checks; added test_doctor_runs_all_ten_checks

## Decisions Made

- All 8 new check class imports placed at module level (not inside doctor()) — required for `patch()` to resolve to the `synapse.cli.app.*` namespace used in tests
- `_AllChecksPassingContext` uses `__enter__`/`__exit__` directly (not `@contextmanager`) for clean ExitStack integration
- Failure-specific tests use raw ExitStack with targeted override rather than composing `_AllChecksPassingContext` — avoids needing to yield individual mock handles from the helper

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 03 is fully complete — all language server checks implemented (Plans 01-04) and wired into the CLI (Plan 05)
- Phase 04 (MCP doctor tool) can proceed: all check classes are importable from their canonical module paths and DoctorService is validated end-to-end
- No blockers or concerns

---
*Phase: 03-language-server-checks*
*Completed: 2026-03-23*
