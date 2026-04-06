"""Unit tests for LSP-backed base type resolution in _index_base_types().

These tests verify that _index_base_types() uses LSP request_definition() +
symbol_map lookup rather than the name-heuristic approach.
"""
from __future__ import annotations

import textwrap
from contextlib import contextmanager
from unittest.mock import MagicMock, call

import pytest
import tree_sitter_c_sharp
from tree_sitter import Language, Parser

from synapps.indexer.indexer import Indexer
from synapps.lsp.interface import IndexSymbol, LSPAdapter, SymbolKind

_lang = Language(tree_sitter_c_sharp.language())
_parser = Parser(_lang)


def _parse(source: str):
    return _parser.parse(bytes(source, "utf-8"))


def _mock_ls(definitions: list[dict] | None = None, raises: Exception | None = None):
    """Create a mock LSPResolverBackend.

    definitions: list of Location dicts to return from request_definition
    raises: if set, request_definition raises this exception
    """
    ls = MagicMock()

    @contextmanager
    def _open_file(rel_path):
        yield

    ls.open_file = _open_file

    if raises is not None:
        ls.request_definition.side_effect = raises
    else:
        ls.request_definition.return_value = definitions if definitions is not None else []

    return ls


def _mock_ls_open_fails():
    """Create a mock LSPResolverBackend whose open_file context manager raises."""
    ls = MagicMock()

    @contextmanager
    def _open_file_raises(rel_path):
        raise Exception("open_file failed")
        yield  # noqa: unreachable — required for contextmanager protocol

    ls.open_file = _open_file_raises
    return ls


def _make_indexer(language: str = "csharp"):
    """Create an Indexer with mock connection and mock LSP adapter."""
    from synapps.indexer.csharp.csharp_base_type_extractor import CSharpBaseTypeExtractor

    mock_conn = MagicMock()

    mock_lsp = MagicMock(spec=LSPAdapter)
    mock_lsp.file_extensions = frozenset({".cs"})

    plugin = MagicMock()
    plugin.name = language
    plugin.file_extensions = frozenset({".cs"})
    plugin.create_import_extractor.return_value = None
    plugin.create_base_type_extractor.return_value = CSharpBaseTypeExtractor()
    plugin.create_attribute_extractor = MagicMock(return_value=None)
    plugin.create_call_extractor = MagicMock(return_value=None)
    plugin.create_type_ref_extractor = MagicMock(return_value=None)
    plugin.create_assignment_extractor = MagicMock(return_value=None)
    plugin.create_http_extractor = MagicMock(return_value=None)

    indexer = Indexer(mock_conn, mock_lsp, plugin)
    return indexer, mock_conn


def _location(abs_path: str, line: int, col: int = 0) -> dict:
    """Build a Location dict as returned by LSP request_definition."""
    return {
        "absolutePath": abs_path,
        "range": {"start": {"line": line, "character": col}, "end": {"line": line, "character": col + 10}},
    }


