import pytest
import tree_sitter_python
from tree_sitter import Language, Parser
from synapse.indexer.python.python_base_type_extractor import PythonBaseTypeExtractor

_lang = Language(tree_sitter_python.language())
_parser = Parser(_lang)


def _parse(source: str):
    return _parser.parse(bytes(source, "utf-8"))


@pytest.fixture()
def extractor() -> PythonBaseTypeExtractor:
    return PythonBaseTypeExtractor()


def test_single_inheritance(extractor: PythonBaseTypeExtractor) -> None:
    source = "class Dog(Animal): pass"
    result = extractor.extract("test.py", _parse(source))
    assert result == [("Dog", "Animal", True)]


def test_multiple_inheritance(extractor: PythonBaseTypeExtractor) -> None:
    source = "class Formatter(TextMixin, SerializeMixin): pass"
    result = extractor.extract("test.py", _parse(source))
    assert result == [("Formatter", "TextMixin", True), ("Formatter", "SerializeMixin", False)]


def test_abc_inheritance(extractor: PythonBaseTypeExtractor) -> None:
    source = "class IAnimal(ABC): pass"
    result = extractor.extract("test.py", _parse(source))
    assert result == [("IAnimal", "ABC", True)]


def test_no_base_class(extractor: PythonBaseTypeExtractor) -> None:
    source = "class Standalone: pass"
    result = extractor.extract("test.py", _parse(source))
    assert result == []


def test_dotted_base(extractor: PythonBaseTypeExtractor) -> None:
    source = "class Foo(mymod.Base): pass"
    result = extractor.extract("test.py", _parse(source))
    assert result == [("Foo", "Base", True)]


def test_nested_class(extractor: PythonBaseTypeExtractor) -> None:
    source = "class Outer:\n  class Inner(Base): pass"
    result = extractor.extract("test.py", _parse(source))
    assert ("Inner", "Base", True) in result


def test_empty_source(extractor: PythonBaseTypeExtractor) -> None:
    result = extractor.extract("test.py", _parse(""))
    assert result == []
