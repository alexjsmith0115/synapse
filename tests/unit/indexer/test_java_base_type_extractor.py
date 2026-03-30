import pytest
import tree_sitter_java
from tree_sitter import Language, Parser
from synapps.indexer.java.java_base_type_extractor import JavaBaseTypeExtractor

_lang = Language(tree_sitter_java.language())
_parser = Parser(_lang)


def _parse(source: str):
    return _parser.parse(bytes(source, "utf-8"))


@pytest.fixture
def extractor():
    return JavaBaseTypeExtractor()


# ---------------------------------------------------------------------------
# Class inheritance
# ---------------------------------------------------------------------------


def test_single_inheritance(extractor):
    source = """\
public class Dog extends Animal {
}
"""
    results = extractor.extract("/proj/Dog.java", _parse(source))
    assert len(results) == 1
    assert results[0][:3] == ("Dog", "Animal", True)


def test_implements_interface(extractor):
    source = """\
public class Dog implements IAnimal {
}
"""
    results = extractor.extract("/proj/Dog.java", _parse(source))
    assert len(results) == 1
    assert results[0][:3] == ("Dog", "IAnimal", True)


def test_extends_and_implements(extractor):
    """D-18: extends target is_first_base=True, first implements is_first_base=True (separate clauses)."""
    source = """\
public class Dog extends Animal implements IAnimal, Comparable {
}
"""
    results = extractor.extract("/proj/Dog.java", _parse(source))
    assert any(r[:3] == ("Dog", "Animal", True) for r in results)
    assert any(r[:3] == ("Dog", "IAnimal", True) for r in results)
    assert any(r[:3] == ("Dog", "Comparable", False) for r in results)
    assert len(results) == 3


def test_implements_multiple(extractor):
    source = """\
public class Service implements Serializable, Cloneable, Comparable {
}
"""
    results = extractor.extract("/proj/Service.java", _parse(source))
    assert any(r[:3] == ("Service", "Serializable", True) for r in results)
    assert any(r[:3] == ("Service", "Cloneable", False) for r in results)
    assert any(r[:3] == ("Service", "Comparable", False) for r in results)


# ---------------------------------------------------------------------------
# Interface extends
# ---------------------------------------------------------------------------


def test_interface_extends(extractor):
    source = """\
public interface IAdvanced extends IBasic {
}
"""
    results = extractor.extract("/proj/IAdvanced.java", _parse(source))
    assert len(results) == 1
    assert results[0][:3] == ("IAdvanced", "IBasic", True)


def test_interface_extends_multiple(extractor):
    source = """\
public interface IAdvanced extends IBasic, ISerializable {
}
"""
    results = extractor.extract("/proj/IAdvanced.java", _parse(source))
    assert any(r[:3] == ("IAdvanced", "IBasic", True) for r in results)
    assert any(r[:3] == ("IAdvanced", "ISerializable", False) for r in results)


# ---------------------------------------------------------------------------
# Generic base types
# ---------------------------------------------------------------------------


def test_extends_generic(extractor):
    source = """\
public class MyList extends ArrayList<String> {
}
"""
    results = extractor.extract("/proj/MyList.java", _parse(source))
    assert len(results) == 1
    assert results[0][:3] == ("MyList", "ArrayList", True)


def test_implements_generic(extractor):
    source = """\
public class Foo implements Comparable<String> {
}
"""
    results = extractor.extract("/proj/Foo.java", _parse(source))
    assert len(results) == 1
    assert results[0][:3] == ("Foo", "Comparable", True)


# ---------------------------------------------------------------------------
# No inheritance / empty source
# ---------------------------------------------------------------------------


def test_no_inheritance(extractor):
    source = """\
public class Foo {
    private int x;
}
"""
    results = extractor.extract("/proj/Foo.java", _parse(source))
    assert results == []


def test_empty_source(extractor):
    results = extractor.extract("/proj/Foo.java", _parse(""))
    assert results == []


def test_whitespace_source(extractor):
    results = extractor.extract("/proj/Foo.java", _parse("   \n  "))
    assert results == []


# ---------------------------------------------------------------------------
# Multiple classes in one file
# ---------------------------------------------------------------------------


def test_multiple_classes_in_file(extractor):
    source = """\
public class Dog extends Animal {
}

class Cat implements IAnimal {
}
"""
    results = extractor.extract("/proj/Animals.java", _parse(source))
    assert any(r[:3] == ("Dog", "Animal", True) for r in results)
    assert any(r[:3] == ("Cat", "IAnimal", True) for r in results)


# ---------------------------------------------------------------------------
# Regression: extends vs implements is_first semantics for edge creation
# ---------------------------------------------------------------------------


def test_extends_is_first_separate_from_implements(extractor):
    """Regression: extends and implements have independent is_first flags.

    In Java, 'extends Foo' always has is_first=True (class inheritance).
    'implements Bar, Baz' has is_first=True for Bar (first interface) and
    is_first=False for Baz. The indexer uses kind_map to determine edge type.
    """
    source = """\
public class Dog extends Animal implements IAnimal, Comparable {
}
"""
    results = extractor.extract("/proj/Dog.java", _parse(source))
    # extends target always is_first=True
    assert any(r[:3] == ("Dog", "Animal", True) for r in results)
    # first implements is_first=True
    assert any(r[:3] == ("Dog", "IAnimal", True) for r in results)
    # subsequent implements is_first=False
    assert any(r[:3] == ("Dog", "Comparable", False) for r in results)


# ---------------------------------------------------------------------------
# Position tests
# ---------------------------------------------------------------------------


def test_positions_are_integers(extractor):
    """Positions (line, col) must be non-negative integers from tree-sitter start_point."""
    source = "public class Dog extends Animal {}\n"
    results = extractor.extract("/proj/Dog.java", _parse(source))
    assert len(results) == 1
    _, _, _, line, col = results[0]
    assert isinstance(line, int) and line >= 0
    assert isinstance(col, int) and col >= 0
