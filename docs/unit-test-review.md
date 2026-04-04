# Unit Test Suite Review

**Date:** 2026-04-03
**Scope:** All files under `tests/unit/` (~90 files, ~600+ test cases)
**Goal:** Identify redundant, ineffective, overlapping, misleading, or brittle tests

---

## Executive Summary

Overall quality score: **~85/100**. Most tests are effective and well-structured. Issues are concentrated in specific patterns: mock-only tests that don't verify real behavior, structural duplication across language plugins, and brittle Cypher string assertions.

| Category | Estimated Count | Severity |
|---|---|---|
| Redundant tests | ~45 | Medium |
| Ineffective / tautological tests | ~30 | High |
| Overlapping tests across files | ~25 | Medium |
| Misleading names | ~15 | Low |
| Brittle / fragile tests | ~35 | Medium-High |

---

## 1. Redundant Tests

### 1.1 Structural Duplication Across Language Plugins

The biggest source of redundancy. Tests for base-type extractors, import extractors, call extractors, plugin factory methods, and LSP adapters repeat near-identical logic for each supported language. These could be consolidated with `pytest.mark.parametrize` or a shared base test class.

**Base type extractors** (4 files, identical pattern):
- `tests/unit/indexer/test_csharp_base_type_extractor.py`
- `tests/unit/indexer/test_python_base_type_extractor.py`
- `tests/unit/indexer/test_typescript_base_type_extractor.py`
- `tests/unit/indexer/test_java_base_type_extractor.py`

**Import extractors** (4 files, `test_empty_source()` and `test_deduplicates()` repeated):
- `tests/unit/indexer/test_python_import_extractor.py`
- `tests/unit/indexer/test_java_import_extractor.py`
- `tests/unit/indexer/test_csharp_import_extractor.py`
- `tests/unit/indexer/test_typescript_import_extractor.py`

**Plugin factory methods** (3 files, identical isinstance-check pattern):
- `tests/unit/plugin/test_csharp_plugin.py` (lines 28-50)
- `tests/unit/plugin/test_typescript_plugin.py` (lines 38-70)
- `tests/unit/plugin/test_python_plugin.py` (lines 26-58)

**HTTP extractor wiring** (`tests/unit/plugin/test_http_extractor_wiring.py`, lines 9-30):
Four separate tests that each call `create_http_extractor()` and assert `is not None`. One parametrized test would suffice.

**LSP adapter stub methods** (3 files, identical):
- `test_find_method_calls_returns_empty` and `test_find_overridden_method_returns_none` are copy-pasted across `test_python_adapter.py`, `test_csharp_adapter.py`, and `test_typescript_adapter.py`.

**TypeScript adapter exclusion/extension tests** (`tests/unit/lsp/test_typescript_adapter.py`):
- 8 nearly-identical extension tests (lines 178-204) and 10+ exclusion tests (lines 255-341), each following the same create-file-assert pattern.

**Protocol attribute tests** (`tests/unit/plugin/test_plugin_protocol.py`, lines 39-72):
Eight `test_protocol_has_X` tests that each call `hasattr(LanguagePlugin, ...)`. One parametrized test.

### 1.2 Same-File Duplicates

**`tests/unit/indexer/test_sync.py`:**
- `test_no_changes()` (line 74) and `test_fresh_file_unchanged()` (line 29) verify the same behavior.

**`tests/unit/indexer/test_indexer.py`:**
- `test_is_minified()` (line 43), `test_is_minified_source()` (line 354), and `test_is_minified_source_returns_true_for_long_first_line()` (line 368) all test the same "first line > 500 chars" check.

**`tests/unit/indexer/test_http_phase.py`:**
- `test_conflict_warning_emitted()` (line 77) is a strict subset of `test_conflict_warning_emitted_once_per_pair()` (line 94).

**`tests/unit/indexer/test_call_indexer.py`:**
- `test_writes_call_site_line_and_col()` (line 84) and `test_writes_calls_edge_when_lsp_resolves_callee()` (line 108) overlap on line/col assertions.

