import logging
from unittest.mock import MagicMock, patch, call
from pathlib import Path

import pytest

from synapps.indexer.symbol_resolver import SymbolResolver, _ResolveStats
from synapps.indexer.assignment_ref import AssignmentRef


def _make_ls(root: str = "/proj") -> MagicMock:
    ls = MagicMock()
    ls.repository_root_path = root
    return ls


def _mock_tree() -> MagicMock:
    """Create a sentinel tree object for tests with mocked extractors."""
    return MagicMock()


def test_resolver_walks_cs_files_and_calls_both_extractors(tmp_path):
    (tmp_path / "A.cs").write_text("namespace X { class A { void M() {} } }")

    conn = MagicMock()
    ls = _make_ls(str(tmp_path))
    ls.request_defining_symbol.return_value = None

    call_extractor = MagicMock()
    call_extractor.extract.return_value = []
    type_ref_extractor = MagicMock()
    type_ref_extractor.extract.return_value = []

    resolver = SymbolResolver(conn, ls, call_extractor=call_extractor, type_ref_extractor=type_ref_extractor)
    resolver.resolve(str(tmp_path), {})

    assert call_extractor.extract.call_count == 1
    assert type_ref_extractor.extract.call_count == 1


def test_resolver_opens_lsp_context_once_per_file(tmp_path):
    (tmp_path / "A.cs").write_text("namespace X { class A {} }")

    conn = MagicMock()
    ls = _make_ls(str(tmp_path))

    call_extractor = MagicMock()
    call_extractor.extract.return_value = [("Ns.C.M", "Helper", 1, 0)]
    type_ref_extractor = MagicMock()
    type_ref_extractor.extract.return_value = []

    resolver = SymbolResolver(conn, ls, call_extractor=call_extractor, type_ref_extractor=type_ref_extractor)
    resolver.resolve(str(tmp_path), {})

    ls.open_file.assert_called_once()


def test_resolver_writes_calls_edge():
    conn = MagicMock()
    ls = _make_ls()

    ls.request_definition.return_value = [
        {"absolutePath": "/proj/MyClass.cs", "range": {"start": {"line": 3, "character": 4}}}
    ]

    call_extractor = MagicMock()
    call_extractor.extract.return_value = [("MyNs.MyClass.Caller", "Helper", 5, 12)]
    type_ref_extractor = MagicMock()
    type_ref_extractor.extract.return_value = []

    symbol_map = {("/proj/MyClass.cs", 3): "MyNs.MyClass.Helper"}
    resolver = SymbolResolver(conn, ls, call_extractor=call_extractor, type_ref_extractor=type_ref_extractor)
    resolver._resolve_file("/proj/Foo.cs", "namespace X{}", _mock_tree(), symbol_map)

    assert any("CALLS" in str(c) for c in conn.execute.call_args_list)


def test_resolver_writes_references_edge():
    conn = MagicMock()
    ls = _make_ls()

    from synapps.indexer.type_ref import TypeRef
    type_ref_extractor = MagicMock()
    type_ref_extractor.extract.return_value = [
        TypeRef(owner_full_name="Ns.C.M", type_name="UserDto", line=5, col=15, ref_kind="parameter")
    ]

    type_sym = {
        "name": "UserDto", "kind": 5,
        "parent": {"name": "MyNs", "kind": 3, "parent": None}
    }
    ls.request_defining_symbol.return_value = type_sym

    call_extractor = MagicMock()
    call_extractor.extract.return_value = []

    resolver = SymbolResolver(conn, ls, call_extractor=call_extractor, type_ref_extractor=type_ref_extractor)
    resolver._resolve_file("/proj/Foo.cs", "namespace X{}", _mock_tree(), {})

    assert any("REFERENCES" in str(c) for c in conn.execute.call_args_list)


