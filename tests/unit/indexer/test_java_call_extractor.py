import pytest
import tree_sitter_java
from tree_sitter import Language, Parser
from synapps.indexer.java.java_call_extractor import JavaCallExtractor

_lang = Language(tree_sitter_java.language())
_parser = Parser(_lang)


def _parse(source: str):
    return _parser.parse(bytes(source, "utf-8"))


@pytest.fixture
def extractor():
    return JavaCallExtractor()


# ---------------------------------------------------------------------------
# Basic call extraction
# ---------------------------------------------------------------------------


def test_simple_method_call(extractor):
    source = """\
public class MyClass {
    public void caller() {
        obj.method();
    }
}
"""
    symbol_map = {("/proj/MyClass.java", 1): "com.example.MyClass.caller"}
    results = extractor.extract("/proj/MyClass.java", _parse(source), symbol_map)
    callees = [callee for _, callee, *_ in results]
    assert "method" in callees


def test_chained_method_call(extractor):
    source = """\
public class MyClass {
    public void caller() {
        obj.method().chain();
    }
}
"""
    symbol_map = {("/proj/MyClass.java", 1): "com.example.MyClass.caller"}
    results = extractor.extract("/proj/MyClass.java", _parse(source), symbol_map)
    callees = [callee for _, callee, *_ in results]
    assert "method" in callees
    assert "chain" in callees


def test_constructor_call(extractor):
    source = """\
public class MyClass {
    public void factory() {
        Foo f = new Foo();
    }
}
"""
    symbol_map = {("/proj/MyClass.java", 1): "com.example.MyClass.factory"}
    results = extractor.extract("/proj/MyClass.java", _parse(source), symbol_map)
    callees = [callee for _, callee, *_ in results]
    assert "Foo" in callees


def test_static_method_call(extractor):
    source = """\
public class MyClass {
    public void caller() {
        ClassName.staticMethod();
    }
}
"""
    symbol_map = {("/proj/MyClass.java", 1): "com.example.MyClass.caller"}
    results = extractor.extract("/proj/MyClass.java", _parse(source), symbol_map)
    callees = [callee for _, callee, *_ in results]
    assert "staticMethod" in callees


def test_function_call_within_method(extractor):
    source = """\
public class MyClass {
    public void caller() {
        baz();
    }
}
"""
    symbol_map = {("/proj/MyClass.java", 1): "com.example.MyClass.caller"}
    results = extractor.extract("/proj/MyClass.java", _parse(source), symbol_map)
    callees = [callee for _, callee, *_ in results]
    assert "baz" in callees


def test_caller_full_name_is_set(extractor):
    source = """\
public class MyClass {
    public void caller() {
        helper();
    }
}
"""
    symbol_map = {("/proj/MyClass.java", 1): "com.example.MyClass.caller"}
    results = extractor.extract("/proj/MyClass.java", _parse(source), symbol_map)
    assert any(caller == "com.example.MyClass.caller" for caller, *_ in results)


# ---------------------------------------------------------------------------
# No calls / empty source
# ---------------------------------------------------------------------------


def test_no_calls(extractor):
    source = """\
public class MyClass {
    private int count;
    private String name;
}
"""
    symbol_map = {}
    results = extractor.extract("/proj/MyClass.java", _parse(source), symbol_map)
    assert results == []


def test_empty_source(extractor):
    assert extractor.extract("/proj/MyClass.java", _parse(""), {}) == []


def test_whitespace_source(extractor):
    assert extractor.extract("/proj/MyClass.java", _parse("   \n  "), {}) == []


# ---------------------------------------------------------------------------
# Line indexing and deduplication
# ---------------------------------------------------------------------------


def test_call_line_is_1indexed(extractor):
    source = """\
public class MyClass {
    public void caller() {
        helper();
    }
}
"""
    symbol_map = {("/proj/MyClass.java", 1): "com.example.MyClass.caller"}
    results = extractor.extract("/proj/MyClass.java", _parse(source), symbol_map)
    lines = [line for _, _, line, *_ in results]
    # helper() is on line 3 (1-indexed)
    assert 3 in lines


def test_deduplicates_identical_entries(extractor):
    source = """\
public class MyClass {
    public void caller() {
        foo();
        foo();
    }
}
"""
    symbol_map = {("/proj/MyClass.java", 1): "com.example.MyClass.caller"}
    results = extractor.extract("/proj/MyClass.java", _parse(source), symbol_map)
    seen = set()
    for entry in results:
        assert entry not in seen, f"Duplicate entry: {entry}"
        seen.add(entry)


# ---------------------------------------------------------------------------
# _sites_seen counter
# ---------------------------------------------------------------------------


