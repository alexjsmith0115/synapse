import pytest
from synapse.indexer.typescript.typescript_call_extractor import TypeScriptCallExtractor


@pytest.fixture
def extractor():
    return TypeScriptCallExtractor()


@pytest.fixture
def module_extractor():
    return TypeScriptCallExtractor(module_name_resolver=lambda fp: "mypackage.mymodule")


# ---------------------------------------------------------------------------
# Basic call extraction
# ---------------------------------------------------------------------------


def test_extracts_bare_function_call(extractor):
    source = """\
function caller() {
    helper();
}
"""
    symbol_map = {("/proj/foo.ts", 0): "mypackage.caller"}
    results = extractor.extract("/proj/foo.ts", source, symbol_map)
    callees = [callee for _, callee, *_ in results]
    assert "helper" in callees


def test_caller_full_name_is_set(extractor):
    source = """\
function caller() {
    helper();
}
"""
    symbol_map = {("/proj/foo.ts", 0): "mypackage.caller"}
    results = extractor.extract("/proj/foo.ts", source, symbol_map)
    assert any(caller == "mypackage.caller" for caller, *_ in results)


def test_extracts_method_call(extractor):
    source = """\
class MyClass {
    caller() {
        this.method();
    }
    method() {}
}
"""
    symbol_map = {
        ("/proj/foo.ts", 1): "mypackage.MyClass.caller",
        ("/proj/foo.ts", 4): "mypackage.MyClass.method",
    }
    results = extractor.extract("/proj/foo.ts", source, symbol_map)
    callees = [callee for _, callee, *_ in results]
    assert "method" in callees


def test_extracts_new_expression(extractor):
    source = """\
function factory() {
    return new Foo();
}
"""
    symbol_map = {("/proj/foo.ts", 0): "mypackage.factory"}
    results = extractor.extract("/proj/foo.ts", source, symbol_map)
    callees = [callee for _, callee, *_ in results]
    assert "Foo" in callees


# ---------------------------------------------------------------------------
# Scope classification
# ---------------------------------------------------------------------------


def test_scope_function(extractor):
    """Calls inside function_declaration are attributed to the enclosing function."""
    source = """\
function caller() {
    helper();
}
"""
    symbol_map = {("/proj/foo.ts", 0): "mypackage.caller"}
    results = extractor.extract("/proj/foo.ts", source, symbol_map)
    assert len(results) == 1
    caller, callee, line, col = results[0]
    assert caller == "mypackage.caller"
    assert callee == "helper"


def test_scope_arrow_function(extractor):
    """Calls inside arrow_function are attributed to the enclosing arrow function scope."""
    source = """\
const run = () => {
    helper();
};
"""
    symbol_map = {("/proj/foo.ts", 0): "mypackage.run"}
    results = extractor.extract("/proj/foo.ts", source, symbol_map)
    callees = [callee for _, callee, *_ in results]
    assert "helper" in callees


def test_scope_class_body_skipped(extractor):
    """Calls in public_field_definition / field_definition are skipped."""
    source = """\
function setup() { return 42; }

class MyClass {
    field = setup();

    run() {}
}
"""
    symbol_map = {
        ("/proj/foo.ts", 0): "mypackage.setup",
        ("/proj/foo.ts", 5): "mypackage.MyClass.run",
    }
    results = extractor.extract("/proj/foo.ts", source, symbol_map)
    callees = [callee for _, callee, *_ in results]
    assert "setup" not in callees


def test_scope_module(module_extractor):
    """Module-scope calls use the module_name_resolver callback."""
    source = """\
function getValue() { return 42; }

const RESULT = getValue();
"""
    symbol_map = {("/proj/foo.ts", 0): "mypackage.getValue"}
    results = module_extractor.extract("/proj/foo.ts", source, symbol_map)
    callers = [caller for caller, *_ in results]
    assert "mypackage.mymodule" in callers


def test_scope_module_no_resolver(extractor):
    """Without a resolver, module-scope calls are skipped."""
    source = """\
function getValue() { return 42; }

const RESULT = getValue();
"""
    symbol_map = {("/proj/foo.ts", 0): "mypackage.getValue"}
    results = extractor.extract("/proj/foo.ts", source, symbol_map)
    callers = [caller for caller, *_ in results]
    assert not callers


