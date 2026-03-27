"""Unit tests for TypeScriptAttributeExtractor — META requirements."""
import tree_sitter_typescript
from tree_sitter import Language, Parser

from synapse.indexer.typescript.typescript_attribute_extractor import TypeScriptAttributeExtractor

_ts_lang = Language(tree_sitter_typescript.language_typescript())
_tsx_lang = Language(tree_sitter_typescript.language_tsx())
_ts_parser = Parser(_ts_lang)
_tsx_parser = Parser(_tsx_lang)
_TSX_EXTENSIONS = frozenset({".tsx", ".jsx"})


def _parse(source: str, file_path: str = "/tmp/test.ts"):
    uses_tsx = any(file_path.endswith(ext) for ext in _TSX_EXTENSIONS)
    parser = _tsx_parser if uses_tsx else _ts_parser
    return parser.parse(bytes(source, "utf-8"))


def _make() -> TypeScriptAttributeExtractor:
    return TypeScriptAttributeExtractor()


def test_extract_decorator() -> None:
    """META-01: @Component decorator on class produces Component marker."""
    source = """\
@Component
class AppComponent {
    title = "app";
}
"""
    extractor = _make()
    results = extractor.extract("test.ts", _parse(source, "test.ts"))
    names_and_attrs = {name: attrs for name, attrs in results}
    assert "AppComponent" in names_and_attrs
    assert "Component" in names_and_attrs["AppComponent"]


def test_extract_decorator_with_parens() -> None:
    """META-01: @Component() decorator (with parens) on class produces Component marker."""
    source = """\
@Component({
    selector: "app-root",
    template: "<h1>Hello</h1>"
})
class AppComponent {
    title = "app";
}
"""
    extractor = _make()
    results = extractor.extract("test.ts", _parse(source, "test.ts"))
    names_and_attrs = {name: attrs for name, attrs in results}
    assert "AppComponent" in names_and_attrs
    assert "Component" in names_and_attrs["AppComponent"]


def test_extract_decorator_on_method() -> None:
    """META-01: @Log decorator on method produces Log marker."""
    source = """\
class MyService {
    @Log
    myMethod() {
        return 42;
    }
}
"""
    extractor = _make()
    results = extractor.extract("test.ts", _parse(source, "test.ts"))
    names_and_attrs = {name: attrs for name, attrs in results}
    assert "myMethod" in names_and_attrs
    assert "Log" in names_and_attrs["myMethod"]


def test_extract_abstract_class() -> None:
    """META-02: abstract class produces abstract marker."""
    source = """\
abstract class Foo {
    doWork(): void {}
}
"""
    extractor = _make()
    results = extractor.extract("test.ts", _parse(source, "test.ts"))
    names_and_attrs = {name: attrs for name, attrs in results}
    assert "Foo" in names_and_attrs
    assert "abstract" in names_and_attrs["Foo"]


def test_extract_abstract_method() -> None:
    """META-02: abstract method inside abstract class produces abstract marker."""
    source = """\
abstract class Animal {
    abstract speak(): string;
}
"""
    extractor = _make()
    results = extractor.extract("test.ts", _parse(source, "test.ts"))
    names_and_attrs = {name: attrs for name, attrs in results}
    assert "speak" in names_and_attrs
    assert "abstract" in names_and_attrs["speak"]


def test_extract_static_method() -> None:
    """META-03: static method produces static marker."""
    source = """\
class Factory {
    static create(): Factory {
        return new Factory();
    }
}
"""
    extractor = _make()
    results = extractor.extract("test.ts", _parse(source, "test.ts"))
    names_and_attrs = {name: attrs for name, attrs in results}
    assert "create" in names_and_attrs
    assert "static" in names_and_attrs["create"]


def test_extract_static_field() -> None:
    """META-03: static field produces static marker."""
    source = """\
class Counter {
    static count: number = 0;
}
"""
    extractor = _make()
    results = extractor.extract("test.ts", _parse(source, "test.ts"))
    names_and_attrs = {name: attrs for name, attrs in results}
    assert "count" in names_and_attrs
    assert "static" in names_and_attrs["count"]


