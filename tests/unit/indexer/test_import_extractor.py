import pytest
from synapse.indexer.import_extractor import CSharpImportExtractor


@pytest.fixture()
def extractor() -> CSharpImportExtractor:
    return CSharpImportExtractor()


def test_extract_simple_using(extractor: CSharpImportExtractor) -> None:
    source = "using System.Collections.Generic;\nclass Foo {}"
    result = extractor.extract("/proj/Foo.cs", source)
    assert "System.Collections.Generic" in result


def test_extract_multiple_usings(extractor: CSharpImportExtractor) -> None:
    source = "using System;\nusing System.IO;\nclass Foo {}"
    result = extractor.extract("/proj/Foo.cs", source)
    assert "System" in result
    assert "System.IO" in result


def test_extract_ignores_static_using(extractor: CSharpImportExtractor) -> None:
    source = "using static System.Math;\nclass Foo {}"
    result = extractor.extract("/proj/Foo.cs", source)
    assert result == []


def test_extract_empty_file(extractor: CSharpImportExtractor) -> None:
    assert extractor.extract("/proj/Foo.cs", "") == []


def test_extract_no_duplicates(extractor: CSharpImportExtractor) -> None:
    source = "using System;\nusing System;\nclass Foo {}"
    result = extractor.extract("/proj/Foo.cs", source)
    assert result.count("System") == 1