# ---------------------------------------------------------------------------
# File type / parser selection
# ---------------------------------------------------------------------------


def test_tsx_file_uses_tsx_parser(extractor):
    """A .tsx file with JSX syntax parses correctly."""
    source = """\
function App() {
    helper();
    return <div />;
}
"""
    symbol_map = {("/proj/app.tsx", 0): "mypackage.App"}
    results = extractor.extract("/proj/app.tsx", source, symbol_map)
    callees = [callee for _, callee, *_ in results]
    assert "helper" in callees


def test_jsx_file_uses_tsx_parser(extractor):
    """A .jsx file parses correctly using the tsx parser."""
    source = """\
function App() {
    helper();
    return <div />;
}
"""
    symbol_map = {("/proj/app.jsx", 0): "mypackage.App"}
    results = extractor.extract("/proj/app.jsx", source, symbol_map)
    callees = [callee for _, callee, *_ in results]
    assert "helper" in callees


def test_js_file_uses_ts_parser(extractor):
    """A .js file uses the typescript parser (not tsx)."""
    source = """\
function caller() {
    helper();
}
"""
    symbol_map = {("/proj/foo.js", 0): "mypackage.caller"}
    results = extractor.extract("/proj/foo.js", source, symbol_map)
    callees = [callee for _, callee, *_ in results]
    assert "helper" in callees


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_source_returns_empty(extractor):
    assert extractor.extract("/proj/foo.ts", "", {}) == []


def test_whitespace_source_returns_empty(extractor):
    assert extractor.extract("/proj/foo.ts", "   \n  ", {}) == []


def test_deduplicates_same_call(extractor):
    """Same (caller, callee, line, col) entry must not appear twice."""
    source = """\
function caller() {
    foo();
    foo();
}
"""
    symbol_map = {("/proj/foo.ts", 0): "mypackage.caller"}
    results = extractor.extract("/proj/foo.ts", source, symbol_map)
    seen: set = set()
    for entry in results:
        assert entry not in seen, f"Duplicate entry: {entry}"
        seen.add(entry)


def test_call_line_is_1indexed(extractor):
    source = """\
function caller() {
    helper();
}
"""
    symbol_map = {("/proj/foo.ts", 0): "mypackage.caller"}
    results = extractor.extract("/proj/foo.ts", source, symbol_map)
    lines = [line for _, _, line, _ in results]
    # helper() is on line 2 (1-indexed)
    assert 2 in lines


# ---------------------------------------------------------------------------
# _sites_seen counter
# ---------------------------------------------------------------------------


def test_sites_seen_counts_function_scope_calls(extractor):
    source = """\
class MyClass {
    field = setup();

    methodA() { foo(); }
    methodB() { bar(); }
    methodC() { baz(); }
}
"""
    symbol_map = {
        ("/proj/foo.ts", 3): "pkg.MyClass.methodA",
        ("/proj/foo.ts", 4): "pkg.MyClass.methodB",
        ("/proj/foo.ts", 5): "pkg.MyClass.methodC",
    }
    extractor.extract("/proj/foo.ts", source, symbol_map)
    assert extractor._sites_seen == 3


def test_sites_seen_counts_module_scope_calls(module_extractor):
    source = """\
firstCall();
secondCall();
"""
    symbol_map = {}
    module_extractor.extract("/proj/foo.ts", source, symbol_map)
    assert module_extractor._sites_seen == 2


def test_sites_seen_zero_for_empty_source(extractor):
    extractor.extract("/proj/foo.ts", "", {})
    assert extractor._sites_seen == 0


def test_sites_seen_resets_per_extract_call(extractor):
    source_three = """\
function caller() {
    a();
    b();
    c();
}
"""
    source_one = """\
function caller() {
    x();
}
"""
    symbol_map_three = {("/proj/foo.ts", 0): "pkg.caller"}
    symbol_map_one = {("/proj/bar.ts", 0): "pkg.caller"}

    extractor.extract("/proj/foo.ts", source_three, symbol_map_three)
    assert extractor._sites_seen == 3

    extractor.extract("/proj/bar.ts", source_one, symbol_map_one)
    assert extractor._sites_seen == 1