def test_resolver_writes_calls_edge_when_lsp_returns_class():
    """Roslyn often returns the containing class rather than the method for a call site.
    The fallback path must match the method among the class's children by callee simple name."""
    conn = MagicMock()
    ls = _make_ls()

    # request_definition returns a location that's not in symbol_map, so the fallback path is taken
    ls.request_definition.return_value = [
        {"absolutePath": "/proj/MyClass.cs", "relativePath": "MyClass.cs",
         "range": {"start": {"line": 3, "character": 4}}}
    ]
    method_child = {
        "name": "Helper", "kind": 6,
        "parent": {"name": "MyClass", "kind": 5, "parent": {"name": "MyNs", "kind": 3, "parent": None}},
    }
    # Fallback: request_containing_symbol returns the class, not the method
    ls.request_containing_symbol.return_value = {"name": "MyClass", "kind": 5, "children": [method_child], "parent": None}

    call_extractor = MagicMock()
    call_extractor.extract.return_value = [("MyNs.MyClass.Caller", "Helper", 5, 12)]
    type_ref_extractor = MagicMock()
    type_ref_extractor.extract.return_value = []

    resolver = SymbolResolver(conn, ls, call_extractor=call_extractor, type_ref_extractor=type_ref_extractor)
    # Empty symbol_map triggers the fallback path
    resolver._resolve_file("/proj/Foo.cs", "namespace X{}", _mock_tree(), {})

    assert any("CALLS" in str(c) for c in conn.execute.call_args_list)


def test_resolver_skips_call_when_lsp_returns_class_without_matching_child():
    conn = MagicMock()
    ls = _make_ls()

    ls.request_definition.return_value = [
        {"absolutePath": "/proj/MyClass.cs", "relativePath": "MyClass.cs",
         "range": {"start": {"line": 3, "character": 4}}}
    ]
    # Fallback: request_containing_symbol returns a class whose children don't include the callee
    ls.request_containing_symbol.return_value = {"name": "MyClass", "kind": 5, "children": [], "parent": None}

    call_extractor = MagicMock()
    call_extractor.extract.return_value = [("MyNs.MyClass.Caller", "Helper", 5, 12)]
    type_ref_extractor = MagicMock()
    type_ref_extractor.extract.return_value = []

    resolver = SymbolResolver(conn, ls, call_extractor=call_extractor, type_ref_extractor=type_ref_extractor)
    # Empty symbol_map triggers the fallback path
    resolver._resolve_file("/proj/Foo.cs", "namespace X{}", _mock_tree(), {})

    assert not any("CALLS" in str(c) for c in conn.execute.call_args_list)


def test_resolver_writes_references_edge_via_name_map_fallback():
    """When LSP cannot resolve a type reference (returns None), the name map is used."""
    conn = MagicMock()
    ls = _make_ls()
    ls.request_defining_symbol.return_value = None

    from synapps.indexer.type_ref import TypeRef
    type_ref_extractor = MagicMock()
    type_ref_extractor.extract.return_value = [
        TypeRef(owner_full_name="Ns.TaskService", type_name="ITaskService", line=4, col=21, ref_kind="field_type")
    ]
    call_extractor = MagicMock()
    call_extractor.extract.return_value = []

    resolver = SymbolResolver(
        conn, ls,
        call_extractor=call_extractor,
        type_ref_extractor=type_ref_extractor,
        name_to_full_names={"ITaskService": ["Ns.ITaskService"]},
    )
    resolver._resolve_file("/proj/Foo.cs", "namespace X{}", _mock_tree(), {})

    assert any("REFERENCES" in str(c) for c in conn.execute.call_args_list)


def test_resolver_skips_references_when_name_map_ambiguous():
    """Ambiguous type names (multiple full_names) must not produce a REFERENCES edge."""
    conn = MagicMock()
    ls = _make_ls()
    ls.request_defining_symbol.return_value = None

    from synapps.indexer.type_ref import TypeRef
    type_ref_extractor = MagicMock()
    type_ref_extractor.extract.return_value = [
        TypeRef(owner_full_name="Ns.C", type_name="Item", line=3, col=10, ref_kind="field_type")
    ]
    call_extractor = MagicMock()
    call_extractor.extract.return_value = []

    resolver = SymbolResolver(
        conn, ls,
        call_extractor=call_extractor,
        type_ref_extractor=type_ref_extractor,
        name_to_full_names={"Item": ["Ns.A.Item", "Ns.B.Item"]},
    )
    resolver._resolve_file("/proj/Foo.cs", "namespace X{}", _mock_tree(), {})

    assert not any("REFERENCES" in str(c) for c in conn.execute.call_args_list)


