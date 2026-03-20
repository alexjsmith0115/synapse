import pytest
from synapse.indexer.typescript.typescript_type_ref_extractor import TypeScriptTypeRefExtractor
from synapse.indexer.type_ref import TypeRef

FILE_TS = "test.ts"
FILE_TSX = "test.tsx"


@pytest.fixture
def extractor():
    return TypeScriptTypeRefExtractor()


def _sm(file_path: str, line: int, name: str) -> dict:
    return {(file_path, line): name}


# ---------------------------------------------------------------------------
# TREF-01: parameter type annotations
# ---------------------------------------------------------------------------

def test_extracts_parameter_type(extractor):
    source = "function greet(user: User): void {}\n"
    symbol_map = _sm(FILE_TS, 0, "test.greet")
    results = extractor.extract(FILE_TS, source, symbol_map)
    assert any(r.type_name == "User" and r.ref_kind == "parameter" for r in results)


def test_extracts_optional_parameter(extractor):
    source = "function find(item?: User): void {}\n"
    symbol_map = _sm(FILE_TS, 0, "test.find")
    results = extractor.extract(FILE_TS, source, symbol_map)
    assert any(r.type_name == "User" and r.ref_kind == "parameter" for r in results)


def test_extracts_multiple_params(extractor):
    source = "function save(a: Foo, b: Bar): void {}\n"
    symbol_map = _sm(FILE_TS, 0, "test.save")
    results = extractor.extract(FILE_TS, source, symbol_map)
    names = {r.type_name for r in results if r.ref_kind == "parameter"}
    assert "Foo" in names
    assert "Bar" in names


# ---------------------------------------------------------------------------
# TREF-02: return type annotations
# ---------------------------------------------------------------------------

def test_extracts_return_type(extractor):
    source = "function getUser(): User { return null; }\n"
    symbol_map = _sm(FILE_TS, 0, "test.getUser")
    results = extractor.extract(FILE_TS, source, symbol_map)
    assert any(r.type_name == "User" and r.ref_kind == "return_type" for r in results)


def test_extracts_generic_return_type(extractor):
    """Promise<User> should yield TypeRef for both Promise and User."""
    source = "async function load(): Promise<User> { return null; }\n"
    symbol_map = _sm(FILE_TS, 0, "test.load")
    results = extractor.extract(FILE_TS, source, symbol_map)
    names = {r.type_name for r in results if r.ref_kind == "return_type"}
    assert "Promise" in names
    assert "User" in names


# ---------------------------------------------------------------------------
# TREF-03: field and property type annotations
# ---------------------------------------------------------------------------

def test_extracts_field_type(extractor):
    source = "class MyClass {\n  private user: User;\n}\n"
    class_lines = [(0, "test.MyClass")]
    results = extractor.extract(FILE_TS, source, {}, class_lines)
    assert any(r.type_name == "User" and r.ref_kind == "field_type" for r in results)


def test_extracts_property_type(extractor):
    """Interface property signature."""
    source = "interface MyIface {\n  user: User;\n}\n"
    class_lines = [(0, "test.MyIface")]
    results = extractor.extract(FILE_TS, source, {}, class_lines)
    assert any(r.type_name == "User" and r.ref_kind == "property_type" for r in results)


# ---------------------------------------------------------------------------
# TREF-04: primitive filtering
# ---------------------------------------------------------------------------

def test_skips_primitives(extractor):
    source = (
        "function fn(a: string, b: number, c: boolean): void {}\n"
    )
    symbol_map = _sm(FILE_TS, 0, "test.fn")
    results = extractor.extract(FILE_TS, source, symbol_map)
    type_names = {r.type_name for r in results}
    assert "string" not in type_names
    assert "number" not in type_names
    assert "boolean" not in type_names
    assert "void" not in type_names


def test_skips_all_ts_primitives(extractor):
    source = (
        "function fn(a: any, b: unknown, c: never, d: null, "
        "e: undefined, f: bigint, g: symbol, h: object): void {}\n"
    )
    symbol_map = _sm(FILE_TS, 0, "test.fn")
    results = extractor.extract(FILE_TS, source, symbol_map)
    type_names = {r.type_name for r in results}
    for prim in ("any", "unknown", "never", "null", "undefined", "bigint", "symbol", "object"):
        assert prim not in type_names, f"Expected {prim!r} to be filtered"


# ---------------------------------------------------------------------------
# Generic / union / array type shapes
# ---------------------------------------------------------------------------

def test_generic_type(extractor):
    """Promise<Result> -> TypeRef for both Promise and Result."""
    source = "function load(): Promise<Result> { return null; }\n"
    symbol_map = _sm(FILE_TS, 0, "test.load")
    results = extractor.extract(FILE_TS, source, symbol_map)
    names = {r.type_name for r in results}
    assert "Promise" in names
    assert "Result" in names


def test_union_type_filters_primitives(extractor):
    """User | null -> TypeRef for User only."""
    source = "function get(): User | null { return null; }\n"
    symbol_map = _sm(FILE_TS, 0, "test.get")
    results = extractor.extract(FILE_TS, source, symbol_map)
    names = {r.type_name for r in results}
    assert "User" in names
    assert "null" not in names


def test_union_non_primitives(extractor):
    """Cat | Dog -> TypeRef for both."""
    source = "function either(): Cat | Dog { return null; }\n"
    symbol_map = _sm(FILE_TS, 0, "test.either")
    results = extractor.extract(FILE_TS, source, symbol_map)
    names = {r.type_name for r in results}
    assert "Cat" in names
    assert "Dog" in names


def test_array_shorthand(extractor):
    """User[] -> TypeRef for User."""
    source = "function list(): User[] { return []; }\n"
    symbol_map = _sm(FILE_TS, 0, "test.list")
    results = extractor.extract(FILE_TS, source, symbol_map)
    names = {r.type_name for r in results}
    assert "User" in names


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_empty_source(extractor):
    assert extractor.extract(FILE_TS, "", {}) == []


def test_tsx_file(extractor):
    """TSX parser must be used for .tsx files."""
    source = "function greet(user: User): void {}\n"
    symbol_map = _sm(FILE_TSX, 0, "test.greet")
    results = extractor.extract(FILE_TSX, source, symbol_map)
    assert any(r.type_name == "User" and r.ref_kind == "parameter" for r in results)
