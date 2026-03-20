import pytest
from synapse.indexer.python.python_import_extractor import PythonImportExtractor


@pytest.fixture()
def extractor() -> PythonImportExtractor:
    return PythonImportExtractor()


def test_from_import_single(extractor: PythonImportExtractor) -> None:
    source = "from synapsepytest.animals import Dog"
    result = extractor.extract("test.py", source)
    assert result == [("synapsepytest.animals", "Dog")]


def test_from_import_multiple(extractor: PythonImportExtractor) -> None:
    source = "from synapsepytest.animals import Dog, Cat"
    result = extractor.extract("test.py", source)
    assert ("synapsepytest.animals", "Dog") in result
    assert ("synapsepytest.animals", "Cat") in result
    assert len(result) == 2


def test_bare_import(extractor: PythonImportExtractor) -> None:
    source = "import synapsepytest.animals"
    result = extractor.extract("test.py", source)
    assert result == [("synapsepytest.animals", None)]


def test_star_import_skipped(extractor: PythonImportExtractor) -> None:
    source = "from synapsepytest.animals import *"
    result = extractor.extract("test.py", source)
    assert result == []


def test_relative_import_single_dot() -> None:
    extractor = PythonImportExtractor(source_root="tests/fixtures/SynapsePyTest")
    source = "from . import animals"
    result = extractor.extract("tests/fixtures/SynapsePyTest/synapsepytest/services.py", source)
    assert result == [("synapsepytest", "animals")]


def test_relative_import_double_dot() -> None:
    # `from ..util import helper` in pkg/sub/mod.py resolves to pkg.util as module
    extractor = PythonImportExtractor(source_root="")
    source = "from ..util import helper"
    result = extractor.extract("pkg/sub/mod.py", source)
    assert result == [("pkg.util", "helper")]


def test_empty_source(extractor: PythonImportExtractor) -> None:
    result = extractor.extract("test.py", "")
    assert result == []


def test_duplicate_imports_deduplicated(extractor: PythonImportExtractor) -> None:
    source = "from mymod import Foo\nfrom mymod import Foo"
    result = extractor.extract("test.py", source)
    assert result.count(("mymod", "Foo")) == 1
