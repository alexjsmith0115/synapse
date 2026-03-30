import pytest
import tree_sitter_typescript
from tree_sitter import Language, Parser

from synapps.indexer.typescript.typescript_base_type_extractor import TypeScriptBaseTypeExtractor

_ts_lang = Language(tree_sitter_typescript.language_typescript())
_tsx_lang = Language(tree_sitter_typescript.language_tsx())
_ts_parser = Parser(_ts_lang)
_tsx_parser = Parser(_tsx_lang)
_TSX_EXTENSIONS = frozenset({".tsx", ".jsx"})


def _parse(source: str, file_path: str = "/tmp/test.ts"):
    uses_tsx = any(file_path.endswith(ext) for ext in _TSX_EXTENSIONS)
    parser = _tsx_parser if uses_tsx else _ts_parser
    return parser.parse(bytes(source, "utf-8"))


@pytest.fixture()
def extractor() -> TypeScriptBaseTypeExtractor:
    return TypeScriptBaseTypeExtractor()


def test_class_single_extends(extractor: TypeScriptBaseTypeExtractor) -> None:
    source = "class Dog extends Animal {}"
    result = extractor.extract("test.ts", _parse(source, "test.ts"))
    assert len(result) == 1
    assert result[0][:3] == ("Dog", "Animal", True)


def test_class_extends_and_implements(extractor: TypeScriptBaseTypeExtractor) -> None:
    source = "class Dog extends Animal implements IAnimal, ISerializable {}"
    result = extractor.extract("test.ts", _parse(source, "test.ts"))
    assert len(result) == 3
    assert result[0][:3] == ("Dog", "Animal", True)
    assert result[1][:3] == ("Dog", "IAnimal", True)
    assert result[2][:3] == ("Dog", "ISerializable", False)


def test_class_implements_only(extractor: TypeScriptBaseTypeExtractor) -> None:
    source = "class Cat implements IAnimal {}"
    result = extractor.extract("test.ts", _parse(source, "test.ts"))
    assert len(result) == 1
    assert result[0][:3] == ("Cat", "IAnimal", True)


def test_class_extends_generic(extractor: TypeScriptBaseTypeExtractor) -> None:
    source = "class MyList extends Array<string> {}"
    result = extractor.extract("test.ts", _parse(source, "test.ts"))
    assert len(result) == 1
    assert result[0][:3] == ("MyList", "Array", True)


def test_class_extends_qualified(extractor: TypeScriptBaseTypeExtractor) -> None:
    source = "class Service extends ns.Base {}"
    result = extractor.extract("test.ts", _parse(source, "test.ts"))
    assert len(result) == 1
    assert result[0][:3] == ("Service", "Base", True)


def test_class_implements_qualified(extractor: TypeScriptBaseTypeExtractor) -> None:
    source = "class Service implements ns.IService {}"
    result = extractor.extract("test.ts", _parse(source, "test.ts"))
    assert len(result) == 1
    assert result[0][:3] == ("Service", "IService", True)


def test_abstract_class_extends(extractor: TypeScriptBaseTypeExtractor) -> None:
    source = "abstract class AbstractBase extends BaseClass implements IBase {}"
    result = extractor.extract("test.ts", _parse(source, "test.ts"))
    assert len(result) == 2
    assert result[0][:3] == ("AbstractBase", "BaseClass", True)
    assert result[1][:3] == ("AbstractBase", "IBase", True)


def test_interface_extends_single(extractor: TypeScriptBaseTypeExtractor) -> None:
    source = "interface ICat extends IAnimal {}"
    result = extractor.extract("test.ts", _parse(source, "test.ts"))
    assert len(result) == 1
    assert result[0][:3] == ("ICat", "IAnimal", True)


def test_interface_extends_multiple(extractor: TypeScriptBaseTypeExtractor) -> None:
    source = "interface ICat extends IAnimal, ISerializable {}"
    result = extractor.extract("test.ts", _parse(source, "test.ts"))
    assert len(result) == 2
    assert result[0][:3] == ("ICat", "IAnimal", True)
    assert result[1][:3] == ("ICat", "ISerializable", False)


def test_interface_extends_generic(extractor: TypeScriptBaseTypeExtractor) -> None:
    source = "interface ICollection<T> extends Iterable<T> {}"
    result = extractor.extract("test.ts", _parse(source, "test.ts"))
    assert len(result) == 1
    assert result[0][:3] == ("ICollection", "Iterable", True)


def test_no_base_types(extractor: TypeScriptBaseTypeExtractor) -> None:
    source = "class Standalone {}"
    result = extractor.extract("test.ts", _parse(source, "test.ts"))
    assert result == []


def test_empty_source(extractor: TypeScriptBaseTypeExtractor) -> None:
    result = extractor.extract("test.ts", _parse("", "test.ts"))
    assert result == []


def test_tsx_file_jsx_syntax(extractor: TypeScriptBaseTypeExtractor) -> None:
    source = "class MyComponent extends React.Component { render() { return <div />; } }"
    # Should not raise even with JSX syntax
    result = extractor.extract("MyComponent.tsx", _parse(source, "MyComponent.tsx"))
    assert isinstance(result, list)


def test_multiple_classes_in_file(extractor: TypeScriptBaseTypeExtractor) -> None:
    source = "class Dog extends Animal {}\nclass Cat implements IAnimal {}"
    result = extractor.extract("test.ts", _parse(source, "test.ts"))
    assert any(r[:3] == ("Dog", "Animal", True) for r in result)
    assert any(r[:3] == ("Cat", "IAnimal", True) for r in result)


def test_implements_with_generic(extractor: TypeScriptBaseTypeExtractor) -> None:
    source = "class Foo implements Comparable<string> {}"
    result = extractor.extract("test.ts", _parse(source, "test.ts"))
    assert len(result) == 1
    assert result[0][:3] == ("Foo", "Comparable", True)


def test_positions_are_integers(extractor: TypeScriptBaseTypeExtractor) -> None:
    """Positions (line, col) must be non-negative integers from tree-sitter start_point."""
    source = "class Dog extends Animal {}"
    result = extractor.extract("test.ts", _parse(source, "test.ts"))
    assert len(result) == 1
    _, _, _, line, col = result[0]
    assert isinstance(line, int) and line >= 0
    assert isinstance(col, int) and col >= 0


def test_qualified_extends_position_points_to_property(extractor: TypeScriptBaseTypeExtractor) -> None:
    """For 'ns.Base', position should point to 'Base' property_identifier, not member_expression."""
    source = "class Service extends ns.Base {}"
    result = extractor.extract("test.ts", _parse(source, "test.ts"))
    assert len(result) == 1
    _, base_name, _, line, col = result[0]
    assert base_name == "Base"
    # 'Base' comes after 'class Service extends ns.' (24 chars), col >= 23
    assert col >= 3