def test_extract_async_function() -> None:
    """META-04: top-level async function produces async marker."""
    source = """\
async function fetchData(): Promise<string> {
    return "data";
}
"""
    extractor = _make()
    results = extractor.extract("test.ts", _parse(source, "test.ts"))
    names_and_attrs = {name: attrs for name, attrs in results}
    assert "fetchData" in names_and_attrs
    assert "async" in names_and_attrs["fetchData"]


def test_extract_async_method() -> None:
    """META-04: async method produces async marker."""
    source = """\
class DataService {
    async getData(): Promise<string[]> {
        return [];
    }
}
"""
    extractor = _make()
    results = extractor.extract("test.ts", _parse(source, "test.ts"))
    names_and_attrs = {name: attrs for name, attrs in results}
    assert "getData" in names_and_attrs
    assert "async" in names_and_attrs["getData"]


def test_extract_export_class() -> None:
    """META-05: export class produces export marker."""
    source = """\
export class Foo {
    x = 1;
}
"""
    extractor = _make()
    results = extractor.extract("test.ts", _parse(source, "test.ts"))
    names_and_attrs = {name: attrs for name, attrs in results}
    assert "Foo" in names_and_attrs
    assert "export" in names_and_attrs["Foo"]


def test_extract_export_function() -> None:
    """META-05: export function produces export marker."""
    source = """\
export function bar(): void {}
"""
    extractor = _make()
    results = extractor.extract("test.ts", _parse(source, "test.ts"))
    names_and_attrs = {name: attrs for name, attrs in results}
    assert "bar" in names_and_attrs
    assert "export" in names_and_attrs["bar"]


def test_extract_accessibility_public() -> None:
    """META-05: public member produces public marker."""
    source = """\
class Greeter {
    public greet(): string {
        return "hi";
    }
}
"""
    extractor = _make()
    results = extractor.extract("test.ts", _parse(source, "test.ts"))
    names_and_attrs = {name: attrs for name, attrs in results}
    assert "greet" in names_and_attrs
    assert "public" in names_and_attrs["greet"]


def test_extract_accessibility_private() -> None:
    """META-05: private member produces private marker."""
    source = """\
class Greeter {
    private secret(): string {
        return "shhh";
    }
}
"""
    extractor = _make()
    results = extractor.extract("test.ts", _parse(source, "test.ts"))
    names_and_attrs = {name: attrs for name, attrs in results}
    assert "secret" in names_and_attrs
    assert "private" in names_and_attrs["secret"]


def test_extract_accessibility_protected() -> None:
    """META-05: protected member produces protected marker."""
    source = """\
class Base {
    protected helper(): void {}
}
"""
    extractor = _make()
    results = extractor.extract("test.ts", _parse(source, "test.ts"))
    names_and_attrs = {name: attrs for name, attrs in results}
    assert "helper" in names_and_attrs
    assert "protected" in names_and_attrs["helper"]


def test_combined_modifiers_static_async() -> None:
    """Combined: static async method has both markers."""
    source = """\
class Processor {
    static async process(data: string): Promise<string> {
        return data;
    }
}
"""
    extractor = _make()
    results = extractor.extract("test.ts", _parse(source, "test.ts"))
    names_and_attrs = {name: attrs for name, attrs in results}
    assert "process" in names_and_attrs
    attrs = names_and_attrs["process"]
    assert "static" in attrs
    assert "async" in attrs


def test_export_abstract_decorated() -> None:
    """Combined: export + abstract + decorator -> all markers present."""
    source = """\
@Injectable()
export abstract class Service {
    abstract handle(): void;
}
"""
    extractor = _make()
    results = extractor.extract("test.ts", _parse(source, "test.ts"))
    names_and_attrs = {name: attrs for name, attrs in results}
    assert "Service" in names_and_attrs
    attrs = names_and_attrs["Service"]
    assert "Injectable" in attrs
    assert "export" in attrs
    assert "abstract" in attrs


