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
    _FRAMEWORK_CLASS_ATTRIBUTES,
    _build_base_exclusion_where,
    _ENTITY_DTO_ANNOTATIONS,
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

    def test_contains_configure_web_host(self) -> None:
        assert "ConfigureWebHost" in _EXCLUDED_METHOD_NAMES

    def test_contains_create_host_builder(self) -> None:
        assert "CreateHostBuilder" in _EXCLUDED_METHOD_NAMES

    def test_contains_create_web_host_builder(self) -> None:
        assert "CreateWebHostBuilder" in _EXCLUDED_METHOD_NAMES


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

    def test_contains_authorize(self) -> None:
        assert "Authorize" in _FRAMEWORK_ATTRIBUTES

    def test_contains_allow_anonymous(self) -> None:
        assert "AllowAnonymous" in _FRAMEWORK_ATTRIBUTES

    def test_contains_global_setup(self) -> None:
        assert "GlobalSetup" in _FRAMEWORK_ATTRIBUTES

    def test_contains_global_cleanup(self) -> None:
        assert "GlobalCleanup" in _FRAMEWORK_ATTRIBUTES


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

    # --- Constructor name matching (parameterized) ---

    def test_constructor_excluded_by_starts_with_classname(self) -> None:
        # JDT LS stores Java constructors as "ClassName()" or "ClassName(Type, Type)"
        # Must match via STARTS WITH (p.name + '(') not just exact p.name = m.name.
        # The concatenation MUST be parenthesized: Memgraph evaluates STARTS WITH with
        # higher precedence than +, so the unparenthesized form `STARTS WITH p.name + '('`
        # is parsed as `(STARTS WITH p.name) + '('` → bool + string → runtime error.
        assert "m.name STARTS WITH (p.name + '(')" in self.clause

    def test_constructor_starts_with_concatenation_is_parenthesized(self) -> None:
        # Regression for: "Invalid types: bool and string for '+'"
        # The unparenthesized form `m.name STARTS WITH p.name + '('` causes Memgraph to
        # evaluate this as `(m.name STARTS WITH p.name) + '('` (bool + string → error).
        # This test ensures the parenthesized form is used and the broken form is absent.
        assert "m.name STARTS WITH p.name + '('" not in self.clause

    def test_constructor_excluded_for_generic_class(self) -> None:
        # C# generic classes: class name is "Repository<T>" but constructor name is "Repository".
        # Neither p.name = m.name nor m.name STARTS WITH (p.name + '(') matches.
        # Must also check p.name STARTS WITH (m.name + '<') to catch generic type suffix.
        assert "p.name STARTS WITH (m.name + '<')" in self.clause

    # --- .NET Startup/Program convention exclusions ---

    def test_configure_services_in_name_check(self) -> None:
        assert "'ConfigureServices'" in self.clause

    def test_startup_class_excluded(self) -> None:
        assert "cfg.name = 'Startup'" in self.clause

    def test_program_class_excluded(self) -> None:
        assert "cfg.name = 'Program'" in self.clause

    def test_configure_excluded_in_options_class(self) -> None:
        # ASP.NET IConfigureOptions<T> pattern: Configure() in classes ending with "Options"
        assert "ENDS WITH 'Options'" in self.clause

    # --- Heuristic 1: External bases exclusion ---

    def test_clause_excludes_methods_on_classes_with_external_bases(self) -> None:
        assert "external_bases" in self.clause

    def test_external_bases_check_requires_non_static(self) -> None:
        assert "m.is_static" in self.clause

    # --- Heuristic 2: C# virtual modifier ---

    def test_clause_excludes_virtual_methods(self) -> None:
        assert 'CONTAINS \'"virtual"\'' in self.clause

    # --- Heuristic 3: Abstract methods ---

    def test_clause_excludes_abstract_methods(self) -> None:
        assert "m.is_abstract" in self.clause

    # --- Heuristic 4: Class-level framework attributes ---

    def test_clause_checks_class_level_attributes(self) -> None:
        # Must check attributes on the PARENT class, not just the method
        assert '"component"' in self.clause

    def test_clause_checks_class_level_ApiController(self) -> None:
        assert '"ApiController"' in self.clause


