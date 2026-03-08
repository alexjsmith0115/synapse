import pytest
from synapse.indexer.call_extractor import TreeSitterCallExtractor


@pytest.fixture
def extractor():
    return TreeSitterCallExtractor()


def test_extracts_simple_method_call(extractor):
    source = """\
namespace MyNs {
    class MyClass {
        public void Caller() {
            Helper();
        }
        public void Helper() {}
    }
}
"""
    # symbol_map keys: (abs_file_path, 0-indexed line) -> full_name
    symbol_map = {
        ("/proj/Foo.cs", 2): "MyNs.MyClass.Caller",   # line 3 in source = index 2
        ("/proj/Foo.cs", 5): "MyNs.MyClass.Helper",   # line 6 in source = index 5
    }
    results = extractor.extract("/proj/Foo.cs", source, symbol_map)
    callee_names = [callee for _, callee, _ in results]
    assert "Helper" in callee_names


def test_extracts_member_access_call(extractor):
    source = """\
namespace MyNs {
    class MyClass {
        public void Run() {
            _service.Execute();
        }
    }
}
"""
    symbol_map = {("/proj/Foo.cs", 2): "MyNs.MyClass.Run"}
    results = extractor.extract("/proj/Foo.cs", source, symbol_map)
    callee_names = [callee for _, callee, _ in results]
    assert "Execute" in callee_names


def test_caller_full_name_is_set(extractor):
    source = """\
namespace MyNs {
    class MyClass {
        public void Caller() {
            Helper();
        }
    }
}
"""
    symbol_map = {("/proj/Foo.cs", 2): "MyNs.MyClass.Caller"}
    results = extractor.extract("/proj/Foo.cs", source, symbol_map)
    assert any(caller == "MyNs.MyClass.Caller" for caller, _, _ in results)


def test_returns_empty_for_empty_source(extractor):
    assert extractor.extract("/proj/Empty.cs", "", {}) == []


def test_no_duplicates(extractor):
    source = """\
namespace MyNs {
    class MyClass {
        public void M() {
            Foo();
            Foo();
        }
    }
}
"""
    symbol_map = {("/proj/Foo.cs", 2): "MyNs.MyClass.M"}
    results = extractor.extract("/proj/Foo.cs", source, symbol_map)
    foo_calls = [(c, n, l) for c, n, l in results if n == "Foo"]
    # Two calls on different lines => two entries, but same (caller, callee, line) deduplicated
    callee_lines = [l for _, n, l in foo_calls if n == "Foo"]
    assert len(callee_lines) == len(set(callee_lines))