**`tests/unit/graph/test_staleness.py`:**
- `test_check_staleness_stale_file()` and `test_check_staleness_fresh_file()` are a parametrize candidate.

**`tests/unit/graph/test_edges_delete_outgoing.py`:**
- `test_passes_file_path_to_both_queries()` (line 43) re-asserts what the first two tests already verify.

### 1.3 Doctor Tests — Duplicate Pass/Fix Scenarios

Each language check file has a "pass" test and a separate "pass_fix_is_none" test that verify the same code path:
- `test_python.py`: `test_python_pass_when_version_exits_zero` + `test_python_pass_fix_is_none`
- `test_java.py`: `test_java_pass_when_version_exits_zero` + `test_java_pass_fix_is_none`; `test_jdtls_pass_when_launcher_jar_exists` + `test_jdtls_pass_fix_is_none`
- `test_typescript.py`: `test_node_pass_when_version_exits_zero` + `test_node_pass_fix_is_none`
- `test_docker_daemon.py`: `test_docker_daemon_pass_when_ping_succeeds` + `test_docker_daemon_pass_has_no_fix`
- `test_memgraph_bolt.py`: `test_memgraph_pass_when_bolt_handshake_receives_4_bytes` + `test_memgraph_pass_has_no_fix`

Additionally, `test_fix_strings.py` re-tests the same fix strings that individual check files already cover.

---

## 2. Ineffective / Tautological Tests

### 2.1 Mock-Only Tests (Testing Mocks, Not Logic)

**`tests/unit/graph/test_connection.py`** — Most tests here verify mock setup:
- `test_query_returns_records`: asserts `result == mock_records` (tautological)
- `test_execute_returns_none`: verifies mock returns None
- `test_execute_implicit_uses_session_run`: verifies mock method was called
- `test_close_calls_driver_close`: verifies mock was called
- `test_query_with_timeout_returns_records`: would pass even if timeout logic was broken

**`tests/unit/doctor/test_cli_doctor.py`** — Entire file patches all 10 check classes with mocks. Tests verify mock configuration, not actual CLI behavior. Would pass even if the CLI stopped calling the checks.

**`tests/unit/test_mcp_sync.py`** — Registers tools against a mock MCP object and asserts tool names exist in a dict the test itself populates.

**`tests/unit/test_mcp_server.py`** (`test_main_uses_connection_manager`): Patches all dependencies, asserts mocks were called. No actual flow tested.

**`tests/unit/indexer/test_overrides_indexer.py`** — All 6 tests only verify mock call counts, not actual Cypher correctness.

**`tests/unit/indexer/test_method_implements_indexer.py`** — All 13 tests use mocks and only check `query.call_count` or `execute.call_count`. A broken algorithm would still pass.

**`tests/unit/indexer/test_import_fallback.py`** — Verifies calls were added to a pending list, not that resolution produced correct results.

### 2.2 Tautological Assertions

**`tests/unit/doctor/test_base.py`:**
- `test_checkresult_has_required_fields`: tests dataclass field assignment (language feature, not app logic)
- `test_checkstatus_valid_values`: asserts a type annotation matches itself
- `test_doctor_check_is_runtime_checkable`: tests Python's protocol mechanism

**`tests/unit/doctor/test_service.py`:**
- `test_service_returns_doctor_report`: `isinstance()` check that's always True by construction
- `test_empty_service_returns_empty_report`: passing empty list guarantees empty result

**`tests/unit/indexer/test_parsed_file.py`** — All tests verify dataclass fields equal what was assigned. Would pass even if parsing was broken.

**`tests/unit/lsp/test_python_adapter.py`:**
- `test_find_method_calls_returns_empty`: tests a stub that returns `[]` by design
- `test_find_overridden_method_returns_none`: tests a stub that returns `None` by design

**`tests/unit/lsp/test_csharp_adapter.py`:**
- `test_csharp_adapter_implements_protocol`: uses `isinstance(...) or hasattr(...)` which always passes

---

## 3. Overlapping Tests Across Files