class TestExpandedExcludedMethodNames:
    """New method names added for C# and Java false positive reduction."""

    def test_contains_doGet(self) -> None:
        assert "doGet" in _EXCLUDED_METHOD_NAMES

    def test_contains_doPost(self) -> None:
        assert "doPost" in _EXCLUDED_METHOD_NAMES

    def test_contains_service(self) -> None:
        assert "service" in _EXCLUDED_METHOD_NAMES

    def test_contains_init(self) -> None:
        assert "init" in _EXCLUDED_METHOD_NAMES

    def test_contains_destroy(self) -> None:
        assert "destroy" in _EXCLUDED_METHOD_NAMES

    def test_contains_contextInitialized(self) -> None:
        assert "contextInitialized" in _EXCLUDED_METHOD_NAMES

    def test_contains_contextDestroyed(self) -> None:
        assert "contextDestroyed" in _EXCLUDED_METHOD_NAMES

    def test_contains_afterPropertiesSet(self) -> None:
        assert "afterPropertiesSet" in _EXCLUDED_METHOD_NAMES

    def test_contains_onApplicationEvent(self) -> None:
        assert "onApplicationEvent" in _EXCLUDED_METHOD_NAMES

    def test_contains_OnGet(self) -> None:
        assert "OnGet" in _EXCLUDED_METHOD_NAMES

    def test_contains_OnPost(self) -> None:
        assert "OnPost" in _EXCLUDED_METHOD_NAMES

    def test_contains_OnGetAsync(self) -> None:
        assert "OnGetAsync" in _EXCLUDED_METHOD_NAMES

    def test_contains_OnPostAsync(self) -> None:
        assert "OnPostAsync" in _EXCLUDED_METHOD_NAMES

    def test_contains_OnConnectedAsync(self) -> None:
        assert "OnConnectedAsync" in _EXCLUDED_METHOD_NAMES

    def test_contains_OnDisconnectedAsync(self) -> None:
        assert "OnDisconnectedAsync" in _EXCLUDED_METHOD_NAMES

    def test_contains_StartAsync(self) -> None:
        assert "StartAsync" in _EXCLUDED_METHOD_NAMES

    def test_contains_StopAsync(self) -> None:
        assert "StopAsync" in _EXCLUDED_METHOD_NAMES

    def test_contains_ExecuteAsync(self) -> None:
        assert "ExecuteAsync" in _EXCLUDED_METHOD_NAMES

    def test_contains_Invoke(self) -> None:
        assert "Invoke" in _EXCLUDED_METHOD_NAMES

    def test_contains_InvokeAsync(self) -> None:
        assert "InvokeAsync" in _EXCLUDED_METHOD_NAMES


class TestExpandedFrameworkAttributes:
    """New method-level framework attributes for C# and Java."""

    def test_contains_Route(self) -> None:
        assert "Route" in _FRAMEWORK_ATTRIBUTES

    def test_contains_TestInitialize(self) -> None:
        assert "TestInitialize" in _FRAMEWORK_ATTRIBUTES

    def test_contains_TestCleanup(self) -> None:
        assert "TestCleanup" in _FRAMEWORK_ATTRIBUTES

    def test_contains_Benchmark(self) -> None:
        assert "Benchmark" in _FRAMEWORK_ATTRIBUTES

    def test_contains_kafkalistener(self) -> None:
        assert "kafkalistener" in _FRAMEWORK_ATTRIBUTES

    def test_contains_rabbitlistener(self) -> None:
        assert "rabbitlistener" in _FRAMEWORK_ATTRIBUTES

    def test_contains_jmslistener(self) -> None:
        assert "jmslistener" in _FRAMEWORK_ATTRIBUTES

    def test_contains_path(self) -> None:
        assert "path" in _FRAMEWORK_ATTRIBUTES

    def test_contains_jsoncreator(self) -> None:
        assert "jsoncreator" in _FRAMEWORK_ATTRIBUTES

    def test_contains_exceptionhandler(self) -> None:
        assert "exceptionhandler" in _FRAMEWORK_ATTRIBUTES

    def test_contains_transactional(self) -> None:
        assert "transactional" in _FRAMEWORK_ATTRIBUTES


