import pytest
import tree_sitter_java
from tree_sitter import Language, Parser
from synapps.indexer.java.java_type_ref_extractor import JavaTypeRefExtractor
from synapps.indexer.type_ref import TypeRef

_lang = Language(tree_sitter_java.language())
_parser = Parser(_lang)


def _parse(source: str):
    return _parser.parse(bytes(source, "utf-8"))


FILE = "/proj/MyClass.java"


@pytest.fixture
def extractor():
    return JavaTypeRefExtractor()


def _sm(line: int, name: str) -> dict:
    return {(FILE, line): name}


def _csm(line: int, name: str) -> list[tuple[int, str]]:
    return [(line, name)]


# ---------------------------------------------------------------------------
# Parameter types
# ---------------------------------------------------------------------------


def test_parameter_type(extractor):
    source = """\
public class MyClass {
    public void greet(Animal a) {}
}
"""
    symbol_map = _sm(1, "com.example.MyClass.greet")
    results = extractor.extract(FILE, _parse(source), symbol_map)
    assert any(r.type_name == "Animal" and r.ref_kind == "parameter" for r in results)


def test_multiple_parameter_types(extractor):
    source = """\
public class MyClass {
    public void process(Foo a, Bar b) {}
}
"""
    symbol_map = _sm(1, "com.example.MyClass.process")
    results = extractor.extract(FILE, _parse(source), symbol_map)
    names = {r.type_name for r in results if r.ref_kind == "parameter"}
    assert "Foo" in names
    assert "Bar" in names


# ---------------------------------------------------------------------------
# Return types
# ---------------------------------------------------------------------------


def test_return_type(extractor):
    source = """\
public class MyClass {
    public String getName() { return ""; }
}
"""
    symbol_map = _sm(1, "com.example.MyClass.getName")
    results = extractor.extract(FILE, _parse(source), symbol_map)
    assert any(r.type_name == "String" and r.ref_kind == "return_type" for r in results)


# ---------------------------------------------------------------------------
# Field types
# ---------------------------------------------------------------------------


def test_field_type(extractor):
    source = """\
public class MyClass {
    private Animal animal;
}
"""
    class_symbol_map = _csm(0, "com.example.MyClass")
    results = extractor.extract(FILE, _parse(source), {}, class_symbol_map)
    assert any(r.type_name == "Animal" and r.ref_kind == "field_type" for r in results)


# ---------------------------------------------------------------------------
# Generic types
# ---------------------------------------------------------------------------


def test_generic_type(extractor):
    source = """\
public class MyClass {
    private List<Animal> animals;
}
"""
    class_symbol_map = _csm(0, "com.example.MyClass")
    results = extractor.extract(FILE, _parse(source), {}, class_symbol_map)
    names = {r.type_name for r in results}
    assert "List" in names
    assert "Animal" in names


def test_nested_generic_type(extractor):
    source = """\
public class MyClass {
    private Map<String, List<Animal>> lookup;
}
"""
    class_symbol_map = _csm(0, "com.example.MyClass")
    results = extractor.extract(FILE, _parse(source), {}, class_symbol_map)
    names = {r.type_name for r in results}
    assert "Map" in names
    assert "String" in names
    assert "List" in names
    assert "Animal" in names


# ---------------------------------------------------------------------------
# Primitive / void filtering (D-20)
# ---------------------------------------------------------------------------


def test_skips_primitives(extractor):
    source = """\
public class MyClass {
    public void process(int count, boolean flag, long id) {}
}
"""
    symbol_map = _sm(1, "com.example.MyClass.process")
    results = extractor.extract(FILE, _parse(source), symbol_map)
    type_names = {r.type_name for r in results}
    assert "int" not in type_names
    assert "boolean" not in type_names
    assert "long" not in type_names


