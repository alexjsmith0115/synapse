from __future__ import annotations

from synapps.indexer.java.java_attribute_extractor import JavaAttributeExtractor
from synapps.indexer.java.java_base_type_extractor import JavaBaseTypeExtractor
from synapps.indexer.java.java_import_extractor import JavaImportExtractor
from synapps.indexer.java.java_type_ref_extractor import JavaTypeRefExtractor
from synapps.lsp.java import JavaLSPAdapter


class JavaPlugin:
    def __init__(self):
        import tree_sitter_java
        from tree_sitter import Language, Parser
        self._ts_language = Language(tree_sitter_java.language())
        self._ts_parser = Parser(self._ts_language)

    @property
    def name(self) -> str:
        return "java"

    @property
    def file_extensions(self) -> frozenset[str]:
        return frozenset({".java"})

    def create_lsp_adapter(self, root_path: str) -> JavaLSPAdapter:
        return JavaLSPAdapter.create(root_path)

    def create_call_extractor(self) -> None:
        return None

    def create_import_extractor(self, source_root: str = "") -> JavaImportExtractor:
        return JavaImportExtractor(source_root=source_root)

    def create_base_type_extractor(self) -> JavaBaseTypeExtractor:
        return JavaBaseTypeExtractor()

    def create_attribute_extractor(self) -> JavaAttributeExtractor:
        return JavaAttributeExtractor()

    def create_type_ref_extractor(self) -> JavaTypeRefExtractor:
        return JavaTypeRefExtractor()

    def create_assignment_extractor(self) -> None:
        return None

    def create_http_extractor(self):
        from synapps.indexer.java.java_http_extractor import JavaHttpExtractor
        return JavaHttpExtractor()

    def parse_file(self, file_path: str, source: str) -> ParsedFile:
        from synapps.indexer.tree_sitter_util import ParsedFile
        tree = self._ts_parser.parse(bytes(source, "utf-8"))
        return ParsedFile(file_path=file_path, source=source, tree=tree)