def test_resolve_call_passes_line_col_to_upsert_calls(tmp_path):
    """SymbolResolver should pass call-site position to upsert_calls."""
    cs_file = tmp_path / "A.cs"
    cs_file.write_text("namespace X { class A { void M() { B(); } } }")

    conn = MagicMock()
    ls = MagicMock()
    ls.repository_root_path = str(tmp_path)
    # request_definition returns a definition location
    ls.request_definition.return_value = [{
        "absolutePath": str(cs_file),
        "relativePath": "A.cs",
        "range": {"start": {"line": 0, "character": 30}},
    }]

    # symbol_map keyed by (file_path, line_0) → full_name
    symbol_map = {(str(cs_file), 0): "X.A.B"}

    # call_extractor returns (caller, callee_simple, line_1, col_0)
    extractor = MagicMock()
    extractor.extract.return_value = [("X.A.M", "B", 1, 35)]
    type_ref_extractor = MagicMock()
    type_ref_extractor.extract.return_value = []

    resolver = SymbolResolver(conn, ls, call_extractor=extractor, type_ref_extractor=type_ref_extractor)

    with patch("synapps.indexer.symbol_resolver.batch_upsert_calls") as mock_batch:
        resolver.resolve_single_file(str(cs_file), symbol_map)

    mock_batch.assert_called_once()
    batch = mock_batch.call_args[0][1]
    assert len(batch) == 1
    assert batch[0]["line"] == 1  # 1-indexed from extractor
    assert batch[0]["col"] == 35


def test_resolve_call_resolves_overloaded_callee_name() -> None:
    """If graph stores 'X.M(int)' but symbol_map has 'X.M', the CALLS edge must use the stored overloaded name."""
    conn = MagicMock()
    # Graph has the overloaded full_name (one unambiguous match)
    conn.query.return_value = [["Ns.C.M(int)"]]

    ls = MagicMock()
    ls.repository_root_path = "/repo"
    ls.request_definition.return_value = [
        {"absolutePath": "/repo/C.cs", "range": {"start": {"line": 7, "character": 4}}}
    ]

    # Symbol map stores the plain name; _resolve_callee_name upgrades it to the overloaded variant
    symbol_map = {("/repo/C.cs", 7): "Ns.C.M"}

    resolver = SymbolResolver(conn, ls)
    resolver._resolve_call("Ns.C.Caller", "file.cs", 10, 5, "M", symbol_map=symbol_map)

    # _resolve_call accumulates in _pending_calls; check the batch directly
    assert len(resolver._pending_calls) == 1
    assert resolver._pending_calls[0]["callee"] == "Ns.C.M(int)", (
        f"Expected overloaded name 'Ns.C.M(int)' to be used, but got: {resolver._pending_calls[0]['callee']!r}"
    )


def test_resolver_walks_py_files_with_python_extractor(tmp_path) -> None:
    """SymbolResolver walks .py files when file_extensions includes .py."""
    (tmp_path / "module.py").write_text("def foo(): pass")

    conn = MagicMock()
    ls = _make_ls(str(tmp_path))

    call_extractor = MagicMock()
    call_extractor.extract.return_value = []
    type_ref_extractor = MagicMock()
    type_ref_extractor.extract.return_value = []

    resolver = SymbolResolver(
        conn, ls,
        call_extractor=call_extractor,
        type_ref_extractor=type_ref_extractor,
        file_extensions=frozenset({".py"}),
    )
    resolver.resolve(str(tmp_path), {})

    assert call_extractor.extract.call_count == 1
    called_path = call_extractor.extract.call_args[0][0]
    assert called_path.endswith("module.py")


