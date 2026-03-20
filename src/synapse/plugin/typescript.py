from __future__ import annotations

from synapse.lsp.typescript import TypeScriptLSPAdapter


class TypeScriptPlugin:
    @property
    def name(self) -> str:
        return "typescript"

    @property
    def file_extensions(self) -> frozenset[str]:
        return frozenset({".ts", ".tsx", ".js", ".jsx", ".mts", ".cts", ".mjs", ".cjs"})

    def create_lsp_adapter(self, root_path: str) -> TypeScriptLSPAdapter:
        return TypeScriptLSPAdapter.create(root_path)

    def create_call_extractor(self):
        from synapse.indexer.typescript.typescript_call_extractor import TypeScriptCallExtractor
        return TypeScriptCallExtractor()

    def create_import_extractor(self, source_root: str = ""):
        from synapse.indexer.typescript.typescript_import_extractor import TypeScriptImportExtractor
        return TypeScriptImportExtractor(source_root=source_root)

    def create_base_type_extractor(self):
        from synapse.indexer.typescript.typescript_base_type_extractor import TypeScriptBaseTypeExtractor
        return TypeScriptBaseTypeExtractor()

    def create_attribute_extractor(self):
        from synapse.indexer.typescript.typescript_attribute_extractor import TypeScriptAttributeExtractor
        return TypeScriptAttributeExtractor()

    def create_type_ref_extractor(self):
        from synapse.indexer.typescript.typescript_type_ref_extractor import TypeScriptTypeRefExtractor
        return TypeScriptTypeRefExtractor()
