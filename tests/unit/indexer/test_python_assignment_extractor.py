import pytest
import tree_sitter_python
from tree_sitter import Language, Parser
from synapse.indexer.assignment_ref import AssignmentRef
from synapse.indexer.python.python_assignment_extractor import PythonAssignmentExtractor

_lang = Language(tree_sitter_python.language())
_parser = Parser(_lang)


def _parse(source: str):
    return _parser.parse(bytes(source, "utf-8"))


@pytest.fixture
def extractor():
    return PythonAssignmentExtractor()


# ---------------------------------------------------------------------------
# Class-scope self._field = call() assignments
# ---------------------------------------------------------------------------


def test_extracts_self_field_call_assignment(extractor):
    source = """\
class MyClass:
    def __init__(self):
        self._handler = create_handler()
"""
    class_lines = [(0, "mod.MyClass")]
    results = extractor.extract(
        "/proj/foo.py", _parse(source), {}, class_lines=class_lines
    )
    assert len(results) == 1
    ref = results[0]
    assert ref.class_full_name == "mod.MyClass"
    assert ref.field_name == "_handler"
    assert ref.source_file == "/proj/foo.py"
    assert ref.source_line == 2  # 0-indexed line of create_handler()
    assert ref.source_col == 24  # column of create_handler (0-indexed)


def test_extracts_attribute_call_assignment(extractor):
    source = """\
class MyClass:
    def __init__(self):
        self._service = ServiceFactory.create()
"""
    class_lines = [(0, "mod.MyClass")]
    results = extractor.extract(
        "/proj/foo.py", _parse(source), {}, class_lines=class_lines
    )
    assert len(results) == 1
    ref = results[0]
    assert ref.class_full_name == "mod.MyClass"
    assert ref.field_name == "_service"
    # source position at ServiceFactory (start of the call function expression)
    assert ref.source_line == 2
    assert ref.source_col == 24


def test_skips_string_rhs(extractor):
    source = """\
class MyClass:
    def __init__(self):
        self._name = "hello"
"""
    class_lines = [(0, "mod.MyClass")]
    results = extractor.extract(
        "/proj/foo.py", _parse(source), {}, class_lines=class_lines
    )
    assert results == []


def test_skips_list_rhs(extractor):
    source = """\
class MyClass:
    def __init__(self):
        self._items = [1, 2, 3]
"""
    class_lines = [(0, "mod.MyClass")]
    results = extractor.extract(
        "/proj/foo.py", _parse(source), {}, class_lines=class_lines
    )
    assert results == []


def test_skips_non_self_assignment_in_method(extractor):
    source = """\
class MyClass:
    def __init__(self):
        x = 42
"""
    class_lines = [(0, "mod.MyClass")]
    results = extractor.extract(
        "/proj/foo.py", _parse(source), {}, class_lines=class_lines
    )
    assert results == []


def test_module_scope_call_assignment(extractor):
    source = """\
_handler = create_handler()
"""
    results = extractor.extract(
        "/proj/foo.py",
        _parse(source),
        {},
        module_name_resolver=lambda fp: "mypackage.mymodule",
    )
    assert len(results) == 1
    ref = results[0]
    assert ref.class_full_name == "mypackage.mymodule"
    assert ref.field_name == "_handler"


def test_module_scope_skips_non_call(extractor):
    source = """\
_handler = "not_a_call"
"""
    results = extractor.extract(
        "/proj/foo.py",
        _parse(source),
        {},
        module_name_resolver=lambda fp: "mypackage.mymodule",
    )
    assert results == []


def test_nested_class_inner_field(extractor):
    source = """\
class Outer:
    class Inner:
        def __init__(self):
            self._inner = factory()
"""
    class_lines = [(0, "mod.Outer"), (1, "mod.Outer.Inner")]
    results = extractor.extract(
        "/proj/foo.py", _parse(source), {}, class_lines=class_lines
    )
    assert len(results) == 1
    assert results[0].class_full_name == "mod.Outer.Inner"
    assert results[0].field_name == "_inner"


def test_multiple_assignments_in_same_class(extractor):
    source = """\
class MyClass:
    def __init__(self):
        self._a = make_a()
        self._b = make_b()
        self._c = make_c()
"""
    class_lines = [(0, "mod.MyClass")]
    results = extractor.extract(
        "/proj/foo.py", _parse(source), {}, class_lines=class_lines
    )
    assert len(results) == 3
    names = [r.field_name for r in results]
    assert "_a" in names
    assert "_b" in names
    assert "_c" in names


def test_empty_source_returns_empty(extractor):
    results = extractor.extract("/proj/foo.py", _parse(""), {})
    assert results == []
