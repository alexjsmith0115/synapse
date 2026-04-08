from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from synapps.indexer.indexer import Indexer


class TestIndexBaseTypesExternalBases:
    """Verify _index_base_types calls set_external_bases for unresolved types."""

    def _make_indexer(self) -> Indexer:
        conn = MagicMock()
        lsp = MagicMock()
        plugin = MagicMock()
        plugin.create_base_type_extractor.return_value = MagicMock()
        plugin.create_import_extractor.return_value = MagicMock()
        plugin.create_attribute_extractor.return_value = MagicMock()
        plugin.create_call_extractor.return_value = MagicMock()
        plugin.create_type_ref_extractor.return_value = MagicMock()
        plugin.file_extensions = frozenset({".cs"})
        plugin.name = "csharp"
        return Indexer(conn=conn, lsp=lsp, plugin=plugin)

    @patch("synapps.indexer.indexer.set_external_bases")
    def test_unresolved_base_type_triggers_set_external_bases(
        self, mock_set_ext: MagicMock,
    ) -> None:
        indexer = self._make_indexer()
        indexer._base_type_extractor.extract.return_value = [
            ("OrdersController", "ControllerBase", True, 5, 30),
        ]

        symbol_map = {("/src/Controllers.cs", 3): "MyApp.OrdersController"}
        kind_map = {"MyApp.OrdersController": MagicMock()}

        ls = MagicMock()
        ls.request_definition.return_value = [
            {"absolutePath": "/sdk/Microsoft.AspNetCore.Mvc.dll", "range": {"start": {"line": 0}}}
        ]
        ls.open_file.return_value.__enter__ = MagicMock(return_value=None)
        ls.open_file.return_value.__exit__ = MagicMock(return_value=False)

        indexer._index_base_types(
            "/src/Controllers.cs", MagicMock(), symbol_map, kind_map,
            ls, "/src", {},
        )

        mock_set_ext.assert_called_once_with(
            indexer._conn, "MyApp.OrdersController", ["ControllerBase"],
        )

    @patch("synapps.indexer.indexer.set_external_bases")
    def test_resolved_base_type_does_not_trigger_set_external_bases(
        self, mock_set_ext: MagicMock,
    ) -> None:
        indexer = self._make_indexer()
        indexer._base_type_extractor.extract.return_value = [
            ("Child", "Parent", True, 5, 30),
        ]

        symbol_map = {
            ("/src/Models.cs", 3): "MyApp.Child",
            ("/src/Models.cs", 10): "MyApp.Parent",
        }
        kind_map = {
            "MyApp.Child": MagicMock(),
            "MyApp.Parent": MagicMock(),
        }

        ls = MagicMock()
        ls.request_definition.return_value = [
            {"absolutePath": "/src/Models.cs", "range": {"start": {"line": 9}}}
        ]
        ls.open_file.return_value.__enter__ = MagicMock(return_value=None)
        ls.open_file.return_value.__exit__ = MagicMock(return_value=False)

        indexer._index_base_types(
            "/src/Models.cs", MagicMock(), symbol_map, kind_map,
            ls, "/src", {},
        )

        mock_set_ext.assert_not_called()

    @patch("synapps.indexer.indexer.set_external_bases")
    def test_no_triples_does_not_trigger_set_external_bases(
        self, mock_set_ext: MagicMock,
    ) -> None:
        indexer = self._make_indexer()
        indexer._base_type_extractor.extract.return_value = []

        indexer._index_base_types(
            "/src/Empty.cs", MagicMock(), {}, {},
            MagicMock(), "/src", {},
        )

        mock_set_ext.assert_not_called()