def _collect_edges(mock_conn) -> dict[str, list[tuple[str, str]]]:
    """Extract edge upsert calls grouped by edge type from conn.execute calls.

    Uses param names from edges.py:
    - upsert_inherits: {"child": ..., "parent": ...}  cypher has :Class INHERITS :Class
    - upsert_implements: {"cls": ..., "iface": ...}  cypher has :Class IMPLEMENTS
    - upsert_interface_inherits: {"child": ..., "parent": ...}  cypher has :Interface INHERITS
    """
    edges: dict[str, list[tuple[str, str]]] = {"INHERITS": [], "IMPLEMENTS": [], "INTERFACE_INHERITS": []}
    for c in mock_conn.execute.call_args_list:
        cypher, params = c[0]
        if "IMPLEMENTS" in cypher and "cls" in params and "iface" in params:
            edges["IMPLEMENTS"].append((params["cls"], params["iface"]))
        elif "INHERITS" in cypher and "child" in params and "parent" in params:
            if "Interface" in cypher:
                edges["INTERFACE_INHERITS"].append((params["child"], params["parent"]))
            else:
                edges["INHERITS"].append((params["child"], params["parent"]))
    return edges


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestLspHitCreatesInherits:
    """LSP returns a definition in symbol_map -> INHERITS edge written."""

    def test_lsp_hit_creates_inherits(self):
        indexer, mock_conn = _make_indexer()

        source = "class Dog : Animal {}"
        tree = _parse(source)

        abs_path = "/proj/Animal.cs"
        # symbol_map uses 1-based lines (adapter convention); _location uses 0-based (LSP protocol)
        symbol_map = {(abs_path, 1): "Animals.Animal", ("/proj/Dog.cs", 1): "Animals.Dog"}
        kind_map = {
            "Animals.Dog": SymbolKind.CLASS,
            "Animals.Animal": SymbolKind.CLASS,
        }
        name_to_full_names = {"Dog": ["Animals.Dog"]}
        ls = _mock_ls(definitions=[_location(abs_path, 0)])

        indexer._index_base_types("/proj/Dog.cs", tree, symbol_map, kind_map, ls, "/proj", name_to_full_names)

        edges = _collect_edges(mock_conn)
        assert ("Animals.Dog", "Animals.Animal") in edges["INHERITS"]


class TestLspHitCreatesImplements:
    """Class implements interface (base_kind == INTERFACE) -> IMPLEMENTS edge."""

    def test_lsp_hit_creates_implements(self):
        indexer, mock_conn = _make_indexer(language="python")

        source = "class Cache : ICache {}"
        tree = _parse(source)

        abs_path = "/proj/ICache.cs"
        symbol_map = {(abs_path, 1): "Services.ICache", ("/proj/Cache.cs", 1): "Services.Cache"}
        kind_map = {
            "Services.Cache": SymbolKind.CLASS,
            "Services.ICache": SymbolKind.INTERFACE,
        }
        name_to_full_names = {"Cache": ["Services.Cache"]}
        ls = _mock_ls(definitions=[_location(abs_path, 0)])

        indexer._index_base_types("/proj/Cache.cs", tree, symbol_map, kind_map, ls, "/proj", name_to_full_names)

        edges = _collect_edges(mock_conn)
        assert ("Services.Cache", "Services.ICache") in edges["IMPLEMENTS"]


class TestLspHitCreatesInterfaceInherits:
    """Interface extends interface -> INTERFACE_INHERITS edge."""

    def test_lsp_hit_creates_interface_inherits(self):
        indexer, mock_conn = _make_indexer(language="python")

        source = "class IExtended : IBase {}"
        tree = _parse(source)

        abs_path = "/proj/IBase.cs"
        symbol_map = {(abs_path, 1): "NS.IBase", ("/proj/IExtended.cs", 1): "NS.IExtended"}
        kind_map = {
            "NS.IExtended": SymbolKind.INTERFACE,
            "NS.IBase": SymbolKind.INTERFACE,
        }
        name_to_full_names = {"IExtended": ["NS.IExtended"]}
        ls = _mock_ls(definitions=[_location(abs_path, 0)])

        indexer._index_base_types("/proj/IExtended.cs", tree, symbol_map, kind_map, ls, "/proj", name_to_full_names)

        edges = _collect_edges(mock_conn)
        assert ("NS.IExtended", "NS.IBase") in edges["INTERFACE_INHERITS"]


class TestLspCsharpFirstBaseDualWrite:
    """C# first base writes both INHERITS and IMPLEMENTS (existing logic)."""

    def test_lsp_csharp_first_base_dual_write(self):
        indexer, mock_conn = _make_indexer(language="csharp")

        source = "class Dog : Animal {}"
        tree = _parse(source)

        abs_path = "/proj/Animal.cs"
        symbol_map = {(abs_path, 1): "NS.Animal", ("/proj/Dog.cs", 1): "NS.Dog"}
        kind_map = {
            "NS.Dog": SymbolKind.CLASS,
            "NS.Animal": SymbolKind.CLASS,
        }
        name_to_full_names = {"Dog": ["NS.Dog"]}
        ls = _mock_ls(definitions=[_location(abs_path, 0)])

        indexer._index_base_types("/proj/Dog.cs", tree, symbol_map, kind_map, ls, "/proj", name_to_full_names)

        edges = _collect_edges(mock_conn)
        # For C# first base: both INHERITS and IMPLEMENTS are written (typed MATCH guards
        # ensure only the semantically correct one persists in the graph)
        assert ("NS.Dog", "NS.Animal") in edges["INHERITS"]
        assert ("NS.Dog", "NS.Animal") in edges["IMPLEMENTS"]


