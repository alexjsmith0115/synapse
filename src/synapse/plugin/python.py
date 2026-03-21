from __future__ import annotations

from synapse.indexer.python.python_assignment_extractor import PythonAssignmentExtractor
from synapse.indexer.python.python_attribute_extractor import PythonAttributeExtractor
from synapse.indexer.python.python_base_type_extractor import PythonBaseTypeExtractor
from synapse.indexer.python.python_call_extractor import PythonCallExtractor
from synapse.indexer.python.python_import_extractor import PythonImportExtractor
from synapse.indexer.python.python_type_ref_extractor import PythonTypeRefExtractor
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

    def create_call_extractor(self) -> PythonCallExtractor:
        return PythonCallExtractor()

    def create_import_extractor(self, source_root: str = "") -> PythonImportExtractor:
        return PythonImportExtractor(source_root=source_root)

    def create_base_type_extractor(self) -> PythonBaseTypeExtractor:
        return PythonBaseTypeExtractor()

    def create_attribute_extractor(self) -> PythonAttributeExtractor:
        return PythonAttributeExtractor()

    def create_type_ref_extractor(self) -> PythonTypeRefExtractor:
        return PythonTypeRefExtractor()

    def create_assignment_extractor(self) -> PythonAssignmentExtractor:
        return PythonAssignmentExtractor()
