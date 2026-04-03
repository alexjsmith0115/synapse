import pytest
import tree_sitter_java
from tree_sitter import Language, Parser
from synapps.indexer.java.java_attribute_extractor import JavaAttributeExtractor

_lang = Language(tree_sitter_java.language())
_parser = Parser(_lang)


def _parse(source: str):
    return _parser.parse(bytes(source, "utf-8"))


@pytest.fixture
def extractor():
    return JavaAttributeExtractor()


# ---------------------------------------------------------------------------
# Annotations
# ---------------------------------------------------------------------------


def test_single_annotation(extractor):
    source = """\
public class MyClass {
    @Override
    public void speak() {}
}
"""
    results = extractor.extract("/proj/MyClass.java", _parse(source))
    names_and_attrs = {name: attrs for name, attrs in results}
    assert "speak" in names_and_attrs
    assert "override" in names_and_attrs["speak"]


def test_multiple_annotations(extractor):
    source = """\
public class MyClass {
    @Deprecated
    @Override
    public void speak() {}
}
"""
    results = extractor.extract("/proj/MyClass.java", _parse(source))
    names_and_attrs = {name: attrs for name, attrs in results}
    assert "speak" in names_and_attrs
    assert "deprecated" in names_and_attrs["speak"]
    assert "override" in names_and_attrs["speak"]


def test_annotation_with_arguments(extractor):
    source = """\
public class MyClass {
    @SuppressWarnings("unchecked")
    public void process() {}
}
"""
    results = extractor.extract("/proj/MyClass.java", _parse(source))
    names_and_attrs = {name: attrs for name, attrs in results}
    assert "process" in names_and_attrs
    assert "suppresswarnings" in names_and_attrs["process"]


# ---------------------------------------------------------------------------
# Modifier keywords (D-19)
# ---------------------------------------------------------------------------


def test_modifier_abstract(extractor):
    source = """\
public abstract class Foo {
    public abstract void doWork();
}
"""
    results = extractor.extract("/proj/Foo.java", _parse(source))
    names_and_attrs = {name: attrs for name, attrs in results}
    assert "Foo" in names_and_attrs
    assert "abstract" in names_and_attrs["Foo"]
    assert "doWork" in names_and_attrs
    assert "abstract" in names_and_attrs["doWork"]


def test_modifier_static(extractor):
    source = """\
public class MyClass {
    public static void helper() {}
}
"""
    results = extractor.extract("/proj/MyClass.java", _parse(source))
    names_and_attrs = {name: attrs for name, attrs in results}
    assert "helper" in names_and_attrs
    assert "static" in names_and_attrs["helper"]


def test_modifier_synchronized(extractor):
    source = """\
public class MyClass {
    public synchronized void process() {}
}
"""
    results = extractor.extract("/proj/MyClass.java", _parse(source))
    names_and_attrs = {name: attrs for name, attrs in results}
    assert "process" in names_and_attrs
    assert "synchronized" in names_and_attrs["process"]


def test_modifier_final(extractor):
    source = """\
public final class Constants {
}
"""
    results = extractor.extract("/proj/Constants.java", _parse(source))
    names_and_attrs = {name: attrs for name, attrs in results}
    assert "Constants" in names_and_attrs
    assert "final" in names_and_attrs["Constants"]


def test_modifier_native(extractor):
    source = """\
public class MyClass {
    public native void nativeMethod();
}
"""
    results = extractor.extract("/proj/MyClass.java", _parse(source))
    names_and_attrs = {name: attrs for name, attrs in results}
    assert "nativeMethod" in names_and_attrs
    assert "native" in names_and_attrs["nativeMethod"]


# ---------------------------------------------------------------------------
# Combined annotations + modifiers
# ---------------------------------------------------------------------------


def test_combined_annotation_and_modifier(extractor):
    source = """\
public class MyClass {
    @Override
    public static void helper() {}
}
"""
    results = extractor.extract("/proj/MyClass.java", _parse(source))
    names_and_attrs = {name: attrs for name, attrs in results}
    assert "helper" in names_and_attrs
    attrs = names_and_attrs["helper"]
    assert "override" in attrs
    assert "static" in attrs


# ---------------------------------------------------------------------------
# No attributes / empty source
# ---------------------------------------------------------------------------


def test_no_attributes(extractor):
    """Plain class with no modifiers or annotations should produce no results."""
    source = """\
class PlainClass {
    void doThing() {}
}
"""
    results = extractor.extract("/proj/PlainClass.java", _parse(source))
    names_and_attrs = {name: attrs for name, attrs in results}
    assert "PlainClass" not in names_and_attrs
    assert "doThing" not in names_and_attrs


def test_empty_source(extractor):
    results = extractor.extract("/proj/MyClass.java", _parse(""))
    assert results == []


def test_whitespace_source(extractor):
    results = extractor.extract("/proj/MyClass.java", _parse("   \n  "))
    assert results == []


# ---------------------------------------------------------------------------
# Field annotations (regression for _declaration_name bug on field_declaration)
# ---------------------------------------------------------------------------


def test_field_annotation_autowired(extractor):
    """@Autowired on a field should be captured with field name."""
    source = """\
public class MyService {
    @Autowired
    private OrderRepository repo;
}
"""
    results = extractor.extract("/proj/MyService.java", _parse(source))
    names_and_attrs = {name: attrs for name, attrs in results}
    assert "repo" in names_and_attrs
    assert "autowired" in names_and_attrs["repo"]


def test_field_annotation_inject(extractor):
    """@Inject on a field should be captured with field name."""
    source = """\
public class MyService {
    @Inject
    private IAnimal animal;
}
"""
    results = extractor.extract("/proj/MyService.java", _parse(source))
    names_and_attrs = {name: attrs for name, attrs in results}
    assert "animal" in names_and_attrs
    assert "inject" in names_and_attrs["animal"]


def test_field_multiple_declarators_annotation(extractor):
    """@Value on a multi-declarator field: only first declarator name extracted."""
    source = """\
public class MyService {
    @Value
    private String a, b;
}
"""
    results = extractor.extract("/proj/MyService.java", _parse(source))
    names_and_attrs = {name: attrs for name, attrs in results}
    # _declaration_name returns the first declarator name
    assert "a" in names_and_attrs
    assert "value" in names_and_attrs["a"]