def test_sites_seen_counts_calls(extractor):
    source = """\
public class MyClass {
    public void methodA() { foo(); }
    public void methodB() { bar(); }
    public void methodC() { baz(); }
}
"""
    symbol_map = {
        ("/proj/MyClass.java", 1): "pkg.MyClass.methodA",
        ("/proj/MyClass.java", 2): "pkg.MyClass.methodB",
        ("/proj/MyClass.java", 3): "pkg.MyClass.methodC",
    }
    extractor.extract("/proj/MyClass.java", _parse(source), symbol_map)
    assert extractor._sites_seen == 3


def test_sites_seen_zero_for_empty_source(extractor):
    extractor.extract("/proj/MyClass.java", _parse(""), {})
    assert extractor._sites_seen == 0


def test_sites_seen_resets_per_extract_call(extractor):
    source_three = """\
public class A {
    public void caller() {
        a();
        b();
        c();
    }
}
"""
    source_one = """\
public class B {
    public void caller() {
        x();
    }
}
"""
    symbol_map_three = {("/proj/A.java", 1): "pkg.A.caller"}
    symbol_map_one = {("/proj/B.java", 1): "pkg.B.caller"}

    extractor.extract("/proj/A.java", _parse(source_three), symbol_map_three)
    assert extractor._sites_seen == 3

    extractor.extract("/proj/B.java", _parse(source_one), symbol_map_one)
    assert extractor._sites_seen == 1


# ---------------------------------------------------------------------------
# Scope detection — class-body field initializer calls must be skipped
# ---------------------------------------------------------------------------


def test_skips_field_initializer_call(extractor):
    """Regression: calls in field initializers (class body) must be skipped."""
    source = """\
public class MyClass {
    private List<String> items = Arrays.asList("a", "b");
    public void realMethod() {
        helper();
    }
}
"""
    symbol_map = {("/proj/MyClass.java", 2): "pkg.MyClass.realMethod"}
    results = extractor.extract("/proj/MyClass.java", _parse(source), symbol_map)
    callees = [callee for _, callee, *_ in results]
    assert "helper" in callees
    assert "asList" not in callees


def test_skips_static_field_initializer(extractor):
    """Regression: static field initializers are class-body scope."""
    source = """\
public class Config {
    private static final Logger LOG = LoggerFactory.getLogger(Config.class);
    public void run() {
        LOG.info("running");
    }
}
"""
    symbol_map = {("/proj/Config.java", 2): "pkg.Config.run"}
    results = extractor.extract("/proj/Config.java", _parse(source), symbol_map)
    callees = [callee for _, callee, *_ in results]
    assert "info" in callees
    assert "getLogger" not in callees


def test_includes_constructor_body_calls(extractor):
    """Calls inside constructors should be included."""
    source = """\
public class Service {
    public Service() {
        init();
    }
}
"""
    symbol_map = {("/proj/Service.java", 1): "pkg.Service.Service"}
    results = extractor.extract("/proj/Service.java", _parse(source), symbol_map)
    callees = [callee for _, callee, *_ in results]
    assert "init" in callees


def test_includes_lambda_body_calls(extractor):
    """Calls inside lambdas should be included (lambda is a method scope)."""
    source = """\
public class MyClass {
    public void run() {
        list.forEach(item -> process(item));
    }
}
"""
    symbol_map = {("/proj/MyClass.java", 1): "pkg.MyClass.run"}
    results = extractor.extract("/proj/MyClass.java", _parse(source), symbol_map)
    callees = [callee for _, callee, *_ in results]
    assert "forEach" in callees


# ---------------------------------------------------------------------------
# Control flow block coverage (if/for/try-catch/constructor)
# ---------------------------------------------------------------------------


def test_call_inside_if_block(extractor):
    """Calls inside if-blocks must be captured as part of the enclosing method."""
    source = """\
public class OrderService {
    private OrderRepository orderRepository;
    public void createOrder(Order order) {
        if (order.isValid()) {
            orderRepository.save(order);
        }
    }
}
"""
    symbol_map = {("/proj/OrderService.java", 2): "com.example.OrderService.createOrder"}
    results = extractor.extract("/proj/OrderService.java", _parse(source), symbol_map)
    callees = [callee for _, callee, *_ in results]
    assert "save" in callees
    callers = [caller for caller, *_ in results if _ and _[0] == "save"]
    # All save calls should be attributed to createOrder
    save_entries = [(caller, callee) for caller, callee, *_ in results if callee == "save"]
    assert all(caller == "com.example.OrderService.createOrder" for caller, _ in save_entries)


def test_call_inside_for_loop(extractor):
    """Calls inside for-loop bodies must be captured as part of the enclosing method."""
    source = """\
public class BatchProcessor {
    private ItemService service;
    public void processAll(List<Item> items) {
        for (Item item : items) {
            service.process(item);
        }
    }
}
"""
    symbol_map = {("/proj/BatchProcessor.java", 2): "com.example.BatchProcessor.processAll"}
    results = extractor.extract("/proj/BatchProcessor.java", _parse(source), symbol_map)
    callees = [callee for _, callee, *_ in results]
    assert "process" in callees