class TestLspNoDefinitionsSkips:
    """LSP returns [] -> no edges written, no error raised."""

    def test_lsp_no_definitions_skips(self):
        indexer, mock_conn = _make_indexer()

        source = "class Dog : Animal {}"
        tree = _parse(source)

        ls = _mock_ls(definitions=[])
        symbol_map: dict = {}
        kind_map = {"NS.Dog": SymbolKind.CLASS}
        name_to_full_names = {"Dog": ["NS.Dog"]}

        # Should not raise
        indexer._index_base_types("/proj/Dog.cs", tree, symbol_map, kind_map, ls, "/proj", name_to_full_names)

        mock_conn.execute.assert_not_called()


class TestLspExternalTypeSkipped:
    """LSP returns definition at location NOT in symbol_map -> no edges."""

    def test_lsp_external_type_skipped(self):
        indexer, mock_conn = _make_indexer()

        source = "class Dog : Animal {}"
        tree = _parse(source)

        # Definition points to a location not in symbol_map
        ls = _mock_ls(definitions=[_location("/external/lib/Animal.cs", 42)])
        symbol_map: dict = {}  # empty — external type not indexed
        kind_map = {"NS.Dog": SymbolKind.CLASS}
        name_to_full_names = {"Dog": ["NS.Dog"]}

        indexer._index_base_types("/proj/Dog.cs", tree, symbol_map, kind_map, ls, "/proj", name_to_full_names)

        mock_conn.execute.assert_not_called()


class TestLspExceptionSkips:
    """LSP raises Exception on request_definition -> no edges, no crash."""

    def test_lsp_exception_skips(self):
        indexer, mock_conn = _make_indexer()

        source = "class Dog : Animal {}"
        tree = _parse(source)

        ls = _mock_ls(raises=RuntimeError("LSP crashed"))
        symbol_map: dict = {}
        kind_map = {"NS.Dog": SymbolKind.CLASS}
        name_to_full_names = {"Dog": ["NS.Dog"]}

        # Must not raise
        indexer._index_base_types("/proj/Dog.cs", tree, symbol_map, kind_map, ls, "/proj", name_to_full_names)

        mock_conn.execute.assert_not_called()


class TestLspOpenFileFailure:
    """open_file raises Exception -> entire file skipped gracefully."""

    def test_lsp_open_file_failure(self):
        indexer, mock_conn = _make_indexer()

        source = "class Dog : Animal {}"
        tree = _parse(source)

        ls = _mock_ls_open_fails()
        symbol_map = {("/proj/Animal.cs", 1): "NS.Animal"}
        kind_map = {"NS.Dog": SymbolKind.CLASS, "NS.Animal": SymbolKind.CLASS}
        name_to_full_names = {"Dog": ["NS.Dog"]}

        # Must not raise
        indexer._index_base_types("/proj/Dog.cs", tree, symbol_map, kind_map, ls, "/proj", name_to_full_names)

        mock_conn.execute.assert_not_called()