def test_resolver_uses_upsert_module_calls_for_module_callers(tmp_path) -> None:
    """When caller_full_name is in module_full_names, batch_upsert_module_calls is used."""
    py_file = tmp_path / "config.py"
    py_file.write_text("foo()")

    conn = MagicMock()
    conn.query.return_value = [["myproject.config.helper"]]  # _resolve_callee_name
    ls = _make_ls(str(tmp_path))
    ls.request_definition.return_value = [
        {"absolutePath": str(py_file), "range": {"start": {"line": 0, "character": 0}}}
    ]

    symbol_map = {(str(py_file), 0): "myproject.config.helper"}
    call_extractor = MagicMock()
    call_extractor.extract.return_value = [("myproject.config", "helper", 1, 0)]
    type_ref_extractor = MagicMock()
    type_ref_extractor.extract.return_value = []

    resolver = SymbolResolver(
        conn, ls,
        call_extractor=call_extractor,
        type_ref_extractor=type_ref_extractor,
        file_extensions=frozenset({".py"}),
        module_full_names={"myproject.config"},
    )

    with patch("synapps.indexer.symbol_resolver.batch_upsert_module_calls") as mock_module_batch, \
         patch("synapps.indexer.symbol_resolver.batch_upsert_calls") as mock_calls_batch:
        resolver.resolve(str(tmp_path), symbol_map)

    mock_module_batch.assert_called_once()
    mock_calls_batch.assert_not_called()


def test_resolver_tracks_unresolved_sites(tmp_path) -> None:
    """When LSP returns no definitions, the call site is appended to _unresolved_sites."""
    py_file = tmp_path / "mymod.py"
    py_file.write_text("def run(): foo()")

    conn = MagicMock()
    ls = _make_ls(str(tmp_path))
    ls.request_definition.return_value = []  # no definitions — resolution fails

    call_extractor = MagicMock()
    call_extractor.extract.return_value = [("mymod.run", "foo", 1, 11)]
    type_ref_extractor = MagicMock()
    type_ref_extractor.extract.return_value = []

    resolver = SymbolResolver(
        conn, ls,
        call_extractor=call_extractor,
        type_ref_extractor=type_ref_extractor,
        file_extensions=frozenset({".py"}),
    )
    resolver.resolve(str(tmp_path), {})

    assert len(resolver._unresolved_sites) == 1
    entry = resolver._unresolved_sites[0]
    assert "Unresolved" in entry
    assert "mymod.run" in entry
    assert "foo" in entry
    assert "mymod.py" in entry


def test_resolve_call_fallback_via_assignment_map():
    """When definition lands on a non-method position that IS in assignment_position_map,
    a second LSP call at the source position resolves the callee and writes a CALLS edge."""
    conn = MagicMock()
    ls = _make_ls()

    # First LSP call: definition points to line 10 in handler.py (a field assignment, not in symbol_map)
    ls.request_definition.side_effect = [
        # First call: resolves to the field assignment position
        [{"absolutePath": "/proj/handler.py", "range": {"start": {"line": 10, "character": 0}}}],
        # Second call (assignment fallback): resolves to the actual callee
        [{"absolutePath": "/proj/factory.py", "range": {"start": {"line": 5, "character": 0}}}],
    ]

    call_extractor = MagicMock()
    call_extractor.extract.return_value = [("Mod.MyClass.run", "process", 20, 8)]
    type_ref_extractor = MagicMock()
    type_ref_extractor.extract.return_value = []

    # symbol_map: line 10 in handler.py is NOT a method (no entry), but line 5 in factory.py IS
    symbol_map = {("/proj/factory.py", 5): "Mod.Factory.create_handler"}

    # assignment_position_map: the field assignment at handler.py:10 came from factory.py:7:4
    ref = AssignmentRef("Mod.MyClass", "_handler", "/proj/factory.py", 7, 4)
    assignment_position_map = {("/proj/handler.py", 10): ref}

    resolver = SymbolResolver(
        conn, ls,
        call_extractor=call_extractor,
        type_ref_extractor=type_ref_extractor,
        assignment_position_map=assignment_position_map,
    )

    resolver._stats = _ResolveStats()

    with patch("synapps.indexer.symbol_resolver.batch_upsert_calls") as mock_batch:
        resolver._resolve_file("/proj/Foo.py", "class X: pass", _mock_tree(), symbol_map)

    mock_batch.assert_called_once()
    batch = mock_batch.call_args[0][1]
    assert len(batch) == 1
    assert batch[0]["caller"] == "Mod.MyClass.run"

    # Stats should track the assignment fallback
    assert resolver._stats.calls_resolved == 1
    assert resolver._stats.calls_resolved_via_assignment == 1


