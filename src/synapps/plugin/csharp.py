from __future__ import annotations

from synapps.indexer.csharp.csharp_attribute_extractor import CSharpAttributeExtractor
from synapps.indexer.csharp.csharp_base_type_extractor import CSharpBaseTypeExtractor
from synapps.indexer.csharp.csharp_call_extractor import CSharpCallExtractor
from synapps.indexer.csharp.csharp_import_extractor import CSharpImportExtractor
from synapps.indexer.csharp.csharp_type_ref_extractor import CSharpTypeRefExtractor
from synapps.lsp.csharp import CSharpLSPAdapter


class CSharpPlugin:
    def __init__(self):
        import tree_sitter_c_sharp
        from tree_sitter import Language, Parser
        self._ts_language = Language(tree_sitter_c_sharp.language())
        self._ts_parser = Parser(self._ts_language)

    @property
    def name(self) -> str:
        return "csharp"

    @property
    def file_extensions(self) -> frozenset[str]:
        return frozenset({".cs"})

    def create_lsp_adapter(self, root_path: str) -> CSharpLSPAdapter:
        return CSharpLSPAdapter.create(root_path)

    def create_call_extractor(self) -> None:
        # Returning None activates ReferencesResolver dispatch in the indexer (LANG-04)
        return None

    def create_import_extractor(self, source_root: str = "") -> CSharpImportExtractor:
        return CSharpImportExtractor()

    def create_base_type_extractor(self) -> CSharpBaseTypeExtractor:
        return CSharpBaseTypeExtractor()

    def create_attribute_extractor(self) -> CSharpAttributeExtractor:
        return CSharpAttributeExtractor()

    def create_type_ref_extractor(self) -> CSharpTypeRefExtractor:
        return CSharpTypeRefExtractor()

    def create_assignment_extractor(self) -> None:
        return None

    def create_http_extractor(self):
        from synapps.indexer.csharp.csharp_http_extractor import CSharpHttpExtractor
        return CSharpHttpExtractor()

    def parse_file(self, file_path: str, source: str) -> ParsedFile:
        from synapps.indexer.tree_sitter_util import ParsedFile
        tree = self._ts_parser.parse(bytes(source, "utf-8"))
        return ParsedFile(file_path=file_path, source=source, tree=tree)