### 3.1 HTTP/Orphan Endpoint Cleanup
- `tests/unit/graph/test_http_graph_ops.py::test_delete_orphan_endpoints` (line 77)
- `tests/unit/graph/test_orphan_endpoints.py::test_cleanup_removes_repo_contains_edge_and_orphaned_endpoint` (line 9)
Both test `delete_orphan_endpoints()` with nearly identical assertions. The orphan-specific file is more thorough; the http_graph_ops version is redundant.

### 3.2 DISPATCHES_TO Traversal
Three tests in `tests/unit/graph/test_traversal.py` all assert `"DISPATCHES_TO" in cypher`:
- `test_trace_call_chain_traverses_dispatches_to` (line 79)
- `test_find_entry_points_traverses_dispatches_to` (line 90)
- `test_get_call_depth_traverses_dispatches_to` (line 149)

### 3.3 PROD-04 Regression Tests
Identical `_find_enclosing_symbol()` tests duplicated across:
- `tests/unit/indexer/http/test_python_http_extractor.py` (lines 426-451)
- `tests/unit/indexer/http/test_typescript_http_extractor.py` (lines 324-349)

### 3.4 Doctor Fix Strings
`tests/unit/doctor/test_fix_strings.py` re-tests the same fail+fix scenarios that each individual check file already covers (Docker, Python, Java, C#, TypeScript, Memgraph).

### 3.5 Banner Color Tests
`tests/unit/test_banner.py`: `test_banner_has_two_tone_colors` (line 57) re-asserts the same RGB values already checked by `test_banner_contains_dark_green_color` and `test_banner_contains_light_green_color`.

---

## 4. Misleading Test Names

| File | Test | Issue |
|---|---|---|
| `indexer/test_indexer.py` | `test_index_callback_edges_creates_calls_from_parent_to_callback` | Doesn't test real callback extraction; tests name-string matching |
| `indexer/test_http_phase.py` | `test_phase_skips_when_no_results` | Doesn't "skip" — runs with empty result list |
| `graph/test_analysis.py` | `test_analyze_change_impact_aggregates` | Only checks result keys/counts, not aggregation logic |
| `graph/test_traversal.py` | `test_find_entry_points_attributed_controller` | Doesn't verify attribute checking occurs |
| `graph/test_traversal.py` | `test_find_entry_points_exclude_tests_composes_with_exclude_pattern` | Only checks two param keys exist, not composition behavior |
| `graph/test_edges.py` | `test_upsert_implements_accepts_class_or_interface_label` | Only checks string presence in Cypher |
| `lsp/test_typescript_adapter.py` | `test_top_level_const_with_method_children_promoted_to_class` | "promoted" suggests transformation; actually processes structure as-is |
| `watcher/test_watcher.py` | `test_watcher_stop_joins_observer_thread` | Only asserts `is_running() == False`, not thread-join behavior |
| `doctor/test_service.py` | `test_has_failures_true_on_fail` | Implies multiple failure scenarios; tests single `_FailCheck` |
| `doctor/test_fix_strings.py` | `test_csharp_ls_fix_unchanged` | Doesn't test immutability; tests substring presence |

---

## 5. Brittle / Fragile Tests

### 5.1 Cypher String Matching

Many graph layer tests assert specific substrings in Cypher queries rather than testing behavior:

**`tests/unit/graph/test_analysis.py`:**
- `test_analyze_change_impact_direct_callers_excludes_tests`: asserts `"NOT"` in query
- `test_analyze_change_impact_direct_callers_uses_regex_not_substring`: checks for `"CONTAINS"` absence
- `test_find_interface_contract_via_overrides_chain`: asserts `"OVERRIDES"` in query

**`tests/unit/graph/test_traversal.py`:**
- `test_find_entry_points_test_pattern_filters_callers_in_not_exists` (lines 198-222): Manually parses Cypher by counting braces to extract a NOT EXISTS block. Extremely brittle.
- `test_trace_call_chain_depth_clamped`/`test_trace_call_chain_depth_in_cypher`: assert exact `"*1..10"` / `"*1..4"` strings

**`tests/unit/graph/test_edges.py`:** All tests just assert keyword presence in Cypher (`"INHERITS"`, `"CONTAINS"`, etc.)

**`tests/unit/graph/test_search_language_filter.py`:** All tests assert `"n.language = $language"` in Cypher.

**`tests/unit/graph/test_schema.py`:** Asserts exact index creation call count (10) and specific Cypher syntax strings.

**`tests/unit/indexer/test_sync.py`:** Uses `"language" in file_query_call.args[0]` for query assertions.

### 5.2 Exact Docker API Parameters

**`tests/unit/container/test_manager.py`:**
- `test_shared_mode_creates_shared_container` (line 32): asserts exact port mapping dict and container name
- `test_shared_mode_handles_name_conflict` (line 182): depends on exact mock invocation order

### 5.3 Fix-String URL Assertions

Doctor check tests assert specific URLs in fix text (`"dotnet.microsoft.com"`, `"adoptium.net"`, `"python.org"`, `"nodejs.org"`). These break if URLs change even though behavior is correct.

### 5.4 Timing-Dependent Watcher Tests

**`tests/unit/watcher/test_watcher.py`:**
- Uses `wait_for_call()` with timeout — flaky on slow CI
- Uses `time.sleep(0.3)` then asserts mock wasn't called — insufficient on slow systems

### 5.5 Banner ANSI Escape Assertions

**`tests/unit/test_banner.py`:** Asserts exact ANSI RGB codes (`"45;106;79"`) and block characters (`"\u2588"`). Breaks if the Rich library changes encoding.

---

## 6. Well-Structured Tests (No Issues)

These files are well-organized, non-redundant, and effectively test behavior:

- `tests/unit/indexer/test_python_type_ref_extractor.py` — Organized by requirement (TREF-PY-01 through TREF-PY-06)
- `tests/unit/indexer/test_typescript_type_ref_extractor.py` — Same clear organization
- `tests/unit/indexer/test_python_call_extractor.py` — Comprehensive edge cases, well-separated concerns
- `tests/unit/indexer/test_typescript_call_extractor.py` — Good call-type organization
- `tests/unit/indexer/http/test_route_utils.py` — Focused, each test covers one normalization rule
- `tests/unit/indexer/http/test_matcher.py` — Clear naming, good scenario variety
- `tests/unit/indexer/http/test_constants_resolver.py` — Well-organized by language
- `tests/unit/indexer/test_python_attribute_extractor.py` — Comprehensive decorator testing
- `tests/unit/indexer/test_typescript_attribute_extractor.py` — Clear META requirements
- `tests/unit/indexer/test_csharp_attribute_extractor.py` — Good regression coverage
- `tests/unit/indexer/test_reindex_upsert.py` — Focused D-12 upsert behavior
- `tests/unit/indexer/test_git_sync.py` — Good scenario organization
- `tests/unit/indexer/test_python_assignment_extractor.py` — Clear concern separation
- `tests/unit/test_synignore.py` — Good pattern coverage
- `tests/unit/test_config.py` — Clean and focused
- `tests/unit/service/test_context_impact.py` — Tests real query construction logic
- `tests/unit/hooks/test_scripts.py` — Clear hook script generation tests

---

## Recommendations (Priority Order)

### High — Consolidate language-plugin duplication
Parametrize base-type, import, factory, and stub tests across languages. Would eliminate ~30 redundant tests.

### High — Replace mock-tautology tests with real assertions
`test_connection.py`, `test_cli_doctor.py`, `test_overrides_indexer.py`, `test_method_implements_indexer.py` — either test actual behavior or remove.

### Medium — Merge same-file duplicates
`test_sync.py`, `test_indexer.py` (minified), `test_http_phase.py` (conflict warnings), doctor pass/fix tests.

### Medium — Replace brittle Cypher string matching
For graph tests that assert substring presence in queries, consider testing query results against a test database or extracting query parameters for assertion instead.

### Medium — Consolidate `test_fix_strings.py` with individual check files
The parametrized fix-string tests duplicate what each check's own file already verifies.

### Low — Fix misleading test names
Rename tests where the name doesn't match the actual assertion (see table in section 4).

### Low — Address watcher timing sensitivity
Consider using event-based synchronization instead of `time.sleep()` in watcher tests.