class TestMultipleBaseTypes:
    """Class with 3 bases -> 3 LSP calls, correct edges for each."""

    def test_multiple_base_types(self):
        indexer, mock_conn = _make_indexer(language="python")

        # Python-style inheritance (3 bases)
        source = "class MyClass(Base, IFoo, IBar): pass"

        import tree_sitter_python
        from tree_sitter import Language as TSLanguage, Parser as TSParser
        py_lang = TSLanguage(tree_sitter_python.language())
        py_parser = TSParser(py_lang)
        py_tree = py_parser.parse(bytes(source, "utf-8"))

        from synapps.plugin.python import PythonPlugin
        mock_conn2 = MagicMock()
        mock_lsp2 = MagicMock(spec=LSPAdapter)
        mock_lsp2.file_extensions = frozenset({".py"})
        plugin2 = PythonPlugin()
        indexer2 = Indexer(mock_conn2, mock_lsp2, plugin2)

        base_abs = "/proj/Base.py"
        ifoo_abs = "/proj/IFoo.py"
        ibar_abs = "/proj/IBar.py"

        # symbol_map uses 1-based lines; _location uses 0-based
        symbol_map = {
            (base_abs, 5): "mymod.Base",
            (ifoo_abs, 3): "mymod.IFoo",
            (ibar_abs, 7): "mymod.IBar",
            ("/proj/MyClass.py", 1): "mymod.MyClass",
        }
        kind_map = {
            "mymod.MyClass": SymbolKind.CLASS,
            "mymod.Base": SymbolKind.CLASS,
            "mymod.IFoo": SymbolKind.INTERFACE,
            "mymod.IBar": SymbolKind.INTERFACE,
        }
        name_to_full_names = {"MyClass": ["mymod.MyClass"]}

        def _request_def(rel_path, line, col):
            # Return different definitions based on what's being queried
            # We can't easily distinguish which base is being queried via position alone
            # so just return the first matching entry — use call count to rotate
            call_count = _request_def.count
            _request_def.count += 1
            if call_count == 0:
                return [_location(base_abs, 4)]   # 0-based → 1-based 5
            elif call_count == 1:
                return [_location(ifoo_abs, 2)]   # 0-based → 1-based 3
            else:
                return [_location(ibar_abs, 6)]   # 0-based → 1-based 7
        _request_def.count = 0

        ls = MagicMock()

        @contextmanager
        def _open_file(rel_path):
            yield

        ls.open_file = _open_file
        ls.request_definition.side_effect = _request_def

        indexer2._index_base_types("/proj/MyClass.py", py_tree, symbol_map, kind_map, ls, "/proj", name_to_full_names)

        assert ls.request_definition.call_count == 3
        edges = _collect_edges(mock_conn2)
        assert ("mymod.MyClass", "mymod.Base") in edges["INHERITS"]
        assert ("mymod.MyClass", "mymod.IFoo") in edges["IMPLEMENTS"]
        assert ("mymod.MyClass", "mymod.IBar") in edges["IMPLEMENTS"]


class TestDeclaringTypeResolvedViaFileScope:
    """type_simple is resolved from file-scoped symbol_map entries only."""

    def test_declaring_type_resolved_from_same_file(self):
        indexer, mock_conn = _make_indexer()

        source = "class Dog : Animal {}"
        tree = _parse(source)

        abs_path = "/proj/Animal.cs"
        # Both Dog types are in the same file — both should get edges
        # symbol_map uses 1-based lines; _location uses 0-based
        symbol_map = {
            (abs_path, 1): "NS.Animal",
            ("/proj/Dog.cs", 1): "NS.Dog",
            ("/proj/Dog.cs", 10): "NS2.Dog",
        }
        kind_map = {
            "NS.Dog": SymbolKind.CLASS,
            "NS2.Dog": SymbolKind.CLASS,
            "NS.Animal": SymbolKind.CLASS,
        }
        name_to_full_names = {"Dog": ["NS.Dog", "NS2.Dog"]}
        ls = _mock_ls(definitions=[_location(abs_path, 0)])

        indexer._index_base_types("/proj/Dog.cs", tree, symbol_map, kind_map, ls, "/proj", name_to_full_names)

        edges = _collect_edges(mock_conn)
        assert ("NS.Dog", "NS.Animal") in edges["INHERITS"]
        assert ("NS2.Dog", "NS.Animal") in edges["INHERITS"]

    def test_declaring_type_in_different_file_not_matched(self):
        """A type with the same simple name in a different file must NOT get edges."""
        indexer, mock_conn = _make_indexer()

        source = "class Dog : Animal {}"
        tree = _parse(source)

        abs_path = "/proj/Animal.cs"
        # NS.Dog is in Dog.cs, NS2.Dog is in a DIFFERENT file
        symbol_map = {
            (abs_path, 1): "NS.Animal",
            ("/proj/Dog.cs", 1): "NS.Dog",
            ("/proj/other/Dog.cs", 1): "NS2.Dog",
        }
        kind_map = {
            "NS.Dog": SymbolKind.CLASS,
            "NS2.Dog": SymbolKind.CLASS,
            "NS.Animal": SymbolKind.CLASS,
        }
        name_to_full_names = {"Dog": ["NS.Dog", "NS2.Dog"]}
        ls = _mock_ls(definitions=[_location(abs_path, 0)])

        indexer._index_base_types("/proj/Dog.cs", tree, symbol_map, kind_map, ls, "/proj", name_to_full_names)

        edges = _collect_edges(mock_conn)
        assert ("NS.Dog", "NS.Animal") in edges["INHERITS"]
        # NS2.Dog is in a different file — must NOT get an edge
        assert ("NS2.Dog", "NS.Animal") not in edges["INHERITS"]


