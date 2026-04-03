import pytest
import tree_sitter_c_sharp
from tree_sitter import Language, Parser
from synapps.indexer.csharp.csharp_call_extractor import CSharpCallExtractor

_lang = Language(tree_sitter_c_sharp.language())
_parser = Parser(_lang)


def _parse(source: str):
    return _parser.parse(bytes(source, "utf-8"))


@pytest.fixture
def extractor():
    return CSharpCallExtractor()


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
    results = extractor.extract("/proj/Foo.cs", _parse(source), symbol_map)
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
    results = extractor.extract("/proj/Foo.cs", _parse(source), symbol_map)
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
    results = extractor.extract("/proj/Foo.cs", _parse(source), symbol_map)
    assert any(caller == "MyNs.MyClass.Caller" for caller, *_ in results)


def test_returns_empty_for_empty_source(extractor):
    assert extractor.extract("/proj/Empty.cs", _parse(""), {}) == []


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
    results = extractor.extract("/proj/Foo.cs", _parse(source), symbol_map)
    foo_calls = [(c, n, l, col) for c, n, l, col in results if n == "Foo"]
    # Two Foo calls at different columns are distinct — no (line, col) duplicates
    positions = [(l, col) for _, _, l, col in foo_calls]
    assert len(positions) == len(set(positions)), "Duplicate (line, col) entries found"


def test_extracts_generic_method_call(extractor):
    """Generic invocations like Method<T>() and _svc.Method<T>() must be captured."""
    source = """\
namespace MyNs {
    class MyClass {
        public void Run() {
            Parse<string>();
            _service.Execute<int>();
            _service.Map<int, string>();
        }
    }
}
"""
    symbol_map = {("/proj/Foo.cs", 2): "MyNs.MyClass.Run"}
    results = extractor.extract("/proj/Foo.cs", _parse(source), symbol_map)
    callee_names = [callee for _, callee, *_ in results]
    assert "Parse" in callee_names, "bare generic call not captured"
    assert "Execute" in callee_names, "member-access generic call not captured"
    assert "Map" in callee_names, "multi-type-arg generic call not captured"


def test_extracts_generic_object_creation(extractor):
    """new List<string>() must be captured via generic_name in object_creation_expression."""
    source = """\
namespace MyNs {
    class MyClass {
        public void Run() {
            var x = new List<string>();
        }
    }
}
"""
    symbol_map = {("/proj/Foo.cs", 2): "MyNs.MyClass.Run"}
    results = extractor.extract("/proj/Foo.cs", _parse(source), symbol_map)
    callee_names = [callee for _, callee, *_ in results]
    assert "List" in callee_names, "generic object creation not captured"


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
    results = extractor.extract("/proj/Foo.cs", _parse(source), symbol_map)
    callee_names = [callee for _, callee, *_ in results]
    assert "Compute" not in callee_names


def test_extracts_null_conditional_call(extractor):
    """obj?.Method() must produce a CALLS edge for the method name."""
    source = """\
namespace MyNs {
    class MyClass {
        public void Caller() {
            _service?.Execute();
        }
    }
}
"""
    symbol_map = {("/proj/Foo.cs", 2): "MyNs.MyClass.Caller"}
    results = extractor.extract("/proj/Foo.cs", _parse(source), symbol_map)
    callee_names = [callee for _, callee, *_ in results]
    assert "Execute" in callee_names


def test_extracts_chained_null_conditional(extractor):
    """obj?.Method1()?.Method2() must produce CALLS edges for both method names."""
    source = """\
namespace MyNs {
    class MyClass {
        public void Caller() {
            obj?.Method1()?.Method2();
        }
    }
}
"""
    symbol_map = {("/proj/Foo.cs", 2): "MyNs.MyClass.Caller"}
    results = extractor.extract("/proj/Foo.cs", _parse(source), symbol_map)
    callee_names = [callee for _, callee, *_ in results]
    assert "Method1" in callee_names
    assert "Method2" in callee_names


def test_extracts_null_conditional_generic(extractor):
    """obj?.Method<T>() must produce a CALLS edge for the generic method name."""
    source = """\
namespace MyNs {
    class MyClass {
        public void Caller() {
            _svc?.Process<string>();
        }
    }
}
"""
    symbol_map = {("/proj/Foo.cs", 2): "MyNs.MyClass.Caller"}
    results = extractor.extract("/proj/Foo.cs", _parse(source), symbol_map)
    callee_names = [callee for _, callee, *_ in results]
    assert "Process" in callee_names


def test_extracts_null_conditional_in_null_coalescing(extractor):
    """obj?.Method() ?? fallback must still produce a CALLS edge for the method name."""
    source = """\
namespace MyNs {
    class MyClass {
        public void Caller() {
            var result = _svc?.Execute() ?? "default";
        }
    }
}
"""
    symbol_map = {("/proj/Foo.cs", 2): "MyNs.MyClass.Caller"}
    results = extractor.extract("/proj/Foo.cs", _parse(source), symbol_map)
    callee_names = [callee for _, callee, *_ in results]
    assert "Execute" in callee_names


def test_does_not_extract_null_conditional_indexer(extractor):
    """items?[0] must NOT produce any callee (element_binding_expression, not member_binding_expression)."""
    source = """\
namespace MyNs {
    class MyClass {
        public void Caller() {
            var item = items?[0];
        }
    }
}
"""
    symbol_map = {("/proj/Foo.cs", 2): "MyNs.MyClass.Caller"}
    results = extractor.extract("/proj/Foo.cs", _parse(source), symbol_map)
    assert len(results) == 0
