from __future__ import annotations

import pytest
import tree_sitter_c_sharp as tscsharp
import tree_sitter_java as tsjava
import tree_sitter_python as tspython
from tree_sitter import Language, Parser

from synapps.indexer.tree_sitter_util import ParsedFile, find_enclosing_method_ast

_PY_LANGUAGE = Language(tspython.language())
_JAVA_LANGUAGE = Language(tsjava.language())
_CS_LANGUAGE = Language(tscsharp.language())
_parser = Parser(_PY_LANGUAGE)
_java_parser = Parser(_JAVA_LANGUAGE)
_cs_parser = Parser(_CS_LANGUAGE)


def _make_parsed_file(source: str, file_path: str = "/test/file.py") -> ParsedFile:
    tree = _parser.parse(bytes(source, "utf-8"))
    return ParsedFile(file_path=file_path, source=source, tree=tree)


def _make_java_parsed_file(source: str, file_path: str = "/test/Foo.java") -> ParsedFile:
    tree = _java_parser.parse(bytes(source, "utf-8"))
    return ParsedFile(file_path=file_path, source=source, tree=tree)


def _make_cs_parsed_file(source: str, file_path: str = "/test/Foo.cs") -> ParsedFile:
    tree = _cs_parser.parse(bytes(source, "utf-8"))
    return ParsedFile(file_path=file_path, source=source, tree=tree)


# ---------------------------------------------------------------------------
# Basic: position inside a top-level function
# ---------------------------------------------------------------------------


def test_returns_enclosing_function_name():
    source = """\
def my_func():
    x = 1
    return x
"""
    pf = _make_parsed_file(source)
    symbol_map = {("/test/file.py", 1): "mypackage.my_func"}
    # line 1 (0-based), col 4 — inside the function body
    result = find_enclosing_method_ast("/test/file.py", 1, 4, {"/test/file.py": pf}, symbol_map)
    assert result == "mypackage.my_func"


# ---------------------------------------------------------------------------
# Missing file: parsed_cache does not contain the file
# ---------------------------------------------------------------------------


def test_returns_none_for_missing_file():
    symbol_map: dict[tuple[str, int], str] = {}
    result = find_enclosing_method_ast("/nonexistent/file.py", 0, 0, {}, symbol_map)
    assert result is None


# ---------------------------------------------------------------------------
# Module-level code: position before any function definition
# ---------------------------------------------------------------------------


def test_returns_none_for_module_level_code():
    source = """\
import os

x = 1

def my_func():
    pass
"""
    pf = _make_parsed_file(source)
    symbol_map = {("/test/file.py", 5): "mypackage.my_func"}
    # line 0 (0-based) — import statement, outside any function
    result = find_enclosing_method_ast("/test/file.py", 0, 0, {"/test/file.py": pf}, symbol_map)
    assert result is None


# ---------------------------------------------------------------------------
# Nested functions: innermost function wins
# ---------------------------------------------------------------------------


def test_returns_innermost_for_nested_function():
    source = """\
def outer():
    def inner():
        x = 1
"""
    pf = _make_parsed_file(source)
    symbol_map = {
        ("/test/file.py", 1): "mypackage.outer",
        ("/test/file.py", 2): "mypackage.outer.inner",
    }
    # line 2 (0-based, 0-indexed), col 8 — inside inner function body
    result = find_enclosing_method_ast("/test/file.py", 2, 8, {"/test/file.py": pf}, symbol_map)
    assert result == "mypackage.outer.inner"


# ---------------------------------------------------------------------------
# Symbol map miss: method node exists in AST but has no entry in symbol_map
# ---------------------------------------------------------------------------


def test_returns_none_when_symbol_map_has_no_entry():
    source = """\
def unknown_func():
    pass
"""
    pf = _make_parsed_file(source)
    # Intentionally empty symbol_map — function exists in AST but is not indexed
    symbol_map: dict[tuple[str, int], str] = {}
    result = find_enclosing_method_ast("/test/file.py", 1, 4, {"/test/file.py": pf}, symbol_map)
    assert result is None


# ---------------------------------------------------------------------------
# Method inside class: position inside method body
# ---------------------------------------------------------------------------


def test_returns_method_inside_class():
    source = """\
class MyClass:
    def my_method(self):
        return 42
"""
    pf = _make_parsed_file(source)
    symbol_map = {("/test/file.py", 2): "mypackage.MyClass.my_method"}
    # line 2 (0-based), col 8 — inside method body
    result = find_enclosing_method_ast("/test/file.py", 2, 8, {"/test/file.py": pf}, symbol_map)
    assert result == "mypackage.MyClass.my_method"


# ---------------------------------------------------------------------------
# Java: annotated method — symbol_map keyed by name line, not annotation line
# ---------------------------------------------------------------------------