def test_extract_async_arrow_function() -> None:
    """Arrow function with async produces async marker."""
    source = """\
const fetchData = async () => {
    return "data";
};
"""
    extractor = _make()
    results = extractor.extract("test.ts", _parse(source, "test.ts"))
    names_and_attrs = {name: attrs for name, attrs in results}
    assert "fetchData" in names_and_attrs
    assert "async" in names_and_attrs["fetchData"]


def test_extract_exported_async_arrow_function() -> None:
    """Exported async arrow function produces both export and async markers."""
    source = """\
export const fetchData = async (url: string): Promise<string> => {
    return "";
};
"""
    extractor = _make()
    results = extractor.extract("test.ts", _parse(source, "test.ts"))
    names_and_attrs = {name: attrs for name, attrs in results}
    assert "fetchData" in names_and_attrs
    assert "async" in names_and_attrs["fetchData"]
    assert "export" in names_and_attrs["fetchData"]


def test_non_async_arrow_function_no_markers() -> None:
    """Non-async arrow function without modifiers produces no markers."""
    source = """\
const double = (x: number) => x * 2;
"""
    extractor = _make()
    results = extractor.extract("test.ts", _parse(source, "test.ts"))
    names_and_attrs = {name: attrs for name, attrs in results}
    assert "double" not in names_and_attrs


def test_empty_source() -> None:
    """Empty source returns []."""
    extractor = _make()
    results = extractor.extract("test.ts", _parse("", "test.ts"))
    assert results == []


def test_tsx_file() -> None:
    """TSX: decorators/modifiers work on .tsx file."""
    source = """\
@Component
class MyWidget {
    static render(): string {
        return "<div/>";
    }
}
"""
    extractor = _make()
    results = extractor.extract("test.tsx", _parse(source, "test.tsx"))
    names_and_attrs = {name: attrs for name, attrs in results}
    assert "MyWidget" in names_and_attrs
    assert "Component" in names_and_attrs["MyWidget"]
    assert "render" in names_and_attrs
    assert "static" in names_and_attrs["render"]


def test_no_markers_no_result() -> None:
    """Plain class with no modifiers should not appear in results."""
    source = """\
class PlainClass {
    doThing(): void {}
}
"""
    extractor = _make()
    results = extractor.extract("test.ts", _parse(source, "test.ts"))
    names_and_attrs = {name: attrs for name, attrs in results}
    assert "PlainClass" not in names_and_attrs
    assert "doThing" not in names_and_attrs


# ---------------------------------------------------------------------------
# _attrs_to_flags and TypeScriptPlugin factory method tests
# ---------------------------------------------------------------------------

from synapse.indexer.indexer import _attrs_to_flags, _ATTR_TO_FLAG  # noqa: E402
from synapse.plugin.typescript import TypeScriptPlugin  # noqa: E402


def test_attrs_to_flags_abstract() -> None:
    """TypeScript 'abstract' marker maps to is_abstract flag."""
    assert _attrs_to_flags(["abstract"]) == {"is_abstract": True}


def test_attrs_to_flags_static() -> None:
    """TypeScript 'static' marker maps to is_static flag."""
    assert _attrs_to_flags(["static"]) == {"is_static": True}


def test_attrs_to_flags_async() -> None:
    """TypeScript 'async' marker maps to is_async flag."""
    assert _attrs_to_flags(["async"]) == {"is_async": True}


def test_attrs_to_flags_combined() -> None:
    """Combined abstract+async markers produce both flags."""
    assert _attrs_to_flags(["abstract", "async"]) == {"is_abstract": True, "is_async": True}


def test_attrs_to_flags_decorator_ignored() -> None:
    """Decorators not in _ATTR_TO_FLAG produce no flags."""
    assert _attrs_to_flags(["Injectable"]) == {}


def test_plugin_returns_extractors() -> None:
    """TypeScriptPlugin factory methods return real extractor instances (not None)."""
    plugin = TypeScriptPlugin()
    assert plugin.create_attribute_extractor() is not None
    assert plugin.create_type_ref_extractor() is not None
