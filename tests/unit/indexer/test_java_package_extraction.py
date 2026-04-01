from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest
import tree_sitter_java
from tree_sitter import Language, Parser

from synapps.indexer.indexer import Indexer, _extract_java_package
from synapps.lsp.interface import IndexSymbol, SymbolKind

_lang = Language(tree_sitter_java.language())
_parser = Parser(_lang)


def _parse(source: str):
    return _parser.parse(bytes(source, "utf-8"))


# ---------------------------------------------------------------------------
# _extract_java_package unit tests
# ---------------------------------------------------------------------------


def test_extract_java_package_scoped() -> None:
    """Scoped package declaration returns fully qualified name."""
    source = "package com.synappstest;\n\npublic class Foo {}\n"
    tree = _parse(source)
    assert _extract_java_package(tree) == "com.synappstest"


def test_extract_java_package_simple() -> None:
    """Single-segment package declaration returns the identifier name."""
    source = "package mypackage;\n\npublic class Bar {}\n"
    tree = _parse(source)
    assert _extract_java_package(tree) == "mypackage"


def test_extract_java_package_none() -> None:
    """File with no package declaration returns None."""
    source = "public class Baz {}\n"
    tree = _parse(source)
    assert _extract_java_package(tree) is None


# ---------------------------------------------------------------------------
# _index_file_structure integration with Package CONTAINS wiring
# ---------------------------------------------------------------------------


def _mock_lsp(files: list[str], symbols_by_file: dict) -> MagicMock:
    lsp = MagicMock()
    lsp.get_workspace_files.return_value = files
    lsp.get_document_symbols.side_effect = lambda f: symbols_by_file.get(f, [])
    lsp.language_server = MagicMock()
    return lsp


def test_index_file_structure_wires_package_contains(tmp_path) -> None:
    """_index_file_structure creates Package node and CONTAINS edge for top-level classes."""
    java_file = tmp_path / "Foo.java"
    java_file.write_text("package com.test;\npublic class Foo {}\n")
    file_path = str(java_file)

    symbols = [
        IndexSymbol(
            name="Foo",
            full_name="com.test.Foo",
            kind=SymbolKind.CLASS,
            file_path=file_path,
            line=2,
            end_line=2,
            parent_full_name=None,
        ),
    ]
    lsp = _mock_lsp([file_path], {file_path: symbols})
    conn = MagicMock()

    from synapps.plugin.java import JavaPlugin
    plugin = JavaPlugin()

    with patch("synapps.indexer.indexer.SymbolResolver"), \
         patch("synapps.indexer.indexer.MethodImplementsIndexer"):
        indexer = Indexer(conn, lsp, plugin=plugin)
        indexer.index_project(str(tmp_path), "java")

    execute_calls = [str(c) for c in conn.execute.call_args_list]

    # Package node must be created via MERGE
    pkg_merge_calls = [c for c in execute_calls if "Package" in c and "com.test" in c]
    assert len(pkg_merge_calls) >= 1, (
        f"Expected upsert_package call with 'com.test', got calls:\n" + "\n".join(execute_calls)
    )

    # CONTAINS edge from package to class must be created
    contains_calls = [
        c for c in execute_calls
        if "CONTAINS" in c and "com.test" in c and "com.test.Foo" in c
    ]
    assert len(contains_calls) >= 1, (
        f"Expected CONTAINS edge from com.test to com.test.Foo, got calls:\n" + "\n".join(execute_calls)
    )


def test_index_file_structure_skips_package_for_non_java(tmp_path) -> None:
    """C# indexing does not trigger the Java package wiring path."""
    cs_file = tmp_path / "Foo.cs"
    cs_file.write_text("namespace MyNs { public class Foo {} }\n")
    file_path = str(cs_file)

    symbols = [
        IndexSymbol(
            name="Foo",
            full_name="MyNs.Foo",
            kind=SymbolKind.CLASS,
            file_path=file_path,
            line=1,
            end_line=1,
            parent_full_name=None,
        ),
    ]
    lsp = _mock_lsp([file_path], {file_path: symbols})
    conn = MagicMock()

    with patch("synapps.indexer.indexer.SymbolResolver"), \
         patch("synapps.indexer.indexer.MethodImplementsIndexer"):
        indexer = Indexer(conn, lsp)
        indexer.index_project(str(tmp_path), "csharp")

    execute_calls = [str(c) for c in conn.execute.call_args_list]
    # No Package MERGE should be issued for Java packages (C# packages are different)
    java_pkg_calls = [c for c in execute_calls if "Package" in c and "com." in c]
    assert len(java_pkg_calls) == 0, (
        f"Unexpected Java package calls in C# indexing: {java_pkg_calls}"
    )
