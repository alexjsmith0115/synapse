import pytest
from synapse.indexer.base_type_extractor import CSharpBaseTypeExtractor


@pytest.fixture()
def extractor() -> CSharpBaseTypeExtractor:
    return CSharpBaseTypeExtractor()


def test_extract_class_with_base_class(extractor: CSharpBaseTypeExtractor) -> None:
    source = "class Dog : Animal {}"
    result = extractor.extract("/proj/Dog.cs", source)
    assert ("Dog", "Animal", True) in result


def test_extract_class_implementing_interface(extractor: CSharpBaseTypeExtractor) -> None:
    source = "class UserService : IUserService {}"
    result = extractor.extract("/proj/UserService.cs", source)
    assert ("UserService", "IUserService", True) in result


def test_extract_class_with_multiple_bases_marks_first(extractor: CSharpBaseTypeExtractor) -> None:
    source = "class Repo : BaseRepo, IRepo, IDisposable {}"
    result = extractor.extract("/proj/Repo.cs", source)
    first_flags = {base: is_first for _, base, is_first in result}
    assert first_flags["BaseRepo"] is True
    assert first_flags["IRepo"] is False
    assert first_flags["IDisposable"] is False


def test_extract_interface_inheriting_interface(extractor: CSharpBaseTypeExtractor) -> None:
    source = "interface IService : IDisposable {}"
    result = extractor.extract("/proj/IService.cs", source)
    assert ("IService", "IDisposable", True) in result


def test_extract_no_bases(extractor: CSharpBaseTypeExtractor) -> None:
    source = "class Foo {}"
    result = extractor.extract("/proj/Foo.cs", source)
    assert result == []


def test_extract_generic_base_class(extractor: CSharpBaseTypeExtractor) -> None:
    source = "class MyList : List<string> {}"
    result = extractor.extract("/proj/MyList.cs", source)
    names = {base for _, base, _ in result}
    assert "List" in names


def test_extract_record_with_base(extractor: CSharpBaseTypeExtractor) -> None:
    source = "record Dog : Animal {}"
    result = extractor.extract("/proj/Dog.cs", source)
    assert ("Dog", "Animal", True) in result


def test_extract_empty_file(extractor: CSharpBaseTypeExtractor) -> None:
    assert extractor.extract("/proj/Foo.cs", "") == []