def test_resolve_call_assignment_fallback_second_lsp_fails():
    """When assignment fallback's second LSP call returns empty, call is unresolved."""
    conn = MagicMock()
    ls = _make_ls()

    ls.request_definition.side_effect = [
        # First call: resolves to field assignment position
        [{"absolutePath": "/proj/handler.py", "range": {"start": {"line": 10, "character": 0}}}],
        # Second call (assignment fallback): returns empty
        [],
    ]

    call_extractor = MagicMock()
    call_extractor.extract.return_value = [("Mod.MyClass.run", "process", 20, 8)]
    type_ref_extractor = MagicMock()
    type_ref_extractor.extract.return_value = []

    # symbol_map must be truthy for the lookup block to run, but must NOT contain
    # the first definition position (handler.py:10)
    symbol_map = {("/proj/other.py", 99): "SomeOther.Method"}

    ref = AssignmentRef("Mod.MyClass", "_handler", "/proj/factory.py", 7, 4)
    assignment_position_map = {("/proj/handler.py", 10): ref}

    resolver = SymbolResolver(
        conn, ls,
        call_extractor=call_extractor,
        type_ref_extractor=type_ref_extractor,
        assignment_position_map=assignment_position_map,
    )

    resolver._stats = _ResolveStats()

    with patch("synapps.indexer.symbol_resolver.batch_upsert_calls") as mock_batch:
        resolver._resolve_file("/proj/Foo.py", "class X: pass", _mock_tree(), symbol_map)

    # batch_upsert_calls may be called with an empty batch or not at all
    if mock_batch.called:
        batch = mock_batch.call_args[0][1]
        assert len(batch) == 0
    assert resolver._stats.calls_unresolved == 1
    assert any("assignment fallback failed" in s for s in resolver._unresolved_sites)


def test_resolve_call_no_assignment_map_entry_falls_through():
    """When definition is not in symbol_map AND not in assignment_position_map,
    falls through to the containing_symbol path."""
    conn = MagicMock()
    ls = _make_ls()

    ls.request_definition.return_value = [
        {"absolutePath": "/proj/handler.py", "relativePath": "handler.py",
         "range": {"start": {"line": 10, "character": 0}}}
    ]
    # containing_symbol fallback returns a class with matching method child
    method_child = {
        "name": "process", "kind": 6,
        "parent": {"name": "Handler", "kind": 5, "parent": {"name": "Mod", "kind": 3, "parent": None}},
    }
    ls.request_containing_symbol.return_value = {
        "name": "Handler", "kind": 5, "children": [method_child], "parent": None,
    }

    call_extractor = MagicMock()
    call_extractor.extract.return_value = [("Mod.MyClass.run", "process", 20, 8)]
    type_ref_extractor = MagicMock()
    type_ref_extractor.extract.return_value = []

    # symbol_map truthy but doesn't contain (handler.py, 10)
    symbol_map = {("/proj/other.py", 99): "SomeOther.Method"}
    # Empty assignment_position_map -- no entry for (handler.py, 10)
    assignment_position_map = {}

    resolver = SymbolResolver(
        conn, ls,
        call_extractor=call_extractor,
        type_ref_extractor=type_ref_extractor,
        assignment_position_map=assignment_position_map,
    )

    resolver._stats = _ResolveStats()

    with patch("synapps.indexer.symbol_resolver.batch_upsert_calls") as mock_batch:
        resolver._resolve_file("/proj/Foo.py", "class X: pass", _mock_tree(), symbol_map)

    # Should have fallen through to containing_symbol path and resolved
    mock_batch.assert_called_once()
    assert len(mock_batch.call_args[0][1]) == 1