def test_java_annotated_method_matches_name_line():
    """Regression: tree-sitter method_declaration includes annotations, so
    start_point is on the annotation line. symbol_map is keyed by
    selectionRange (name line) from JDT LS. The lookup must use the name
    node's line, not the declaration node's start line."""
    source = """\
class RabbitSend {
    @Override
    public void send(String msg) {
        channel.basicPublish(msg);
    }
}
"""
    fp = "/test/Foo.java"
    pf = _make_java_parsed_file(source, file_path=fp)
    # symbol_map keyed by name line (line 3, 1-based) — matches JDT LS selectionRange
    symbol_map = {(fp, 3): "foodsearch.mq.RabbitSend.send"}
    # Reference at line 3 (0-based), col 8 — inside send() body
    result = find_enclosing_method_ast(fp, 3, 8, {fp: pf}, symbol_map)
    assert result == "foodsearch.mq.RabbitSend.send"


def test_java_multi_annotation_method():
    """Method with multiple annotations — larger gap between declaration start
    and name line."""
    source = """\
class Controller {
    @CrossOrigin
    @GetMapping("/contacts")
    public List<Contact> getAllContacts() {
        return repo.findAll();
    }
}
"""
    fp = "/test/Controller.java"
    pf = _make_java_parsed_file(source, file_path=fp)
    # Name line is 4 (1-based), annotations start at line 2
    symbol_map = {(fp, 4): "com.example.Controller.getAllContacts"}
    # Reference at line 4 (0-based), col 8 — inside method body
    result = find_enclosing_method_ast(fp, 4, 8, {fp: pf}, symbol_map)
    assert result == "com.example.Controller.getAllContacts"


# ---------------------------------------------------------------------------
# C#: attributed method — same issue as Java annotations
# ---------------------------------------------------------------------------


def test_csharp_attributed_method_matches_name_line():
    """Regression: C# method_declaration includes attribute lists, so
    start_point is on the [HttpGet] line, not the method name line."""
    source = """\
class Controller {
    [HttpGet]
    public void GetItems() {
        return items;
    }
}
"""
    fp = "/test/Foo.cs"
    pf = _make_cs_parsed_file(source, file_path=fp)
    # symbol_map keyed by name line (line 3, 1-based)
    symbol_map = {(fp, 3): "MyApp.Controller.GetItems"}
    # Reference at line 3 (0-based), col 8 — inside method body
    result = find_enclosing_method_ast(fp, 3, 8, {fp: pf}, symbol_map)
    assert result == "MyApp.Controller.GetItems"


# ---------------------------------------------------------------------------
# _is_in_type_checking_block tests
# ---------------------------------------------------------------------------


from synapps.indexer.tree_sitter_util import _is_in_type_checking_block


class TestIsInTypeCheckingBlock:
    def test_position_inside_bare_type_checking_block_returns_true(self):
        """A position inside `if TYPE_CHECKING:` block returns True."""
        source = """\
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    some_call()
"""
        pf = _make_parsed_file(source)
        parsed_cache = {"/test/file.py": pf}
        # line 2 (0-based) is `    some_call()` — inside the TYPE_CHECKING block
        result = _is_in_type_checking_block("/test/file.py", 2, 4, parsed_cache)
        assert result is True

    def test_position_inside_qualified_type_checking_block_returns_true(self):
        """A position inside `if typing.TYPE_CHECKING:` (qualified) block returns True."""
        source = """\
import typing
if typing.TYPE_CHECKING:
    some_call()
"""
        pf = _make_parsed_file(source)
        parsed_cache = {"/test/file.py": pf}
        # line 2 (0-based) is `    some_call()` — inside the typing.TYPE_CHECKING block
        result = _is_in_type_checking_block("/test/file.py", 2, 4, parsed_cache)
        assert result is True

    def test_position_outside_any_type_checking_block_returns_false(self):
        """A position at module level outside any if block returns False."""
        source = """\
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    some_import = True

x = 42
"""
        pf = _make_parsed_file(source)
        parsed_cache = {"/test/file.py": pf}
        # line 4 (0-based) is `x = 42` — outside any block
        result = _is_in_type_checking_block("/test/file.py", 4, 0, parsed_cache)
        assert result is False

    def test_position_inside_regular_if_block_returns_false(self):
        """A position inside a regular `if` block (not TYPE_CHECKING) returns False."""
        source = """\
some_condition = True
if some_condition:
    code()
"""
        pf = _make_parsed_file(source)
        parsed_cache = {"/test/file.py": pf}
        # line 2 (0-based) is `    code()` — inside a regular if block
        result = _is_in_type_checking_block("/test/file.py", 2, 4, parsed_cache)
        assert result is False

    def test_file_not_in_parsed_cache_returns_false(self):
        """When the file is not in parsed_cache, returns False (safe default)."""
        result = _is_in_type_checking_block("/nonexistent/file.py", 0, 0, {})
        assert result is False
