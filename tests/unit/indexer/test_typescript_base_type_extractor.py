import pytest
from synapse.indexer.typescript.typescript_base_type_extractor import TypeScriptBaseTypeExtractor


@pytest.fixture()
def extractor() -> TypeScriptBaseTypeExtractor:
    return TypeScriptBaseTypeExtractor()


def test_class_single_extends(extractor: TypeScriptBaseTypeExtractor) -> None:
    source = "class Dog extends Animal {}"
    result = extractor.extract("test.ts", source)
    assert result == [("Dog", "Animal", True)]


def test_class_extends_and_implements(extractor: TypeScriptBaseTypeExtractor) -> None:
    source = "class Dog extends Animal implements IAnimal, ISerializable {}"
    result = extractor.extract("test.ts", source)
    assert result == [
        ("Dog", "Animal", True),
        ("Dog", "IAnimal", True),
        ("Dog", "ISerializable", False),
    ]


def test_class_implements_only(extractor: TypeScriptBaseTypeExtractor) -> None:
    source = "class Cat implements IAnimal {}"
    result = extractor.extract("test.ts", source)
    assert result == [("Cat", "IAnimal", True)]


def test_class_extends_generic(extractor: TypeScriptBaseTypeExtractor) -> None:
    source = "class MyList extends Array<string> {}"
    result = extractor.extract("test.ts", source)
    assert result == [("MyList", "Array", True)]


def test_class_extends_qualified(extractor: TypeScriptBaseTypeExtractor) -> None:
    source = "class Service extends ns.Base {}"
    result = extractor.extract("test.ts", source)
    assert result == [("Service", "Base", True)]


def test_class_implements_qualified(extractor: TypeScriptBaseTypeExtractor) -> None:
    source = "class Service implements ns.IService {}"
    result = extractor.extract("test.ts", source)
    assert result == [("Service", "IService", True)]


def test_abstract_class_extends(extractor: TypeScriptBaseTypeExtractor) -> None:
    source = "abstract class AbstractBase extends BaseClass implements IBase {}"
    result = extractor.extract("test.ts", source)
    assert result == [
        ("AbstractBase", "BaseClass", True),
        ("AbstractBase", "IBase", True),
    ]


def test_interface_extends_single(extractor: TypeScriptBaseTypeExtractor) -> None:
    source = "interface ICat extends IAnimal {}"
    result = extractor.extract("test.ts", source)
    assert result == [("ICat", "IAnimal", True)]


def test_interface_extends_multiple(extractor: TypeScriptBaseTypeExtractor) -> None:
    source = "interface ICat extends IAnimal, ISerializable {}"
    result = extractor.extract("test.ts", source)
    assert result == [("ICat", "IAnimal", True), ("ICat", "ISerializable", False)]


def test_interface_extends_generic(extractor: TypeScriptBaseTypeExtractor) -> None:
    source = "interface ICollection<T> extends Iterable<T> {}"
    result = extractor.extract("test.ts", source)
    assert result == [("ICollection", "Iterable", True)]


def test_no_base_types(extractor: TypeScriptBaseTypeExtractor) -> None:
    source = "class Standalone {}"
    result = extractor.extract("test.ts", source)
    assert result == []


def test_empty_source(extractor: TypeScriptBaseTypeExtractor) -> None:
    result = extractor.extract("test.ts", "")
    assert result == []


def test_tsx_file_jsx_syntax(extractor: TypeScriptBaseTypeExtractor) -> None:
    source = "class MyComponent extends React.Component { render() { return <div />; } }"
    # Should not raise even with JSX syntax
    result = extractor.extract("MyComponent.tsx", source)
    assert isinstance(result, list)


def test_multiple_classes_in_file(extractor: TypeScriptBaseTypeExtractor) -> None:
    source = "class Dog extends Animal {}\nclass Cat implements IAnimal {}"
    result = extractor.extract("test.ts", source)
    assert ("Dog", "Animal", True) in result
    assert ("Cat", "IAnimal", True) in result


def test_implements_with_generic(extractor: TypeScriptBaseTypeExtractor) -> None:
    source = "class Foo implements Comparable<string> {}"
    result = extractor.extract("test.ts", source)
    assert result == [("Foo", "Comparable", True)]