def test_call_inside_catch_block(extractor):
    """Calls inside try-body and catch-block must both be captured."""
    source = """\
public class SafeRunner {
    private Logger logger;
    public void run() {
        try {
            doWork();
        } catch (Exception e) {
            logger.error("failed", e);
        }
    }
}
"""
    symbol_map = {("/proj/SafeRunner.java", 2): "com.example.SafeRunner.run"}
    results = extractor.extract("/proj/SafeRunner.java", _parse(source), symbol_map)
    callees = [callee for _, callee, *_ in results]
    assert "doWork" in callees
    assert "error" in callees


def test_constructor_call_inside_method(extractor):
    """object_creation_expression (new Foo()) inside a method must be captured."""
    source = """\
public class Factory {
    public Widget create(String name) {
        return new Widget(name);
    }
}
"""
    symbol_map = {("/proj/Factory.java", 1): "com.example.Factory.create"}
    results = extractor.extract("/proj/Factory.java", _parse(source), symbol_map)
    callees = [callee for _, callee, *_ in results]
    assert "Widget" in callees


# ---------------------------------------------------------------------------
# Receiver variable name (5-tuple) tests
# ---------------------------------------------------------------------------


def test_receiver_name_captured_for_instance_call(extractor):
    """receiver.method() → 5th element is the receiver variable name."""
    source = """\
class OrderService {
    public void createOrder() {
        orderRepository.save(new Order());
    }
}
"""
    symbol_map = {("/proj/OrderService.java", 1): "com.example.OrderService.createOrder"}
    results = extractor.extract("/proj/OrderService.java", _parse(source), symbol_map)
    save_entries = [(caller, callee, line, col, receiver) for caller, callee, line, col, receiver in results if callee == "save"]
    assert len(save_entries) == 1
    assert save_entries[0][4] == "orderRepository"


def test_receiver_name_none_for_bare_call(extractor):
    """Bare method call (no receiver) → receiver_name is None."""
    source = """\
class OrderService {
    public void plain() {
        doSomething();
    }
}
"""
    symbol_map = {("/proj/OrderService.java", 1): "com.example.OrderService.plain"}
    results = extractor.extract("/proj/OrderService.java", _parse(source), symbol_map)
    assert len(results) == 1
    caller, callee, line, col, receiver = results[0]
    assert callee == "doSomething"
    assert receiver is None


def test_receiver_name_none_for_constructor_call(extractor):
    """new Foo() constructor call → receiver_name is None."""
    source = """\
class Factory {
    public Animal createAnimal() {
        return new Cat();
    }
}
"""
    symbol_map = {("/proj/Factory.java", 1): "com.example.Factory.createAnimal"}
    results = extractor.extract("/proj/Factory.java", _parse(source), symbol_map)
    cat_entries = [(caller, callee, line, col, receiver) for caller, callee, line, col, receiver in results if callee == "Cat"]
    assert len(cat_entries) == 1
    assert cat_entries[0][4] is None


def test_receiver_name_for_chained_call_is_none_or_not_identifier(extractor):
    """Chained a.b().c() → outermost call 'c' has a method_invocation object, not identifier → receiver_name is None."""
    source = """\
class MyClass {
    public void run() {
        foo.bar().baz();
    }
}
"""
    symbol_map = {("/proj/MyClass.java", 1): "com.example.MyClass.run"}
    results = extractor.extract("/proj/MyClass.java", _parse(source), symbol_map)
    baz_entries = [(caller, callee, line, col, receiver) for caller, callee, line, col, receiver in results if callee == "baz"]
    assert len(baz_entries) == 1
    # baz() receiver is the result of bar(), a method_invocation — not a plain identifier
    assert baz_entries[0][4] is None


def test_extract_returns_5_tuples(extractor):
    """All returned entries must be 5-tuples."""
    source = """\
class MyClass {
    public void caller() {
        obj.method();
        bare();
    }
}
"""
    symbol_map = {("/proj/MyClass.java", 1): "com.example.MyClass.caller"}
    results = extractor.extract("/proj/MyClass.java", _parse(source), symbol_map)
    assert len(results) > 0
    for entry in results:
        assert len(entry) == 5, f"Expected 5-tuple, got {len(entry)}-tuple: {entry}"


def test_caller_callee_line_col_unchanged(extractor):
    """Existing 4-element behavior (caller, callee, line, col) is preserved."""
    source = """\
class OrderService {
    public Animal createAnimal() {
        return orderRepository.save(new Cat());
    }
    public void plain() {
        doSomething();
    }
}
"""
    symbol_map = {("/proj/OrderService.java", 1): "com.example.OrderService.createAnimal"}
    results = extractor.extract("/proj/OrderService.java", _parse(source), symbol_map)
    for caller, callee, line, col, receiver in results:
        assert caller == "com.example.OrderService.createAnimal"
        assert isinstance(callee, str) and callee
        assert isinstance(line, int) and line >= 1
        assert isinstance(col, int) and col >= 0
