---
phase: 05-expand-http-endpoint-mapping-to-all-languages
plan: 05
subsystem: indexer
tags: [tree-sitter, http-extraction, cross-language, constants-resolver, python, typescript, java, csharp]

requires:
  - phase: 05-01
    provides: PythonHttpExtractor and PythonPlugin.create_http_extractor()
  - phase: 05-02
    provides: TypeScriptHttpExtractor returning both endpoint_defs and client_calls
  - phase: 05-03
    provides: JavaHttpExtractor and JavaPlugin.create_http_extractor()
  - phase: 05-04
    provides: CSharpHttpExtractor returning both endpoint_defs and client_calls

provides:
  - Cross-language integration test proving TypeScript client calls match Python FastAPI server endpoints
  - collect_cross_file_constants() utility for scanning top-level URL string constants across all four languages
  - Positive wiring assertions for all 4 language plugins (confirmed already complete from Wave 1)

affects:
  - Future indexer phases that want to resolve imported URL constants in extractor pipelines

tech-stack:
  added: []
  patterns:
    - "_COLLECTORS registry dispatches to per-language constant-collection functions — mirrors _HTTPCLIENT_VERB_MAP pattern from Phase 05"
    - "URL-like filter (_is_url_like) applied at collection time to reduce noise in the constants map"
    - "Component-level cross-language tests (no external services) placed in tests/integration/ because they span multiple subsystems"

key-files:
  created:
    - tests/integration/test_http_cross_language.py
    - src/synapse/indexer/http/constants_resolver.py
    - tests/unit/indexer/http/test_constants_resolver.py
  modified:
    - tests/unit/plugin/test_http_extractor_wiring.py (already updated by Wave 1 — confirmed passing)

key-decisions:
  - "Cross-language test placed in tests/integration/ (not tests/unit/) because it exercises multiple subsystems together, despite requiring no Memgraph — avoids @pytest.mark.integration marker since no external services are needed"
  - "collect_cross_file_constants filters to URL-like strings at collection time (must contain '/' or start with 'http') — prevents noise from non-URL constants polluting the resolution map"
  - "TDD RED phase committed separately (test(05-05):) before GREEN implementation commit — follows project TDD workflow"

patterns-established:
  - "Component-level cross-language tests: parse source from two languages, extract with their respective extractors, feed into match_endpoints(), assert on MatchedEndpoint results"

requirements-completed: [HTTP-INFRA-01]

duration: 11min
completed: 2026-03-25
---

# Phase 05 Plan 05: Finalize HTTP Extraction Matrix Summary

**Cross-language TypeScript-to-Python endpoint matching test plus a four-language URL constant collector (`collect_cross_file_constants`) that scans top-level string assignments for URL resolution**

## Performance

- **Duration:** ~11 min
- **Started:** 2026-03-25T01:25:00Z
- **Completed:** 2026-03-25T01:36:27Z
- **Tasks:** 2
- **Files modified:** 3 created (wiring tests already done by Wave 1)

## Accomplishments

- Confirmed all 4 plugin wiring tests already pass with positive assertions (Wave 1 done)
- Created 3-test cross-language integration test: TypeScript client calls matching Python FastAPI server endpoints, parameterized route matching, and non-matching route verification
- Created `collect_cross_file_constants()` utility with per-language collectors for Python, TypeScript, Java, and C# top-level string constants
- 12 unit tests for the constants resolver covering URL filtering, scope filtering, multi-file collection, and unknown language handling

## Task Commits

1. **Task 1: Plugin wiring tests + cross-language integration test** - `153b719` (feat)
2. **Task 2 RED: Failing tests for constants resolver** - `56e6427` (test)
3. **Task 2 GREEN: constants_resolver.py implementation** - `1c49b2f` (feat)

**Plan metadata:** (to be committed)

_Note: Task 1 Part A (wiring tests) was already complete from Wave 1 — no changes needed. Task 2 used TDD flow with separate RED and GREEN commits._

## Files Created/Modified

- `tests/integration/test_http_cross_language.py` - 3 cross-language matching tests: GET+POST match, parameterized route match, no-match case
- `src/synapse/indexer/http/constants_resolver.py` - `collect_cross_file_constants()` with Python/TypeScript/Java/C# collectors; `_COLLECTORS` registry
- `tests/unit/indexer/http/test_constants_resolver.py` - 12 unit tests covering Python (7) and TypeScript (3) constant collection, empty file, unknown language

## Decisions Made

- Cross-language test placed in `tests/integration/` (not `tests/unit/`) because it spans multiple subsystems, but NOT marked with `@pytest.mark.integration` since it requires no external services
- `collect_cross_file_constants` filters at collection time to values containing "/" or starting with "http" — reduces noise in URL resolution maps used by extractors
- TDD RED commit made separately before GREEN implementation commit to document the workflow

## Deviations from Plan

None - plan executed exactly as written. The wiring tests (Task 1 Part A) were already completed by Wave 1 agents and did not require modification.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All four language HTTP extractors are wired and verified
- Cross-language matching is proven end-to-end (TypeScript client → Python server)
- `collect_cross_file_constants` is available for extractors to use for one-hop imported constant resolution (D-09)
- Phase 05 HTTP endpoint extraction matrix is complete

---
*Phase: 05-expand-http-endpoint-mapping-to-all-languages*
*Completed: 2026-03-25*
