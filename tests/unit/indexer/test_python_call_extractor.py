import pytest
from synapse.indexer.python.python_call_extractor import PythonCallExtractor


@pytest.fixture
def extractor():
    return PythonCallExtractor()


@pytest.fixture
def module_extractor():
    return PythonCallExtractor(module_name_resolver=lambda fp: "mypackage.mymodule")


# ---------------------------------------------------------------------------
# Basic function-body calls
# ---------------------------------------------------------------------------


def test_extracts_function_body_call(extractor):
    source = """\
def helper():
    pass

def caller():
    helper()
"""
    symbol_map = {
        ("/proj/foo.py", 0): "mypackage.helper",
        ("/proj/foo.py", 3): "mypackage.caller",
    }
    results = extractor.extract("/proj/foo.py", source, symbol_map)
    callees = [callee for _, callee, *_ in results]
    assert "helper" in callees


def test_caller_full_name_is_set(extractor):
    source = """\
def caller():
    helper()
"""
    symbol_map = {("/proj/foo.py", 0): "mypackage.caller"}
    results = extractor.extract("/proj/foo.py", source, symbol_map)
    assert any(caller == "mypackage.caller" for caller, *_ in results)


def test_extracts_method_call_self(extractor):
    source = """\
class MyClass:
    def caller(self):
        self.other_method()

    def other_method(self):
        pass
"""
    symbol_map = {
        ("/proj/foo.py", 1): "mypackage.MyClass.caller",
        ("/proj/foo.py", 4): "mypackage.MyClass.other_method",
    }
    results = extractor.extract("/proj/foo.py", source, symbol_map)
    callees = [callee for _, callee, *_ in results]
    assert "other_method" in callees


def test_attribute_call_callee_simple_name(extractor):
    source = """\
def runner(obj):
    obj.do_something()
"""
    symbol_map = {("/proj/foo.py", 0): "mypackage.runner"}
    results = extractor.extract("/proj/foo.py", source, symbol_map)
    callees = [callee for _, callee, *_ in results]
    assert "do_something" in callees


# ---------------------------------------------------------------------------
# Class-scope skipping
# ---------------------------------------------------------------------------


def test_skips_class_scope(extractor):
    source = """\
def some_func():
    return 42

class MyClass:
    field = some_func()

    def run(self):
        pass
"""
    symbol_map = {
        ("/proj/foo.py", 0): "mypackage.some_func",
        ("/proj/foo.py", 6): "mypackage.MyClass.run",
    }
    results = extractor.extract("/proj/foo.py", source, symbol_map)
    callees = [callee for _, callee, *_ in results]
    assert "some_func" not in callees


# ---------------------------------------------------------------------------
# Module-scope calls
# ---------------------------------------------------------------------------


def test_module_scope_caller_full_name(module_extractor):
    source = """\
def get_value():
    return 42

RESULT = get_value()
"""
    symbol_map = {("/proj/foo.py", 0): "mypackage.mymodule.get_value"}
    results = module_extractor.extract("/proj/foo.py", source, symbol_map)
    callers = [caller for caller, *_ in results]
    assert "mypackage.mymodule" in callers


def test_module_scope_skipped_without_resolver(extractor):
    source = """\
def get_value():
    return 42

RESULT = get_value()
"""
    symbol_map = {("/proj/foo.py", 0): "mypackage.get_value"}
    results = extractor.extract("/proj/foo.py", source, symbol_map)
    # Without a resolver, module-scope calls are skipped entirely
    callers = [caller for caller, *_ in results]
    assert "mypackage.mymodule" not in callers


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_returns_empty_for_empty_source(extractor):
    assert extractor.extract("/proj/foo.py", "", {}) == []


def test_super_init(extractor):
    source = """\
class Child:
    def __init__(self):
        super().__init__()
"""
    symbol_map = {("/proj/foo.py", 1): "mypackage.Child.__init__"}
    results = extractor.extract("/proj/foo.py", source, symbol_map)
    callees = [callee for _, callee, *_ in results]
    # super().__init__() — tree-sitter sees `super` call and `__init__` attribute call
    assert "__init__" in callees or "super" in callees


def test_constructor_call(extractor):
    source = """\
def factory():
    return MyClass()
"""
    symbol_map = {("/proj/foo.py", 0): "mypackage.factory"}
    results = extractor.extract("/proj/foo.py", source, symbol_map)
    callees = [callee for _, callee, *_ in results]
    assert "MyClass" in callees


def test_deduplicates_identical_entries(extractor):
    source = """\
def caller():
    foo()
    foo()
"""
    symbol_map = {("/proj/foo.py", 0): "mypackage.caller"}
    results = extractor.extract("/proj/foo.py", source, symbol_map)
    # Both calls are at different lines/cols, so they are NOT duplicates
    # But same (caller, callee, line, col) must not appear twice
    seen = set()
    for entry in results:
        assert entry not in seen, f"Duplicate entry: {entry}"
        seen.add(entry)


def test_call_line_is_1indexed(extractor):
    source = """\
def caller():
    helper()
"""
    symbol_map = {("/proj/foo.py", 0): "mypackage.caller"}
    results = extractor.extract("/proj/foo.py", source, symbol_map)
    lines = [line for _, _, line, _ in results]
    # helper() is on line 2 (1-indexed)
    assert 2 in lines


# ---------------------------------------------------------------------------
# _sites_seen counter
# ---------------------------------------------------------------------------


def test_sites_seen_counts_function_scope_calls(extractor):
    # 3 methods each making 1 call + 1 class-body field assignment call (skipped)
    source = """\
class MyClass:
    field = some_func()

    def method_a(self):
        foo()

    def method_b(self):
        bar()

    def method_c(self):
        baz()
"""
    symbol_map = {
        ("/proj/foo.py", 3): "pkg.MyClass.method_a",
        ("/proj/foo.py", 6): "pkg.MyClass.method_b",
        ("/proj/foo.py", 9): "pkg.MyClass.method_c",
    }
    extractor.extract("/proj/foo.py", source, symbol_map)
    assert extractor._sites_seen == 3


def test_sites_seen_counts_module_scope_calls(module_extractor):
    source = """\
first_call()
second_call()
"""
    symbol_map = {}
    module_extractor.extract("/proj/foo.py", source, symbol_map)
    assert module_extractor._sites_seen == 2


def test_sites_seen_zero_for_empty_source(extractor):
    extractor.extract("/proj/foo.py", "", {})
    assert extractor._sites_seen == 0


def test_sites_seen_resets_per_extract_call(extractor):
    source_three = """\
def caller():
    a()
    b()
    c()
"""
    source_one = """\
def caller():
    x()
"""
    symbol_map_three = {("/proj/foo.py", 0): "pkg.caller"}
    symbol_map_one = {("/proj/bar.py", 0): "pkg.caller"}

    extractor.extract("/proj/foo.py", source_three, symbol_map_three)
    assert extractor._sites_seen == 3

    extractor.extract("/proj/bar.py", source_one, symbol_map_one)
    # Must reflect only the second call, not cumulative
    assert extractor._sites_seen == 1
