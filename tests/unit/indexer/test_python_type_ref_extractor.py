import pytest
import tree_sitter_python
from tree_sitter import Language, Parser
from synapse.indexer.python.python_type_ref_extractor import PythonTypeRefExtractor
from synapse.indexer.type_ref import TypeRef

_lang = Language(tree_sitter_python.language())
_parser = Parser(_lang)


def _parse(source: str):
    return _parser.parse(bytes(source, "utf-8"))


FILE_PY = "test.py"


@pytest.fixture
def extractor():
    return PythonTypeRefExtractor()


def _sm(file_path: str, line: int, name: str) -> dict:
    return {(file_path, line): name}


# ---------------------------------------------------------------------------
# TREF-PY-01: parameter type annotations
# ---------------------------------------------------------------------------

def test_extracts_parameter_type(extractor):
    source = "def greet(user: User):\n    pass\n"
    symbol_map = _sm(FILE_PY, 0, "test.greet")
    results = extractor.extract(FILE_PY, _parse(source), symbol_map)
    assert any(r.type_name == "User" and r.ref_kind == "parameter" for r in results)


def test_extracts_multiple_params(extractor):
    source = "def save(a: Foo, b: Bar):\n    pass\n"
    symbol_map = _sm(FILE_PY, 0, "test.save")
    results = extractor.extract(FILE_PY, _parse(source), symbol_map)
    names = {r.type_name for r in results if r.ref_kind == "parameter"}
    assert "Foo" in names
    assert "Bar" in names


def test_extracts_typed_default_parameter(extractor):
    source = "def process(item: Widget = None):\n    pass\n"
    symbol_map = _sm(FILE_PY, 0, "test.process")
    results = extractor.extract(FILE_PY, _parse(source), symbol_map)
    assert any(r.type_name == "Widget" and r.ref_kind == "parameter" for r in results)


# ---------------------------------------------------------------------------
# TREF-PY-02: return type annotations
# ---------------------------------------------------------------------------

def test_extracts_return_type(extractor):
    source = "def get() -> User:\n    pass\n"
    symbol_map = _sm(FILE_PY, 0, "test.get")
    results = extractor.extract(FILE_PY, _parse(source), symbol_map)
    assert any(r.type_name == "User" and r.ref_kind == "return_type" for r in results)


# ---------------------------------------------------------------------------
# TREF-PY-03: class variable type annotations
# ---------------------------------------------------------------------------

def test_extracts_class_annotation(extractor):
    source = "class C:\n    name: User\n"
    class_lines = [(0, "test.C")]
    results = extractor.extract(FILE_PY, _parse(source), {}, class_lines)
    assert any(r.type_name == "User" and r.ref_kind == "field_type" for r in results)


# ---------------------------------------------------------------------------
# TREF-PY-04: generic types
# ---------------------------------------------------------------------------

def test_generic_type_extracts_inner(extractor):
    source = "def get_users() -> list[User]:\n    pass\n"
    symbol_map = _sm(FILE_PY, 0, "test.get_users")
    results = extractor.extract(FILE_PY, _parse(source), symbol_map)
    names = {r.type_name for r in results}
    assert "User" in names
    assert "list" not in names


def test_generic_dict_extracts_non_primitive(extractor):
    source = "def get_map() -> dict[str, Config]:\n    pass\n"
    symbol_map = _sm(FILE_PY, 0, "test.get_map")
    results = extractor.extract(FILE_PY, _parse(source), symbol_map)
    names = {r.type_name for r in results}
    assert "Config" in names
    assert "dict" not in names
    assert "str" not in names


# ---------------------------------------------------------------------------
# TREF-PY-05: union types (PEP 604)
# ---------------------------------------------------------------------------

def test_union_type_extracts_non_none(extractor):
    source = "def find() -> User | None:\n    pass\n"
    symbol_map = _sm(FILE_PY, 0, "test.find")
    results = extractor.extract(FILE_PY, _parse(source), symbol_map)
    names = {r.type_name for r in results}
    assert "User" in names
    assert "None" not in names


def test_union_type_extracts_both(extractor):
    source = "def either() -> Foo | Bar:\n    pass\n"
    symbol_map = _sm(FILE_PY, 0, "test.either")
    results = extractor.extract(FILE_PY, _parse(source), symbol_map)
    names = {r.type_name for r in results}
    assert "Foo" in names
    assert "Bar" in names


# ---------------------------------------------------------------------------
# TREF-PY-06: primitive filtering
# ---------------------------------------------------------------------------

def test_skips_primitives(extractor):
    source = "def f(x: int, y: str):\n    pass\n"
    symbol_map = _sm(FILE_PY, 0, "test.f")
    results = extractor.extract(FILE_PY, _parse(source), symbol_map)
    assert results == []


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_empty_source(extractor):
    assert extractor.extract(FILE_PY, _parse(""), {}) == []


def test_typing_optional_extracts_inner(extractor):
    source = "def get(x: typing.Optional[User]):\n    pass\n"
    symbol_map = _sm(FILE_PY, 0, "test.get")
    results = extractor.extract(FILE_PY, _parse(source), symbol_map)
    names = {r.type_name for r in results}
    assert "User" in names
    assert "Optional" not in names
    assert "typing" not in names
