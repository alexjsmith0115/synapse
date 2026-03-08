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
    callee_names = [callee for _, callee, *_ in results]
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
    callee_names = [callee for _, callee, *_ in results]
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
    assert any(caller == "MyNs.MyClass.Caller" for caller, *_ in results)


def test_returns_empty_for_empty_source(extractor):
    assert extractor.extract("/proj/Empty.cs", "", {}) == []


def test_no_duplicate_entries_for_same_call(extractor):
    """A call site captured by both query patterns on the same line must not produce duplicates."""
    source = """\
namespace MyNs {
    class MyClass {
        public void M() {
            var x = Foo() ?? Foo();
        }
    }
}
"""
    symbol_map = {("/proj/Foo.cs", 2): "MyNs.MyClass.M"}
    results = extractor.extract("/proj/Foo.cs", source, symbol_map)
    foo_calls = [(c, n, l, col) for c, n, l, col in results if n == "Foo"]
    # Two Foo calls at different columns are distinct — no (line, col) duplicates
    positions = [(l, col) for _, _, l, col in foo_calls]
    assert len(positions) == len(set(positions)), "Duplicate (line, col) entries found"


def test_skips_calls_with_no_enclosing_method(extractor):
    """Call sites that have no enclosing method in symbol_map must be silently dropped."""
    source = """\
namespace MyNs {
    class MyClass {
        private int _x = Compute();
        public void Run() {}
    }
}
"""
    # Only Run() is in the symbol_map; Compute() is at class scope (line 2) before Run() (line 3)
    symbol_map = {("/proj/Foo.cs", 3): "MyNs.MyClass.Run"}
    results = extractor.extract("/proj/Foo.cs", source, symbol_map)
    callee_names = [callee for _, callee, *_ in results]
    assert "Compute" not in callee_names
