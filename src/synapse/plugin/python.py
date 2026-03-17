from __future__ import annotations

from synapse.indexer.python_base_type_extractor import PythonBaseTypeExtractor
from synapse.indexer.python_import_extractor import PythonImportExtractor
from synapse.lsp.python import PythonLSPAdapter


class PythonPlugin:
    @property
    def name(self) -> str:
        return "python"

    @property
    def file_extensions(self) -> frozenset[str]:
        return frozenset({".py"})

    def create_lsp_adapter(self, root_path: str) -> PythonLSPAdapter:
        return PythonLSPAdapter.create(root_path)

    def create_call_extractor(self):
        return None  # Phase 3

    def create_import_extractor(self, source_root: str = "") -> PythonImportExtractor:
        return PythonImportExtractor(source_root=source_root)

    def create_base_type_extractor(self) -> PythonBaseTypeExtractor:
        return PythonBaseTypeExtractor()

    def create_attribute_extractor(self):
        return None  # Phase 4

    def create_type_ref_extractor(self):
        return None  # Not needed for Python
