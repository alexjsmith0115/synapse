from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from synapps.service import SynappsService
from conftest import _MockNode


@pytest.fixture(autouse=True)
def bypass_resolve(monkeypatch):
    """Make resolve_full_name return the name unchanged for all service tests."""
    monkeypatch.setattr("synapps.service.resolve_full_name", lambda conn, name: name)


def _service() -> SynappsService:
    conn = MagicMock()
    return SynappsService(conn=conn)


def _member_node(name: str, signature: str) -> _MockNode:
    return _MockNode(["Method"], {"name": name, "signature": signature, "full_name": f"Ns.MyClass.{name}"})


def test_read_symbol_returns_source_with_path(tmp_path) -> None:
    """Method source is returned with a // path:line header."""
    src = tmp_path / "foo.py"
    src.write_text("def bar(self):\n    pass\n    return 1\n")

    svc = _service()
    with patch.multiple(
        "synapps.service.context",
        get_symbol_source_info=lambda conn, fn: {
            "file_path": str(src),
            "line": 1,
            "end_line": 3,
        },
        get_members_overview=lambda conn, fn: [],
    ):
        result = svc.read_symbol("Ns.Foo.bar")

    assert result is not None
    assert f"// {src}:1" in result
    assert "def bar" in result


def test_read_symbol_includes_parent_signature(tmp_path) -> None:
    """Class member result prepends the containing class's declaration line."""
    class_src = tmp_path / "myclass.py"
    class_src.write_text("class MyClass(Base):\n    pass\n")

    method_src = tmp_path / "myclass.py"

    svc = _service()

    def mock_source_info(conn, full_name):
        # Both the method and the parent class are in the same file
        if full_name == "Ns.MyClass.my_method":
            return {"file_path": str(class_src), "line": 2, "end_line": 2}
        if full_name == "Ns.MyClass":
            return {"file_path": str(class_src), "line": 1, "end_line": 2}
        return None

    # conn.query returns parent data: [[parent_full_name, parent_line, parent_end_line]]
    svc._conn.query.return_value = [["Ns.MyClass", 1, 2]]

    with patch.multiple(
        "synapps.service.context",
        get_symbol_source_info=mock_source_info,
        get_members_overview=lambda conn, fn: [],
    ):
        result = svc.read_symbol("Ns.MyClass.my_method")

    assert result is not None
    assert "class MyClass" in result
    assert "pass" in result
    # Parent signature appears before method source
    parent_idx = result.index("class MyClass")
    method_idx = result.index("pass")
    assert parent_idx < method_idx


def test_read_symbol_no_parent_for_top_level(tmp_path) -> None:
    """Top-level function result has no class signature prepended."""
    src = tmp_path / "top.py"
    src.write_text("def top_func():\n    return 42\n")

    svc = _service()
    # conn.query returns empty (no containing class)
    svc._conn.query.return_value = []

    with patch.multiple(
        "synapps.service.context",
        get_symbol_source_info=lambda conn, fn: {
            "file_path": str(src),
            "line": 1,
            "end_line": 2,
        },
        get_members_overview=lambda conn, fn: [],
    ):
        result = svc.read_symbol("Ns.top_func")

    assert result is not None
    assert "def top_func" in result
    assert "// Containing type" not in result
    assert "class " not in result


def test_read_symbol_fallback_to_members(tmp_path) -> None:
    """When source line count exceeds max_lines, returns member overview instead."""
    src = tmp_path / "big.py"
    # Write 20 lines of source
    src.write_text("\n".join([f"    line_{i} = {i}" for i in range(20)]) + "\n")

    svc = _service()
    svc._conn.query.return_value = []  # no parent

    members = [
        _MockNode(["Method"], {"name": "method_a", "signature": "def method_a(self)", "full_name": "Ns.BigClass.method_a"}),
        _MockNode(["Method"], {"name": "method_b", "signature": "def method_b(self)", "full_name": "Ns.BigClass.method_b"}),
    ]

    with patch.multiple(
        "synapps.service.context",
        get_symbol_source_info=lambda conn, fn: {
            "file_path": str(src),
            "line": 1,
            "end_line": 20,
        },
        get_members_overview=lambda conn, fn: members,
    ):
        result = svc.read_symbol("Ns.BigClass", max_lines=5)

    assert result is not None
    assert "[source exceeds 5 lines" in result
    assert "method_a: def method_a(self)" in result


def test_read_symbol_fallback_note_text(tmp_path) -> None:
    """Fallback note uses exact text with em dash: [source exceeds N lines -- showing members]."""
    src = tmp_path / "big.py"
    src.write_text("\n".join([f"    x = {i}" for i in range(10)]) + "\n")

    svc = _service()
    svc._conn.query.return_value = []

    with patch.multiple(
        "synapps.service.context",
        get_symbol_source_info=lambda conn, fn: {
            "file_path": str(src),
            "line": 1,
            "end_line": 10,
        },
        get_members_overview=lambda conn, fn: [],
    ):
        result = svc.read_symbol("Ns.BigClass", max_lines=3)

    assert result is not None
    # em dash U+2014
    assert "[source exceeds 3 lines \u2014 showing members]" in result


def test_read_symbol_not_found() -> None:
    """Returns None when symbol is not in the graph."""
    svc = _service()

    with patch.multiple(
        "synapps.service.context",
        get_symbol_source_info=lambda conn, fn: None,
        get_members_overview=lambda conn, fn: [],
    ):
        result = svc.read_symbol("Nonexistent")

    assert result is None


def test_read_symbol_no_line_ranges(tmp_path) -> None:
    """Returns informative message when symbol was indexed without line ranges."""
    src = tmp_path / "noline.py"
    src.write_text("def foo(): pass\n")

    svc = _service()

    with patch.multiple(
        "synapps.service.context",
        get_symbol_source_info=lambda conn, fn: {
            "file_path": str(src),
            "line": None,
            "end_line": None,
        },
        get_members_overview=lambda conn, fn: [],
    ):
        result = svc.read_symbol("Ns.NoLines")

    assert result is not None
    assert "indexed without line ranges" in result


def test_read_symbol_default_max_lines_is_100(tmp_path) -> None:
    """Default max_lines is 100: exactly 100 lines does NOT trigger fallback, 101 does."""
    src_100 = tmp_path / "exactly100.py"
    src_100.write_text("\n".join([f"    x = {i}" for i in range(100)]) + "\n")

    src_101 = tmp_path / "over100.py"
    src_101.write_text("\n".join([f"    x = {i}" for i in range(101)]) + "\n")

    svc = _service()
    svc._conn.query.return_value = []

    members = [_MockNode(["Method"], {"name": "m", "signature": "def m(self)", "full_name": "Ns.Cls.m"})]

    # 100 lines — should NOT trigger fallback
    with patch.multiple(
        "synapps.service.context",
        get_symbol_source_info=lambda conn, fn: {
            "file_path": str(src_100),
            "line": 1,
            "end_line": 100,
        },
        get_members_overview=lambda conn, fn: members,
    ):
        result_100 = svc.read_symbol("Ns.Cls")

    assert result_100 is not None
    assert "[source exceeds" not in result_100

    # 101 lines — SHOULD trigger fallback
    with patch.multiple(
        "synapps.service.context",
        get_symbol_source_info=lambda conn, fn: {
            "file_path": str(src_101),
            "line": 1,
            "end_line": 101,
        },
        get_members_overview=lambda conn, fn: members,
    ):
        result_101 = svc.read_symbol("Ns.Cls")

    assert result_101 is not None
    assert "[source exceeds 100 lines" in result_101