class TestLspLineNumberConversion:
    """symbol_map uses 1-based lines (from adapter), LSP returns 0-based.

    Regression: commit 1010bde converted adapter line numbers to 1-based,
    but _index_base_types used raw 0-based def_line from request_definition
    to look up in the now-1-based symbol_map, causing resolution to silently
    fail for any symbol not on line 0 of its file.
    """

    def test_1based_symbol_map_with_0based_lsp_response(self):
        """Base type on a non-zero line must resolve when symbol_map is 1-based."""
        indexer, mock_conn = _make_indexer()

        source = textwrap.dedent("""\
            using System;

            namespace NS;

            public class Dog : Animal {}
        """)
        tree = _parse(source)

        animal_abs = "/proj/Animal.cs"
        # symbol_map uses 1-based lines (as the adapter produces after 1010bde)
        symbol_map = {
            (animal_abs, 3): "NS.Animal",     # 1-based line 3
            ("/proj/Dog.cs", 5): "NS.Dog",    # 1-based line 5
        }
        kind_map = {
            "NS.Dog": SymbolKind.CLASS,
            "NS.Animal": SymbolKind.CLASS,
        }
        name_to_full_names = {"Dog": ["NS.Dog"]}
        # LSP returns 0-based line 2 (== 1-based line 3)
        ls = _mock_ls(definitions=[_location(animal_abs, 2)])

        indexer._index_base_types(
            "/proj/Dog.cs", tree, symbol_map, kind_map, ls, "/proj", name_to_full_names,
        )

        edges = _collect_edges(mock_conn)
        assert ("NS.Dog", "NS.Animal") in edges["INHERITS"]

    def test_interface_implementation_resolves_with_1based_map(self):
        """Class implementing an interface must create IMPLEMENTS edge."""
        indexer, mock_conn = _make_indexer()

        source = textwrap.dedent("""\
            using System;

            namespace NS;

            public class MyService : IMyService {}
        """)
        tree = _parse(source)

        iface_abs = "/proj/IMyService.cs"
        symbol_map = {
            (iface_abs, 11): "NS.IMyService",        # 1-based line 11
            ("/proj/MyService.cs", 5): "NS.MyService",
        }
        kind_map = {
            "NS.MyService": SymbolKind.CLASS,
            "NS.IMyService": SymbolKind.INTERFACE,
        }
        name_to_full_names = {"MyService": ["NS.MyService"]}
        # LSP returns 0-based line 10 (== 1-based line 11)
        ls = _mock_ls(definitions=[_location(iface_abs, 10)])

        indexer._index_base_types(
            "/proj/MyService.cs", tree, symbol_map, kind_map, ls, "/proj", name_to_full_names,
        )

        edges = _collect_edges(mock_conn)
        # C# first base: dual write — IMPLEMENTS should match via Interface label
        assert ("NS.MyService", "NS.IMyService") in edges["IMPLEMENTS"]
