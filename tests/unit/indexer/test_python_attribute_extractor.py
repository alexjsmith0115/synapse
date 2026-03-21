"""Unit tests for PythonAttributeExtractor — PMET requirements."""
from synapse.indexer.python.python_attribute_extractor import PythonAttributeExtractor


def _make() -> PythonAttributeExtractor:
    return PythonAttributeExtractor()


def test_extract_abstractmethod_decorator() -> None:
    source = """\
from abc import ABC, abstractmethod

class IAnimal(ABC):
    @abstractmethod
    def speak(self) -> str: ...
"""
    extractor = _make()
    results = extractor.extract("test.py", source)
    names_and_attrs = {name: attrs for name, attrs in results}
    assert "speak" in names_and_attrs
    assert "abstractmethod" in names_and_attrs["speak"]


def test_extract_staticmethod_decorator() -> None:
    source = """\
class Service:
    @staticmethod
    def version() -> str:
        return "1.0.0"
"""
    extractor = _make()
    results = extractor.extract("test.py", source)
    names_and_attrs = {name: attrs for name, attrs in results}
    assert "version" in names_and_attrs
    assert "staticmethod" in names_and_attrs["version"]


def test_extract_classmethod_decorator() -> None:
    source = """\
class Service:
    @classmethod
    def from_name(cls, name: str) -> "Service":
        return cls()
"""
    extractor = _make()
    results = extractor.extract("test.py", source)
    names_and_attrs = {name: attrs for name, attrs in results}
    assert "from_name" in names_and_attrs
    assert "classmethod" in names_and_attrs["from_name"]


def test_extract_async_def() -> None:
    source = """\
class Service:
    async def get_greeting_async(self) -> str:
        return "hello"
"""
    extractor = _make()
    results = extractor.extract("test.py", source)
    names_and_attrs = {name: attrs for name, attrs in results}
    assert "get_greeting_async" in names_and_attrs
    assert "async" in names_and_attrs["get_greeting_async"]


def test_extract_abc_class() -> None:
    source = """\
from abc import ABC

class IAnimal(ABC):
    pass
"""
    extractor = _make()
    results = extractor.extract("test.py", source)
    names_and_attrs = {name: attrs for name, attrs in results}
    assert "IAnimal" in names_and_attrs
    assert "ABC" in names_and_attrs["IAnimal"]


def test_extract_empty_source_returns_empty() -> None:
    extractor = _make()
    results = extractor.extract("test.py", "")
    assert results == []


def test_extract_source_with_no_decorators_returns_empty() -> None:
    source = """\
class Animal:
    def speak(self) -> str:
        return "..."

    def name(self) -> str:
        return "Animal"
"""
    extractor = _make()
    results = extractor.extract("test.py", source)
    assert results == []


def test_extract_combined_decorators_static_and_async() -> None:
    source = """\
class Service:
    @staticmethod
    async def fetch() -> str:
        return "ok"
"""
    extractor = _make()
    results = extractor.extract("test.py", source)
    names_and_attrs = {name: attrs for name, attrs in results}
    assert "fetch" in names_and_attrs
    attrs = names_and_attrs["fetch"]
    assert "staticmethod" in attrs
    assert "async" in attrs


def test_extract_nested_class_methods() -> None:
    """Methods inside nested classes should return the simple method name."""
    source = """\
class Outer:
    class Inner:
        @classmethod
        def create(cls):
            pass
"""
    extractor = _make()
    results = extractor.extract("test.py", source)
    names_and_attrs = {name: attrs for name, attrs in results}
    assert "create" in names_and_attrs
    assert "classmethod" in names_and_attrs["create"]


def test_python_plugin_create_attribute_extractor_returns_instance() -> None:
    from synapse.plugin.python import PythonPlugin
    plugin = PythonPlugin()
    extractor = plugin.create_attribute_extractor()
    assert isinstance(extractor, PythonAttributeExtractor)


def test_extract_multiple_decorators() -> None:
    """All decorator names on the same function should be returned."""
    source = """\
import functools

class Service:
    @classmethod
    @functools.cache
    def cached_name(cls) -> str:
        return "cached"
"""
    extractor = _make()
    results = extractor.extract("test.py", source)
    names_and_attrs = {name: attrs for name, attrs in results}
    assert "cached_name" in names_and_attrs
    assert "classmethod" in names_and_attrs["cached_name"]


def test_extract_abcmeta_class() -> None:
    """Classes using ABCMeta as metaclass should also get ABC marker."""
    source = """\
from abc import ABCMeta

class IFoo(metaclass=ABCMeta):
    pass
"""
    extractor = _make()
    results = extractor.extract("test.py", source)
    names_and_attrs = {name: attrs for name, attrs in results}
    assert "IFoo" in names_and_attrs
    assert "ABC" in names_and_attrs["IFoo"]


def test_extract_protocol_class() -> None:
    """Classes inheriting from Protocol should get 'Protocol' marker."""
    source = """\
from typing import Protocol

class Drawable(Protocol):
    def draw(self) -> None: ...
"""
    extractor = _make()
    results = extractor.extract("test.py", source)
    names_and_attrs = {name: attrs for name, attrs in results}
    assert "Drawable" in names_and_attrs
    assert "Protocol" in names_and_attrs["Drawable"]


def test_extract_runtime_checkable_protocol() -> None:
    """Protocol with @runtime_checkable decorator should get both markers."""
    source = """\
from typing import Protocol, runtime_checkable

@runtime_checkable
class Comparable(Protocol):
    def __lt__(self, other) -> bool: ...
"""
    extractor = _make()
    results = extractor.extract("test.py", source)
    names_and_attrs = {name: attrs for name, attrs in results}
    assert "Comparable" in names_and_attrs
    assert "Protocol" in names_and_attrs["Comparable"]
    assert "runtime_checkable" in names_and_attrs["Comparable"]
