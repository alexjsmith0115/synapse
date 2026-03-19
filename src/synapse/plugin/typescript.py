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
        return None  # Stub for Phase 10

    def create_import_extractor(self):
        return None  # Stub for Phase 10

    def create_base_type_extractor(self):
        from synapse.indexer.typescript_base_type_extractor import TypeScriptBaseTypeExtractor
        return TypeScriptBaseTypeExtractor()

    def create_attribute_extractor(self):
        return None  # Stub for Phase 11

    def create_type_ref_extractor(self):
        return None  # Stub for Phase 11
