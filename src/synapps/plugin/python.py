from __future__ import annotations

from synapps.indexer.python.python_assignment_extractor import PythonAssignmentExtractor
from synapps.indexer.python.python_attribute_extractor import PythonAttributeExtractor
from synapps.indexer.python.python_base_type_extractor import PythonBaseTypeExtractor
from synapps.indexer.python.python_import_extractor import PythonImportExtractor
from synapps.indexer.python.python_type_ref_extractor import PythonTypeRefExtractor
from synapps.lsp.python import PythonLSPAdapter


class PythonPlugin:
    def __init__(self):
        import tree_sitter_python
        from tree_sitter import Language, Parser
        self._ts_language = Language(tree_sitter_python.language())
        self._ts_parser = Parser(self._ts_language)

    @property
    def name(self) -> str:
        return "python"

    @property
    def file_extensions(self) -> frozenset[str]:
        return frozenset({".py"})

    def create_lsp_adapter(self, root_path: str) -> PythonLSPAdapter:
        return PythonLSPAdapter.create(root_path)

    def create_call_extractor(self) -> None:
        return None

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

    def create_http_extractor(self):
        from synapps.indexer.python.python_http_extractor import PythonHttpExtractor
        return PythonHttpExtractor()

    def parse_file(self, file_path: str, source: str) -> ParsedFile:
        from synapps.indexer.tree_sitter_util import ParsedFile
        tree = self._ts_parser.parse(bytes(source, "utf-8"))
        return ParsedFile(file_path=file_path, source=source, tree=tree)