def test_skips_void(extractor):
    source = """\
public class MyClass {
    public void doWork() {}
}
"""
    symbol_map = _sm(1, "com.example.MyClass.doWork")
    results = extractor.extract(FILE, _parse(source), symbol_map)
    type_names = {r.type_name for r in results}
    assert "void" not in type_names


def test_skips_all_java_primitives(extractor):
    source = """\
public class MyClass {
    public void all(int a, long b, short c, byte d, float e, double f, boolean g, char h) {}
}
"""
    symbol_map = _sm(1, "com.example.MyClass.all")
    results = extractor.extract(FILE, _parse(source), symbol_map)
    type_names = {r.type_name for r in results}
    for prim in ("int", "long", "short", "byte", "float", "double", "boolean", "char"):
        assert prim not in type_names, f"Expected {prim!r} to be filtered"


# ---------------------------------------------------------------------------
# Local variable types
# ---------------------------------------------------------------------------


def test_local_variable_type(extractor):
    source = """\
public class MyClass {
    public void process() {
        Animal a = new Animal();
    }
}
"""
    symbol_map = _sm(1, "com.example.MyClass.process")
    results = extractor.extract(FILE, _parse(source), symbol_map)
    assert any(r.type_name == "Animal" for r in results)


# ---------------------------------------------------------------------------
# Array types
# ---------------------------------------------------------------------------


def test_array_type(extractor):
    source = """\
public class MyClass {
    private Animal[] animals;
}
"""
    class_symbol_map = _csm(0, "com.example.MyClass")
    results = extractor.extract(FILE, _parse(source), {}, class_symbol_map)
    assert any(r.type_name == "Animal" for r in results)


# ---------------------------------------------------------------------------
# No type refs / empty source
# ---------------------------------------------------------------------------


def test_no_type_refs(extractor):
    """Constructor with no typed params yields no refs (only primitives)."""
    source = """\
public class MyClass {
    public MyClass() {}
}
"""
    results = extractor.extract(FILE, _parse(source), {})
    assert results == []


def test_empty_source(extractor):
    results = extractor.extract(FILE, _parse(""), {})
    assert results == []


def test_whitespace_source(extractor):
    results = extractor.extract(FILE, _parse("   \n  "), {})
    assert results == []


# ---------------------------------------------------------------------------
# TypeRef structure
# ---------------------------------------------------------------------------


def test_type_ref_has_correct_owner(extractor):
    source = """\
public class MyClass {
    public void greet(Animal a) {}
}
"""
    symbol_map = _sm(1, "com.example.MyClass.greet")
    results = extractor.extract(FILE, _parse(source), symbol_map)
    animal_refs = [r for r in results if r.type_name == "Animal"]
    assert len(animal_refs) >= 1
    assert animal_refs[0].owner_full_name == "com.example.MyClass.greet"


# ---------------------------------------------------------------------------
# @Autowired field type ref extraction (Issue #2)
# ---------------------------------------------------------------------------


def test_autowired_field_type_ref_has_owner_class(extractor):
    """@Autowired field type refs must carry the containing class as owner_full_name.

    When class_lines is populated with the class scope, JavaTypeRefExtractor must
    use find_enclosing_scope to attribute the field ref to the enclosing class.
    This is the fixed-state test: class_lines is properly passed.
    """
    source = """\
package com.example;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.client.RestTemplate;

public class OrderService {
    @Autowired
    private RestTemplate restTemplate;

    public void doSomething() {}
}
"""
    # class_lines: OrderService class starts at line 5 (0-indexed)
    class_lines = [(5, "com.example.OrderService")]
    results = extractor.extract(FILE, _parse(source), {}, class_lines)
    rest_template_refs = [r for r in results if r.type_name == "RestTemplate"]
    assert rest_template_refs, "Expected a TypeRef for RestTemplate field"
    assert rest_template_refs[0].owner_full_name == "com.example.OrderService", (
        f"Expected owner 'com.example.OrderService' but got {rest_template_refs[0].owner_full_name!r}"
    )
    assert rest_template_refs[0].ref_kind == "field_type"


