from __future__ import annotations

from synapse.indexer.java.java_attribute_extractor import JavaAttributeExtractor
from synapse.indexer.java.java_base_type_extractor import JavaBaseTypeExtractor
from synapse.indexer.java.java_call_extractor import JavaCallExtractor
from synapse.indexer.java.java_import_extractor import JavaImportExtractor
from synapse.indexer.java.java_type_ref_extractor import JavaTypeRefExtractor
from synapse.lsp.java import JavaLSPAdapter


class JavaPlugin:
    @property
    def name(self) -> str:
        return "java"

    @property
    def file_extensions(self) -> frozenset[str]:
        return frozenset({".java"})

    def create_lsp_adapter(self, root_path: str) -> JavaLSPAdapter:
        return JavaLSPAdapter.create(root_path)

    def create_call_extractor(self) -> JavaCallExtractor:
        return JavaCallExtractor()

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