def test_resolve_call_direct_hit_skips_assignment_fallback():
    """When definition IS in symbol_map (direct method hit), assignment fallback is NOT consulted."""
    conn = MagicMock()
    ls = _make_ls()

    ls.request_definition.return_value = [
        {"absolutePath": "/proj/MyClass.py", "range": {"start": {"line": 3, "character": 4}}}
    ]

    call_extractor = MagicMock()
    call_extractor.extract.return_value = [("Mod.Caller.run", "helper", 10, 5)]
    type_ref_extractor = MagicMock()
    type_ref_extractor.extract.return_value = []

    # Direct hit: definition at line 3 IS in symbol_map
    symbol_map = {("/proj/MyClass.py", 3): "Mod.MyClass.helper"}

    # Assignment map also has an entry (should NOT be consulted)
    ref = AssignmentRef("Mod.Caller", "_svc", "/proj/other.py", 1, 0)
    assignment_position_map = {("/proj/MyClass.py", 3): ref}

    resolver = SymbolResolver(
        conn, ls,
        call_extractor=call_extractor,
        type_ref_extractor=type_ref_extractor,
        assignment_position_map=assignment_position_map,
    )

    resolver._stats = _ResolveStats()

    with patch("synapps.indexer.symbol_resolver.batch_upsert_calls") as mock_batch:
        resolver._resolve_file("/proj/Foo.py", "class X: pass", _mock_tree(), symbol_map)

    mock_batch.assert_called_once()
    assert len(mock_batch.call_args[0][1]) == 1
    # Only one LSP call was made (no second call for assignment fallback)
    assert ls.request_definition.call_count == 1
    # Stats: resolved via direct path, not via assignment
    assert resolver._stats.calls_resolved == 1
    assert resolver._stats.calls_resolved_via_assignment == 0


def test_resolve_stats_tracks_assignment_fallback_count():
    """_ResolveStats.calls_resolved_via_assignment starts at 0 and increments correctly."""
    stats = _ResolveStats()
    assert stats.calls_resolved_via_assignment == 0
    stats.calls_resolved_via_assignment += 1
    assert stats.calls_resolved_via_assignment == 1
    stats.calls_resolved_via_assignment += 3
    assert stats.calls_resolved_via_assignment == 4


def test_name_based_fallback_when_lsp_returns_external_definition():
    """When LSP definitions point to files not in symbol_map, fall back to name_to_full_names."""
    conn = MagicMock()
    conn.query.return_value = []
    ls = _make_ls()

    # LSP returns a definition in a library jar file (not in symbol_map)
    ls.request_definition.return_value = [
        {"absolutePath": "/lib/spring/Repository.java",
         "relativePath": "lib/spring/Repository.java",
         "range": {"start": {"line": 50, "character": 8}}}
    ]
    # request_containing_symbol would also fail for a jar
    ls.request_containing_symbol.return_value = None

    call_extractor = MagicMock()
    call_extractor.extract.return_value = [("order.OrderServiceImpl.create", "save", 15, 20)]
    type_ref_extractor = MagicMock()
    type_ref_extractor.extract.return_value = []

    # Provide name_to_full_names with a unique match for "save"
    name_to_full_names = {"save": ["order.OrderRepository.save"]}

    resolver = SymbolResolver(
        conn, ls,
        call_extractor=call_extractor,
        type_ref_extractor=type_ref_extractor,
        name_to_full_names=name_to_full_names,
    )
    tree = _mock_tree()
    symbol_map = {("/proj/OrderServiceImpl.java", 10): "order.OrderServiceImpl.create"}

    resolver._stats = _ResolveStats()
    resolver._resolve_file("/proj/OrderServiceImpl.java", "source", tree, symbol_map)

    # Verify the CALLS edge was created via name-based fallback
    assert resolver._stats.calls_resolved >= 1
    # Check the pending calls contain the expected edge
    # (resolve_file calls _flush_pending which batch writes)
    assert conn.execute.call_count > 0


