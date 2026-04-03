"""Unit tests for dead code / untested exclusion WHERE clause builder.

Tests cover:
- _build_base_exclusion_where generates correct Cypher fragments
- _EXCLUDED_METHOD_NAMES contains expected framework entry points
- _FRAMEWORK_ATTRIBUTES contains expected annotation names
- Regression tests for the Java main() and gRPC/Override bugs (BUG-02..04)
"""
from __future__ import annotations

import pytest

from synapps.graph.analysis import (
    _EXCLUDED_METHOD_NAMES,
    _FRAMEWORK_ATTRIBUTES,
    _build_base_exclusion_where,
)


class TestExcludedMethodNames:
    def test_contains_main_lowercase(self) -> None:
        assert "main" in _EXCLUDED_METHOD_NAMES

    def test_contains_main_pascalcase(self) -> None:
        assert "Main" in _EXCLUDED_METHOD_NAMES

    def test_contains_init(self) -> None:
        assert "__init__" in _EXCLUDED_METHOD_NAMES

    def test_contains_constructor(self) -> None:
        assert "constructor" in _EXCLUDED_METHOD_NAMES


class TestFrameworkAttributes:
    def test_contains_override(self) -> None:
        # BUG-04: Java @Override annotation is stored lowercase by JavaAttributeExtractor.
        # Adding "override" to _FRAMEWORK_ATTRIBUTES catches gRPC service method overrides
        # and other Java methods overriding external framework base classes whose base
        # class is not indexed (so no OVERRIDES edge exists).
        assert "override" in _FRAMEWORK_ATTRIBUTES

    def test_contains_bean(self) -> None:
        assert "bean" in _FRAMEWORK_ATTRIBUTES

    def test_contains_requestmapping(self) -> None:
        assert "requestmapping" in _FRAMEWORK_ATTRIBUTES


class TestBuildExclusionWhere:
    def setup_method(self) -> None:
        self.clause = _build_base_exclusion_where()

    def test_returns_string(self) -> None:
        assert isinstance(self.clause, str)
        assert len(self.clause) > 0

    # --- BUG-02 regression: Java main() name exclusion ---

    def test_build_exclusion_where_excludes_main(self) -> None:
        # The WHERE clause must include 'main' in the name exclusion list.
        # m.name for Java main() methods is stored as 'main' (simple name from JDT LS),
        # not 'main(String[])' -- so the name-based exclusion is the correct path.
        assert "'main'" in self.clause
        assert "m.name IN [" in self.clause

    def test_main_name_exclusion_covers_both_cases(self) -> None:
        # Both 'main' (Java) and 'Main' (C# style) must be excluded.
        assert "'main'" in self.clause
        assert "'Main'" in self.clause

    def test_main_exclusion_via_name_list_is_correct_approach(self) -> None:
        # Regression: JDT LS stores the method name as 'main' (not 'main(String[])').
        # The overload suffix only appears in full_name (e.g. 'com.App.main(String[])').
        # The exclusion correctly uses m.name (not m.full_name), so 'main' IS matched.
        # This test confirms the name list in the clause contains 'main'.
        name_list_start = self.clause.index("m.name IN [")
        name_list_end = self.clause.index("]", name_list_start)
        name_list_fragment = self.clause[name_list_start:name_list_end + 1]
        assert "'main'" in name_list_fragment

    def test_build_exclusion_where_excludes_main_with_params(self) -> None:
        # DEAD-01/02: JDT LS may store the method name as 'main(String[])' instead of 'main'.
        # The WHERE clause must also filter names that start with 'main(' to cover this variant.
        assert "m.name STARTS WITH 'main('" in self.clause

    def test_main_exclusion_covers_both_name_variants(self) -> None:
        # Belt-and-suspenders: both the IN-list check (for 'main') and the STARTS WITH check
        # (for 'main(String[])') must be present so neither variant slips through.
        assert "'main'" in self.clause
        assert "m.name STARTS WITH 'main('" in self.clause

    # --- BUG-03: Spring configure() in Adapter/Configurer classes ---

    def test_build_exclusion_where_excludes_configure_in_configuration(self) -> None:
        # Existing behavior must be preserved: Configure (PascalCase, C#) in *Configuration.
        assert "ENDS WITH 'Configuration'" in self.clause

    def test_build_exclusion_where_excludes_configure_in_configurer(self) -> None:
        # BUG-03: Spring WebSecurityConfigurerAdapter's configure() override was not excluded
        # because the suffix check only covered 'Configuration'. Must now cover 'Configurer'.
        assert "ENDS WITH 'Configurer'" in self.clause

    def test_build_exclusion_where_excludes_configure_in_adapter(self) -> None:
        # BUG-03: Spring Security WebSecurityConfigurerAdapter and other Adapter classes
        # use configure() as a framework entry point. Must be excluded by class suffix.
        assert "ENDS WITH 'Adapter'" in self.clause

    def test_configure_clause_includes_java_lowercase(self) -> None:
        # BUG-03: Java methods are stored lowercase by JDT LS, so 'configure' (lowercase)
        # is the actual stored name. The clause must include both forms.
        assert "'configure'" in self.clause

    def test_configure_clause_includes_csharp_pascalcase(self) -> None:
        # C# Configure (PascalCase) must still be covered for backward compatibility.
        assert "'Configure'" in self.clause

    def test_configure_uses_in_list_for_both_cases(self) -> None:
        # The implementation should use m.name IN [...] rather than separate equality checks.
        # The list now includes 'ConfigureServices' for .NET Startup conventions.
        assert "m.name IN ['configure', 'Configure', 'ConfigureServices']" in self.clause

    # --- BUG-04: gRPC @Override exclusion via attribute check ---

    def test_framework_attributes_contains_override(self) -> None:
        # BUG-04: Java @Override is stored as "override" by JavaAttributeExtractor.lower().
        # The attribute check in the WHERE clause must include '"override"'.
        assert "\"override\"" in self.clause or "'override'" in self.clause

    def test_build_exclusion_where_excludes_overridden_java_method(self) -> None:
        # BUG-04: A method with attributes containing "override" should be excluded.
        # The clause uses CONTAINS '"override"' against the JSON-serialized attributes list.
        assert "override" in self.clause

    # --- Structural correctness ---

    def test_clause_starts_with_not(self) -> None:
        assert self.clause.startswith("NOT ")

    def test_clause_excludes_test_files(self) -> None:
        assert "m.file_path =~ $test_pattern" in self.clause

    def test_clause_excludes_interface_members(self) -> None:
        assert "m)<-[:CONTAINS]-(:Interface)" in self.clause

    def test_clause_excludes_overrides_edge(self) -> None:
        assert "(m)-[:OVERRIDES]->()" in self.clause