class TestFrameworkClassAttributes:
    """New class-level framework attributes constant."""

    def test_contains_component(self) -> None:
        assert "component" in _FRAMEWORK_CLASS_ATTRIBUTES

    def test_contains_service(self) -> None:
        assert "service" in _FRAMEWORK_CLASS_ATTRIBUTES

    def test_contains_repository(self) -> None:
        assert "repository" in _FRAMEWORK_CLASS_ATTRIBUTES

    def test_contains_controller(self) -> None:
        assert "controller" in _FRAMEWORK_CLASS_ATTRIBUTES

    def test_contains_restcontroller(self) -> None:
        assert "restcontroller" in _FRAMEWORK_CLASS_ATTRIBUTES

    def test_contains_configuration(self) -> None:
        assert "configuration" in _FRAMEWORK_CLASS_ATTRIBUTES

    def test_contains_ApiController(self) -> None:
        assert "ApiController" in _FRAMEWORK_CLASS_ATTRIBUTES

    def test_contains_TestClass(self) -> None:
        assert "TestClass" in _FRAMEWORK_CLASS_ATTRIBUTES

    def test_contains_TestFixture(self) -> None:
        assert "TestFixture" in _FRAMEWORK_CLASS_ATTRIBUTES

    def test_contains_webservlet(self) -> None:
        assert "webservlet" in _FRAMEWORK_CLASS_ATTRIBUTES

    def test_contains_singleton(self) -> None:
        assert "singleton" in _FRAMEWORK_CLASS_ATTRIBUTES


class TestEntityDtoAnnotations:
    """_ENTITY_DTO_ANNOTATIONS constant: Java entity/DTO framework-managed getter/setter classes."""

    def test_contains_entity(self) -> None:
        assert "entity" in _ENTITY_DTO_ANNOTATIONS

    def test_contains_data(self) -> None:
        assert "data" in _ENTITY_DTO_ANNOTATIONS

    def test_contains_embeddable(self) -> None:
        assert "embeddable" in _ENTITY_DTO_ANNOTATIONS

    def test_contains_mappedsuperclass(self) -> None:
        assert "mappedsuperclass" in _ENTITY_DTO_ANNOTATIONS

    def test_contains_getter(self) -> None:
        assert "getter" in _ENTITY_DTO_ANNOTATIONS

    def test_contains_setter(self) -> None:
        assert "setter" in _ENTITY_DTO_ANNOTATIONS

    def test_all_lowercase(self) -> None:
        # JavaAttributeExtractor stores all annotations via .lower(),
        # so every entry must already be lowercase for CONTAINS checks to match.
        assert all(a == a.lower() for a in _ENTITY_DTO_ANNOTATIONS)


class TestBuildExclusionWhereEntityDto:
    """Additional WHERE clause tests for vendor-path and entity/DTO getter/setter exclusions."""

    def setup_method(self) -> None:
        self.clause = _build_base_exclusion_where()

    def test_clause_has_vendor_pattern_exclusion(self) -> None:
        assert "NOT m.file_path =~ $vendor_pattern" in self.clause

    def test_clause_excludes_entity_dto_getters_via_class_annotation(self) -> None:
        # The clause must check c.attributes CONTAINS '"entity"' to detect @Entity classes.
        assert 'CONTAINS \'"entity"\'' in self.clause

    def test_clause_entity_dto_has_name_guard(self) -> None:
        # The name guard restricts exclusion to getter/setter methods only,
        # not all methods on annotated classes.
        assert "m.name STARTS WITH 'get'" in self.clause
        assert "m.name STARTS WITH 'set'" in self.clause
        assert "m.name STARTS WITH 'is'" in self.clause

    def test_entity_dto_name_guard_inside_list_comprehension(self) -> None:
        # The name guard must appear AFTER the second occurrence of "(m)<-[:CONTAINS]-(c:Class)"
        # confirming it is inside the entity/DTO list comprehension WHERE clause, not global.
        # If placed globally, ALL get*/set*/is* methods would be suppressed (D-06 violation).
        class_traversal = "(m)<-[:CONTAINS]-(c:Class)"
        first_idx = self.clause.index(class_traversal)
        second_idx = self.clause.index(class_traversal, first_idx + 1)
        name_guard_idx = self.clause.index("STARTS WITH 'get'")
        assert name_guard_idx > second_idx, (
            "Name guard 'STARTS WITH get' must be inside the entity/DTO list comprehension, "
            "not outside it. Found it before the second class traversal pattern."
        )