def test_name_based_fallback_skipped_when_ambiguous():
    """When name_to_full_names has multiple candidates, don't create edge."""
    conn = MagicMock()
    conn.query.return_value = []
    ls = _make_ls()

    ls.request_definition.return_value = [
        {"absolutePath": "/lib/external.java",
         "relativePath": "lib/external.java",
         "range": {"start": {"line": 1, "character": 0}}}
    ]
    ls.request_containing_symbol.return_value = None

    call_extractor = MagicMock()
    call_extractor.extract.return_value = [("A.B.method", "save", 5, 10)]
    type_ref_extractor = MagicMock()
    type_ref_extractor.extract.return_value = []

    # Multiple candidates — ambiguous, should not resolve
    name_to_full_names = {"save": ["X.Repository.save", "Y.Repository.save"]}

    resolver = SymbolResolver(
        conn, ls,
        call_extractor=call_extractor,
        type_ref_extractor=type_ref_extractor,
        name_to_full_names=name_to_full_names,
    )
    tree = _mock_tree()
    symbol_map = {("/proj/B.java", 3): "A.B.method"}

    resolver._stats = _ResolveStats()
    resolver._resolve_file("/proj/B.java", "source", tree, symbol_map)

    assert resolver._stats.calls_unresolved >= 1


def test_resolve_file_open_file_exception_logs_skipped_counts(caplog):
    """Regression: when open_file raises, the warning log must include the counts of
    skipped call_sites and type_refs so operators can diagnose resolution failures."""
    conn = MagicMock()
    ls = _make_ls()

    # open_file raises so the whole file resolution is skipped
    ls.open_file.side_effect = RuntimeError("LSP process died")

    # 5 call sites and 2 type refs that will be skipped
    call_extractor = MagicMock()
    call_extractor.extract.return_value = [
        ("A.B.method1", "foo", 1, 0),
        ("A.B.method1", "bar", 2, 0),
        ("A.B.method1", "baz", 3, 0),
        ("A.B.method2", "qux", 4, 0),
        ("A.B.method2", "quux", 5, 0),
    ]
    from synapps.indexer.type_ref import TypeRef
    type_ref_extractor = MagicMock()
    type_ref_extractor.extract.return_value = [
        TypeRef(owner_full_name="A.B", type_name="Foo", line=1, col=5, ref_kind="field_type"),
        TypeRef(owner_full_name="A.B", type_name="Bar", line=2, col=5, ref_kind="field_type"),
    ]

    resolver = SymbolResolver(
        conn, ls,
        call_extractor=call_extractor,
        type_ref_extractor=type_ref_extractor,
    )
    resolver._stats = _ResolveStats()

    with caplog.at_level(logging.WARNING, logger="synapps.indexer.symbol_resolver"):
        resolver._resolve_file("/proj/MyClass.cs", "class X {}", _mock_tree(), {})

    # The warning must mention counts so operators know what was dropped
    warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert any(warning_messages), "Expected a WARNING log but none was emitted"
    warning_text = " ".join(warning_messages)
    assert "5" in warning_text, f"Expected skipped call count '5' in warning: {warning_text!r}"
    assert "2" in warning_text, f"Expected skipped type ref count '2' in warning: {warning_text!r}"

    # Stats must reflect the skipped call sites
    assert resolver._stats.calls_unresolved == 5


def test_resolve_file_open_file_exception_increments_calls_unresolved():
    """Regression: calls_unresolved stat must be incremented by all skipped call sites
    when open_file raises, not just by 1."""
    conn = MagicMock()
    ls = _make_ls()
    ls.open_file.side_effect = OSError("file not found in LSP workspace")

    call_extractor = MagicMock()
    call_extractor.extract.return_value = [
        ("Pkg.Service.run", "helper", 10, 5),
        ("Pkg.Service.run", "save", 11, 5),
        ("Pkg.Service.run", "validate", 12, 5),
    ]
    type_ref_extractor = MagicMock()
    type_ref_extractor.extract.return_value = []

    resolver = SymbolResolver(
        conn, ls,
        call_extractor=call_extractor,
        type_ref_extractor=type_ref_extractor,
    )
    resolver._stats = _ResolveStats()

    resolver._resolve_file("/proj/Service.cs", "class X {}", _mock_tree(), {})

    assert resolver._stats.calls_unresolved == 3
