import pytest
from synapse.indexer.type_ref_extractor import TreeSitterTypeRefExtractor


@pytest.fixture
def extractor():
    return TreeSitterTypeRefExtractor()


def test_extracts_method_return_type(extractor):
    source = """\
namespace MyNs {
    class MyClass {
        public UserDto GetUser() {
            return null;
        }
    }
}
"""
    symbol_map = {("/proj/Foo.cs", 2): "MyNs.MyClass.GetUser"}
    results = extractor.extract("/proj/Foo.cs", source, symbol_map)
    assert any(r.ref_kind == "return_type" and r.type_name == "UserDto" for r in results)


def test_extracts_method_parameter_type(extractor):
    source = """\
namespace MyNs {
    class MyClass {
        public void Save(UserDto dto) {}
    }
}
"""
    symbol_map = {("/proj/Foo.cs", 2): "MyNs.MyClass.Save"}
    results = extractor.extract("/proj/Foo.cs", source, symbol_map)
    assert any(r.ref_kind == "parameter" and r.type_name == "UserDto" for r in results)


def test_extracts_property_type(extractor):
    source = """\
namespace MyNs {
    class MyClass {
        public UserDto User { get; set; }
    }
}
"""
    # Properties need a class-level symbol map entry
    symbol_map = {}
    results = extractor.extract("/proj/Foo.cs", source, symbol_map)
    assert any(r.ref_kind == "property_type" and r.type_name == "UserDto" for r in results)


def test_extracts_field_type(extractor):
    source = """\
namespace MyNs {
    class MyClass {
        private UserDto _user;
    }
}
"""
    symbol_map = {}
    results = extractor.extract("/proj/Foo.cs", source, symbol_map)
    assert any(r.ref_kind == "field_type" and r.type_name == "UserDto" for r in results)


def test_skips_primitive_types(extractor):
    source = """\
namespace MyNs {
    class MyClass {
        public int GetCount() { return 0; }
        private string _name;
    }
}
"""
    symbol_map = {("/proj/Foo.cs", 2): "MyNs.MyClass.GetCount"}
    results = extractor.extract("/proj/Foo.cs", source, symbol_map)
    type_names = [r.type_name for r in results]
    assert "int" not in type_names
    assert "string" not in type_names


def test_returns_empty_for_empty_source(extractor):
    assert extractor.extract("/proj/Empty.cs", "", {}) == []
