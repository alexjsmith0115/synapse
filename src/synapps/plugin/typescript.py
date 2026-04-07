from __future__ import annotations

from synapps.indexer.typescript.typescript_attribute_extractor import TypeScriptAttributeExtractor
from synapps.indexer.typescript.typescript_base_type_extractor import TypeScriptBaseTypeExtractor
from synapps.indexer.typescript.typescript_import_extractor import TypeScriptImportExtractor
from synapps.indexer.typescript.typescript_type_ref_extractor import TypeScriptTypeRefExtractor
from synapps.lsp.typescript import TypeScriptLSPAdapter


_TSX_EXTENSIONS = frozenset({".tsx", ".jsx"})


class TypeScriptPlugin:
    def __init__(self):
        import tree_sitter_typescript
        from tree_sitter import Language, Parser
        self._ts_lang = Language(tree_sitter_typescript.language_typescript())
        self._tsx_lang = Language(tree_sitter_typescript.language_tsx())
        self._ts_parser = Parser(self._ts_lang)
        self._tsx_parser = Parser(self._tsx_lang)

    @property
    def name(self) -> str:
        return "typescript"

    @property
    def file_extensions(self) -> frozenset[str]:
        return frozenset({".ts", ".tsx", ".js", ".jsx", ".mts", ".cts", ".mjs", ".cjs"})

    @property
    def excluded_suffixes(self) -> frozenset[str]:
        return frozenset({".min.js", ".min.css", ".bundle.js", ".chunk.js"})

    def create_lsp_adapter(self, root_path: str) -> TypeScriptLSPAdapter:
        return TypeScriptLSPAdapter.create(root_path)

    def create_call_extractor(self) -> None:
        return None

    def create_import_extractor(self, source_root: str = "") -> TypeScriptImportExtractor:
        return TypeScriptImportExtractor(source_root=source_root)

    def create_base_type_extractor(self) -> TypeScriptBaseTypeExtractor:
        return TypeScriptBaseTypeExtractor()

    def create_attribute_extractor(self) -> TypeScriptAttributeExtractor:
        return TypeScriptAttributeExtractor()

    def create_type_ref_extractor(self) -> TypeScriptTypeRefExtractor:
        return TypeScriptTypeRefExtractor()

    def create_assignment_extractor(self) -> None:
        return None

    def create_http_extractor(self):
        from synapps.indexer.typescript.typescript_http_extractor import TypeScriptHttpExtractor
        return TypeScriptHttpExtractor()

    def parse_file(self, file_path: str, source: str) -> ParsedFile:
        from synapps.indexer.tree_sitter_util import ParsedFile
        uses_tsx = any(file_path.endswith(ext) for ext in _TSX_EXTENSIONS)
        parser = self._tsx_parser if uses_tsx else self._ts_parser
        tree = parser.parse(bytes(source, "utf-8"))
        return ParsedFile(file_path=file_path, source=source, tree=tree)
