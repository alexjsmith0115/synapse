import pytest
from synapse.indexer.java.java_type_ref_extractor import JavaTypeRefExtractor
from synapse.indexer.type_ref import TypeRef

FILE = "/proj/MyClass.java"


@pytest.fixture
def extractor():
    return JavaTypeRefExtractor()


def _sm(line: int, name: str) -> dict:
    return {(FILE, line): name}


def _csm(line: int, name: str) -> dict:
    return {(FILE, line): name}


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
    results = extractor.extract(FILE, source, symbol_map)
    assert any(r.type_name == "Animal" and r.ref_kind == "parameter" for r in results)


def test_multiple_parameter_types(extractor):
    source = """\
public class MyClass {
    public void process(Foo a, Bar b) {}
}
"""
    symbol_map = _sm(1, "com.example.MyClass.process")
    results = extractor.extract(FILE, source, symbol_map)
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
    results = extractor.extract(FILE, source, symbol_map)
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
    results = extractor.extract(FILE, source, {}, class_symbol_map)
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
    results = extractor.extract(FILE, source, {}, class_symbol_map)
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
    results = extractor.extract(FILE, source, {}, class_symbol_map)
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
    results = extractor.extract(FILE, source, symbol_map)
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
    results = extractor.extract(FILE, source, symbol_map)
    type_names = {r.type_name for r in results}
    assert "void" not in type_names


def test_skips_all_java_primitives(extractor):
    source = """\
public class MyClass {
    public void all(int a, long b, short c, byte d, float e, double f, boolean g, char h) {}
}
"""
    symbol_map = _sm(1, "com.example.MyClass.all")
    results = extractor.extract(FILE, source, symbol_map)
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
    results = extractor.extract(FILE, source, symbol_map)
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
    results = extractor.extract(FILE, source, {}, class_symbol_map)
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
    results = extractor.extract(FILE, source, {})
    assert results == []


def test_empty_source(extractor):
    results = extractor.extract(FILE, "", {})
    assert results == []


def test_whitespace_source(extractor):
    results = extractor.extract(FILE, "   \n  ", {})
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
    results = extractor.extract(FILE, source, symbol_map)
    animal_refs = [r for r in results if r.type_name == "Animal"]
    assert len(animal_refs) >= 1
    assert animal_refs[0].owner_full_name == "com.example.MyClass.greet"
