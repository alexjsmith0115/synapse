import pytest
from synapse.indexer.java.java_base_type_extractor import JavaBaseTypeExtractor


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
    results = extractor.extract("/proj/Dog.java", source)
    assert results == [("Dog", "Animal", True)]


def test_implements_interface(extractor):
    source = """\
public class Dog implements IAnimal {
}
"""
    results = extractor.extract("/proj/Dog.java", source)
    assert results == [("Dog", "IAnimal", True)]


def test_extends_and_implements(extractor):
    """D-18: extends target is_first_base=True, first implements is_first_base=True (separate clauses)."""
    source = """\
public class Dog extends Animal implements IAnimal, Comparable {
}
"""
    results = extractor.extract("/proj/Dog.java", source)
    assert ("Dog", "Animal", True) in results
    assert ("Dog", "IAnimal", True) in results
    assert ("Dog", "Comparable", False) in results
    assert len(results) == 3


def test_implements_multiple(extractor):
    source = """\
public class Service implements Serializable, Cloneable, Comparable {
}
"""
    results = extractor.extract("/proj/Service.java", source)
    assert ("Service", "Serializable", True) in results
    assert ("Service", "Cloneable", False) in results
    assert ("Service", "Comparable", False) in results


# ---------------------------------------------------------------------------
# Interface extends
# ---------------------------------------------------------------------------


def test_interface_extends(extractor):
    source = """\
public interface IAdvanced extends IBasic {
}
"""
    results = extractor.extract("/proj/IAdvanced.java", source)
    assert results == [("IAdvanced", "IBasic", True)]


def test_interface_extends_multiple(extractor):
    source = """\
public interface IAdvanced extends IBasic, ISerializable {
}
"""
    results = extractor.extract("/proj/IAdvanced.java", source)
    assert ("IAdvanced", "IBasic", True) in results
    assert ("IAdvanced", "ISerializable", False) in results


# ---------------------------------------------------------------------------
# Generic base types
# ---------------------------------------------------------------------------


def test_extends_generic(extractor):
    source = """\
public class MyList extends ArrayList<String> {
}
"""
    results = extractor.extract("/proj/MyList.java", source)
    assert results == [("MyList", "ArrayList", True)]


def test_implements_generic(extractor):
    source = """\
public class Foo implements Comparable<String> {
}
"""
    results = extractor.extract("/proj/Foo.java", source)
    assert results == [("Foo", "Comparable", True)]


# ---------------------------------------------------------------------------
# No inheritance / empty source
# ---------------------------------------------------------------------------


def test_no_inheritance(extractor):
    source = """\
public class Foo {
    private int x;
}
"""
    results = extractor.extract("/proj/Foo.java", source)
    assert results == []


def test_empty_source(extractor):
    results = extractor.extract("/proj/Foo.java", "")
    assert results == []


def test_whitespace_source(extractor):
    results = extractor.extract("/proj/Foo.java", "   \n  ")
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
    results = extractor.extract("/proj/Animals.java", source)
    assert ("Dog", "Animal", True) in results
    assert ("Cat", "IAnimal", True) in results