def test_field_type_ref_no_owner_without_class_lines(extractor):
    """When class_lines is empty, field type refs cannot find an enclosing scope.

    This documents the baseline behavior: without class_lines, the owner is None
    and the TypeRef is filtered out (find_enclosing_scope returns None -> no emit).
    The fix is upstream (class_lines_per_file propagation from indexer.py), not here.
    """
    source = """\
package com.example;

public class OrderService {
    private RestTemplate restTemplate;
}
"""
    # No class_lines provided — simulates the broken propagation case
    results = extractor.extract(FILE, _parse(source), {}, class_lines=[])
    rest_template_refs = [r for r in results if r.type_name == "RestTemplate"]
    # With empty class_lines, find_enclosing_scope returns None and no TypeRef is emitted
    assert rest_template_refs == [], (
        "Expected no TypeRef for RestTemplate when class_lines is empty "
        f"(broken baseline), but got: {rest_template_refs}"
    )


# ---------------------------------------------------------------------------
# field_symbol_map: field-level owner for REFERENCES edges (FILD-02)
# ---------------------------------------------------------------------------


def test_field_ref_uses_field_owner(extractor):
    """When field_symbol_map provides a field full_name, TypeRef.owner_full_name is the field.

    The REFERENCES edge source must be the Field node (com.example.AnimalService.animal),
    not the enclosing class (com.example.AnimalService).
    """
    source = """\
package com.example;

public class AnimalService {
    private IAnimal animal;
}
"""
    # field 'animal' at line 3 (0-indexed) in the source above
    class_lines = [(2, "com.example.AnimalService")]
    field_symbol_map = {(FILE, 3): "com.example.AnimalService.animal"}
    results = extractor.extract(FILE, _parse(source), {}, class_lines, field_symbol_map=field_symbol_map)
    ianimal_refs = [r for r in results if r.type_name == "IAnimal"]
    assert ianimal_refs, "Expected a TypeRef for IAnimal field"
    assert ianimal_refs[0].owner_full_name == "com.example.AnimalService.animal", (
        f"Expected owner 'com.example.AnimalService.animal', got {ianimal_refs[0].owner_full_name!r}"
    )
    assert ianimal_refs[0].ref_kind == "field_type"


def test_field_ref_fallback_to_class(extractor):
    """When field_symbol_map has no entry for a field_declaration, fall back to class scope."""
    source = """\
package com.example;

public class AnimalService {
    private IAnimal animal;
}
"""
    class_lines = [(2, "com.example.AnimalService")]
    # field_symbol_map provided but does not contain this field
    results = extractor.extract(FILE, _parse(source), {}, class_lines, field_symbol_map={})
    ianimal_refs = [r for r in results if r.type_name == "IAnimal"]
    assert ianimal_refs, "Expected a TypeRef for IAnimal field"
    assert ianimal_refs[0].owner_full_name == "com.example.AnimalService", (
        f"Expected class-level fallback owner 'com.example.AnimalService', "
        f"got {ianimal_refs[0].owner_full_name!r}"
    )


def test_backward_compat_no_field_map(extractor):
    """Calling extract() without field_symbol_map kwarg behaves identically to before.

    Field declarations use the class-level owner (from class_lines scope lookup).
    """
    source = """\
package com.example;

public class AnimalService {
    private IAnimal animal;
}
"""
    class_lines = [(2, "com.example.AnimalService")]
    # No field_symbol_map argument — backward-compatible call
    results = extractor.extract(FILE, _parse(source), {}, class_lines)
    ianimal_refs = [r for r in results if r.type_name == "IAnimal"]
    assert ianimal_refs, "Expected a TypeRef for IAnimal field"
    assert ianimal_refs[0].owner_full_name == "com.example.AnimalService", (
        f"Expected class-level owner 'com.example.AnimalService', "
        f"got {ianimal_refs[0].owner_full_name!r}"
    )
