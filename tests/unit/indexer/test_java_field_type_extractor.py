from __future__ import annotations

import pytest
import tree_sitter_java
from tree_sitter import Language, Parser

from synapps.indexer.java.java_field_type_extractor import JavaFieldTypeExtractor

_lang = Language(tree_sitter_java.language())
_parser = Parser(_lang)


def _parse(source: str):
    return _parser.parse(bytes(source, "utf-8"))


FILE = "/proj/MyClass.java"


@pytest.fixture
def extractor():
    return JavaFieldTypeExtractor()


# ---------------------------------------------------------------------------
# Simple field types
# ---------------------------------------------------------------------------


def test_simple_field(extractor):
    source = """\
public class MyClass {
    private IAnimal animal;
}
"""
    results = extractor.extract(FILE, _parse(source))
    assert ("animal", "IAnimal") in results


def test_generic_field(extractor):
    """Generic field like List<Order> -> outer type only."""
    source = """\
public class MyClass {
    private List<Order> orders;
}
"""
    results = extractor.extract(FILE, _parse(source))
    assert ("orders", "List") in results


def test_array_field(extractor):
    """Array field like Animal[] -> element type."""
    source = """\
public class MyClass {
    private Animal[] animals;
}
"""
    results = extractor.extract(FILE, _parse(source))
    assert ("animals", "Animal") in results


def test_multiple_declarators(extractor):
    """Multiple declarators on one line: Foo a, b -> two pairs."""
    source = """\
public class MyClass {
    private Foo a, b;
}
"""
    results = extractor.extract(FILE, _parse(source))
    assert ("a", "Foo") in results
    assert ("b", "Foo") in results


def test_primitive_field_skipped(extractor):
    """Primitive fields produce no results."""
    source = """\
public class MyClass {
    private int count;
}
"""
    results = extractor.extract(FILE, _parse(source))
    assert len(results) == 0


def test_nested_class_fields(extractor):
    """Fields in nested classes are handled."""
    source = """\
public class Outer {
    private Foo foo;

    public class Inner {
        private Bar bar;
    }
}
"""
    results = extractor.extract(FILE, _parse(source))
    names = {name for name, _ in results}
    assert "foo" in names
    assert "bar" in names


def test_empty_source(extractor):
    results = extractor.extract(FILE, _parse(""))
    assert results == []
