import os

import pytest
import tree_sitter_typescript
from tree_sitter import Language, Parser

from synapps.indexer.typescript.typescript_import_extractor import (
    TypeScriptImportExtractor,
    build_import_map,
)

_ts_lang = Language(tree_sitter_typescript.language_typescript())
_tsx_lang = Language(tree_sitter_typescript.language_tsx())
_ts_parser = Parser(_ts_lang)
_tsx_parser = Parser(_tsx_lang)
_TSX_EXTENSIONS = frozenset({".tsx", ".jsx"})


def _parse(source: str, file_path: str = "/tmp/test.ts"):
    uses_tsx = any(file_path.endswith(ext) for ext in _TSX_EXTENSIONS)
    parser = _tsx_parser if uses_tsx else _ts_parser
    return parser.parse(bytes(source, "utf-8"))


@pytest.fixture()
def extractor() -> TypeScriptImportExtractor:
    # source_root="src" so that imports from "src/index.ts" resolve relative to src/
    return TypeScriptImportExtractor(source_root="src")


# ---------------------------------------------------------------------------
# Named imports
# ---------------------------------------------------------------------------


def test_named_import(extractor: TypeScriptImportExtractor) -> None:
    source = "import { Dog, Cat } from './animals';"
    result = extractor.extract("src/index.ts", _parse(source, "src/index.ts"))
    assert ("animals", "Dog") in result
    assert ("animals", "Cat") in result
    assert len(result) == 2


def test_named_import_single(extractor: TypeScriptImportExtractor) -> None:
    source = "import { Dog } from './animals';"
    result = extractor.extract("src/index.ts", _parse(source, "src/index.ts"))
    assert result == [("animals", "Dog")]


# ---------------------------------------------------------------------------
# Default imports
# ---------------------------------------------------------------------------


def test_default_import(extractor: TypeScriptImportExtractor) -> None:
    source = "import Animal from '../animal';"
    # source_root="src", file at src/services/index.ts -> ../animal resolves to src/animal -> relpath = "animal"
    result = extractor.extract("src/services/index.ts", _parse(source, "src/services/index.ts"))
    assert ("animal", None) in result


# ---------------------------------------------------------------------------
# Namespace imports
# ---------------------------------------------------------------------------


def test_namespace_import(extractor: TypeScriptImportExtractor) -> None:
    source = "import * as Utils from './utils';"
    result = extractor.extract("src/index.ts", _parse(source, "src/index.ts"))
    assert ("utils", None) in result


# ---------------------------------------------------------------------------
# Type imports (treated identically to value imports)
# ---------------------------------------------------------------------------


def test_type_import(extractor: TypeScriptImportExtractor) -> None:
    source = "import type { IAnimal } from './types';"
    result = extractor.extract("src/index.ts", _parse(source, "src/index.ts"))
    assert ("types", "IAnimal") in result


# ---------------------------------------------------------------------------
# CommonJS require()
# ---------------------------------------------------------------------------


def test_require(extractor: TypeScriptImportExtractor) -> None:
    # source_root="src", file at src/index.ts, ./fs -> fs
    source = "const fs = require('./fs');"
    result = extractor.extract("src/index.ts", _parse(source, "src/index.ts"))
    assert ("fs", None) in result


def test_require_package(extractor: TypeScriptImportExtractor) -> None:
    source = "const path = require('path');"
    result = extractor.extract("src/index.ts", _parse(source, "src/index.ts"))
    assert ("path", None) in result


# ---------------------------------------------------------------------------
# Re-exports (named)
# ---------------------------------------------------------------------------


def test_reexport_named(extractor: TypeScriptImportExtractor) -> None:
    # source_root="src", file at src/index.ts, ./foo -> foo
    source = "export { Foo, Bar } from './foo';"
    result = extractor.extract("src/index.ts", _parse(source, "src/index.ts"))
    assert ("foo", "Foo") in result
    assert ("foo", "Bar") in result
    assert len(result) == 2


def test_reexport_named_single(extractor: TypeScriptImportExtractor) -> None:
    source = "export { Foo } from './foo';"
    result = extractor.extract("src/index.ts", _parse(source, "src/index.ts"))
    assert result == [("foo", "Foo")]


# ---------------------------------------------------------------------------
# Re-exports (star)
# ---------------------------------------------------------------------------


def test_reexport_star(extractor: TypeScriptImportExtractor) -> None:
    # source_root="src", file at src/index.ts, ./barrel -> barrel
    source = "export * from './barrel';"
    result = extractor.extract("src/index.ts", _parse(source, "src/index.ts"))
    assert ("barrel", None) in result


# ---------------------------------------------------------------------------
# Relative path resolution
# ---------------------------------------------------------------------------


def test_relative_import_resolved(tmp_path) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    extractor = TypeScriptImportExtractor(source_root=str(tmp_path))
    source = "import { Dog } from './animals';"
    # file_path inside src/
    file_path = str(src_dir / "index.ts")
    result = extractor.extract(file_path, _parse(source, file_path))
    # './animals' from src/index.ts should resolve to src/animals relative to tmp_path
    assert len(result) == 1
    module_path, symbol = result[0]
    assert symbol == "Dog"
    # Should be forward-slash separated path relative to source_root
    assert module_path == "src/animals"


def test_relative_import_parent_dir(tmp_path) -> None:
    src_dir = tmp_path / "src"
    services_dir = src_dir / "services"
    services_dir.mkdir(parents=True)
    extractor = TypeScriptImportExtractor(source_root=str(tmp_path))
    source = "import Animal from '../animal';"
    file_path = str(services_dir / "service.ts")
    result = extractor.extract(file_path, _parse(source, file_path))
    assert len(result) == 1
    module_path, symbol = result[0]
    assert symbol is None
    assert module_path == "src/animal"


# ---------------------------------------------------------------------------
# Package imports passed through unchanged
# ---------------------------------------------------------------------------


def test_package_import_unchanged(extractor: TypeScriptImportExtractor) -> None:
    source = "import React from 'react';"
    result = extractor.extract("src/index.ts", _parse(source, "src/index.ts"))
    assert ("react", None) in result


def test_scoped_package_import_unchanged(extractor: TypeScriptImportExtractor) -> None:
    source = "import { Component } from '@angular/core';"
    result = extractor.extract("src/index.ts", _parse(source, "src/index.ts"))
    assert ("@angular/core", "Component") in result


# ---------------------------------------------------------------------------
# Aliased imports use original name
# ---------------------------------------------------------------------------


def test_aliased_import_uses_original_name(extractor: TypeScriptImportExtractor) -> None:
    # source_root="src", file at src/index.ts, ./animals -> animals
    source = "import { Dog as D } from './animals';"
    result = extractor.extract("src/index.ts", _parse(source, "src/index.ts"))
    # Must use original name "Dog", not alias "D"
    assert ("animals", "Dog") in result
    assert ("animals", "D") not in result


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_source_returns_empty(extractor: TypeScriptImportExtractor) -> None:
    result = extractor.extract("src/index.ts", _parse("", "src/index.ts"))
    assert result == []


def test_whitespace_only_returns_empty(extractor: TypeScriptImportExtractor) -> None:
    result = extractor.extract("src/index.ts", _parse("   \n  ", "src/index.ts"))
    assert result == []


def test_deduplicates(extractor: TypeScriptImportExtractor) -> None:
    # source_root="src", file at src/index.ts, ./animals -> animals
    source = "import { Dog } from './animals';\nimport { Dog } from './animals';"
    result = extractor.extract("src/index.ts", _parse(source, "src/index.ts"))
    assert result.count(("animals", "Dog")) == 1


# ---------------------------------------------------------------------------
# File type handling
# ---------------------------------------------------------------------------


def test_tsx_file_parses(extractor: TypeScriptImportExtractor) -> None:
    source = "import React from 'react';\nimport { useState } from 'react';"
    result = extractor.extract("src/App.tsx", _parse(source, "src/App.tsx"))
    assert ("react", None) in result
    assert ("react", "useState") in result


def test_jsx_file_parses(extractor: TypeScriptImportExtractor) -> None:
    source = "import React from 'react';"
    result = extractor.extract("src/App.jsx", _parse(source, "src/App.jsx"))
    assert ("react", None) in result


def test_js_file_parses(extractor: TypeScriptImportExtractor) -> None:
    source = "const path = require('path');"
    result = extractor.extract("src/index.js", _parse(source, "src/index.js"))
    assert ("path", None) in result


def test_ts_file_parses(extractor: TypeScriptImportExtractor) -> None:
    # source_root="src", file at src/index.ts, ./animals -> animals
    source = "import { Dog } from './animals';"
    result = extractor.extract("src/index.ts", _parse(source, "src/index.ts"))
    assert ("animals", "Dog") in result


# ---------------------------------------------------------------------------
# Mixed import styles in one file
# ---------------------------------------------------------------------------


def test_mixed_import_styles(extractor: TypeScriptImportExtractor) -> None:
    # source_root="src", file at src/index.ts
    # ./animals -> animals, ./barrel -> barrel, 'react' -> 'react'
    source = "\n".join([
        "import React from 'react';",
        "import { useState, useEffect } from 'react';",
        "import type { FC } from 'react';",
        "export { Dog } from './animals';",
        "export * from './barrel';",
    ])
    result = extractor.extract("src/index.ts", _parse(source, "src/index.ts"))
    assert ("react", None) in result
    assert ("react", "useState") in result
    assert ("react", "useEffect") in result
    assert ("react", "FC") in result
    assert ("animals", "Dog") in result
    assert ("barrel", None) in result


# ---------------------------------------------------------------------------
# Regression: tsconfig path alias resolution
# ---------------------------------------------------------------------------


def test_path_alias_resolved_from_tsconfig(tmp_path) -> None:
    """@/ aliases from tsconfig.json paths should be resolved to real paths."""
    # Create a tsconfig.json with path alias
    tsconfig = tmp_path / "tsconfig.json"
    tsconfig.write_text('{"compilerOptions": {"paths": {"@/*": ["./src/*"]}}}')

    ext = TypeScriptImportExtractor(source_root=str(tmp_path))
    source = "import { Navigation } from '@/features/auth/Navigation';\n"
    file_path = str(tmp_path / "src" / "App.tsx")
    result = ext.extract(file_path, _parse(source, file_path))
    modules = [m for m, _ in result]
    assert "src/features/auth/Navigation" in modules


def test_path_alias_from_subdirectory_tsconfig(tmp_path) -> None:
    """Monorepo: tsconfig.json in frontend/ subdirectory should be found."""
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    tsconfig = frontend / "tsconfig.json"
    tsconfig.write_text('{"compilerOptions": {"paths": {"@/*": ["./src/*"]}}}')

    ext = TypeScriptImportExtractor(source_root=str(tmp_path))
    source = "import { Nav } from '@/components/Nav';\n"
    file_path = str(tmp_path / "frontend" / "src" / "App.tsx")
    result = ext.extract(file_path, _parse(source, file_path))
    modules = [m for m, _ in result]
    assert "frontend/src/components/Nav" in modules


def test_path_alias_lazy_loading() -> None:
    """Aliases load lazily — constructor with empty source_root doesn't fail."""
    ext = TypeScriptImportExtractor(source_root="")
    # Setting source_root after construction (mimics indexer.py:531)
    ext._source_root = "/nonexistent"
    # Should not raise — just returns empty aliases
    source = "import { X } from '@/foo';\n"
    result = ext.extract("/test.ts", _parse(source))
    modules = [m for m, _ in result]
    # No tsconfig.json at /nonexistent, so alias passes through unchanged
    assert "@/foo" in modules


# ---------------------------------------------------------------------------
# JSONC (comments + trailing commas) in tsconfig.json
# ---------------------------------------------------------------------------


def test_path_alias_with_block_comments(tmp_path) -> None:
    """tsconfig.json with /* */ block comments should parse correctly."""
    tsconfig = tmp_path / "tsconfig.json"
    tsconfig.write_text(
        '{\n'
        '  "compilerOptions": {\n'
        '    /* Bundler mode */\n'
        '    "moduleResolution": "bundler",\n'
        '    "paths": {"@/*": ["./src/*"]}\n'
        '  }\n'
        '}'
    )
    ext = TypeScriptImportExtractor(source_root=str(tmp_path))
    source = "import { Nav } from '@/components/Nav';\n"
    file_path = str(tmp_path / "src" / "App.tsx")
    result = ext.extract(file_path, _parse(source, file_path))
    modules = [m for m, _ in result]
    assert "src/components/Nav" in modules


def test_path_alias_with_line_comments(tmp_path) -> None:
    """tsconfig.json with // line comments should parse correctly."""
    tsconfig = tmp_path / "tsconfig.json"
    tsconfig.write_text(
        '{\n'
        '  "compilerOptions": {\n'
        '    // Path aliases\n'
        '    "paths": {"@/*": ["./src/*"]}\n'
        '  }\n'
        '}'
    )
    ext = TypeScriptImportExtractor(source_root=str(tmp_path))
    source = "import { Nav } from '@/components/Nav';\n"
    file_path = str(tmp_path / "src" / "App.tsx")
    result = ext.extract(file_path, _parse(source, file_path))
    modules = [m for m, _ in result]
    assert "src/components/Nav" in modules


def test_path_alias_with_trailing_commas(tmp_path) -> None:
    """tsconfig.json with trailing commas should parse correctly."""
    tsconfig = tmp_path / "tsconfig.json"
    tsconfig.write_text(
        '{\n'
        '  "compilerOptions": {\n'
        '    "paths": {"@/*": ["./src/*"]},\n'
        '  },\n'
        '}'
    )
    ext = TypeScriptImportExtractor(source_root=str(tmp_path))
    source = "import { Nav } from '@/components/Nav';\n"
    file_path = str(tmp_path / "src" / "App.tsx")
    result = ext.extract(file_path, _parse(source, file_path))
    modules = [m for m, _ in result]
    assert "src/components/Nav" in modules


# ---------------------------------------------------------------------------
# build_import_map
# ---------------------------------------------------------------------------


def test_build_import_map_named_imports(tmp_path) -> None:
    """build_import_map creates {file: {symbol: module_path}} from extract results."""
    tsconfig = tmp_path / "tsconfig.json"
    tsconfig.write_text('{"compilerOptions": {"paths": {"@/*": ["./src/*"]}}}')

    ext = TypeScriptImportExtractor(source_root=str(tmp_path))
    source = (
        "import { AppRoutes } from '@/routes/AppRoutes';\n"
        "import { AppProviders } from './providers/AppProviders';\n"
        "import React from 'react';\n"
    )
    file_path = str(tmp_path / "src" / "App.tsx")
    tree = _parse(source, file_path)
    import_map = build_import_map(ext, {file_path: tree})

    assert import_map[file_path]["AppRoutes"] == "src/routes/AppRoutes"
    assert import_map[file_path]["AppProviders"] == "src/providers/AppProviders"
    # Default import (None symbol) and package imports should be excluded
    assert "React" not in import_map[file_path]
    assert "react" not in import_map[file_path]


def test_build_import_map_excludes_default_imports(tmp_path) -> None:
    """Default imports (symbol=None) are excluded from the import map."""
    ext = TypeScriptImportExtractor(source_root=str(tmp_path))
    source = "import App from './App';\n"
    file_path = str(tmp_path / "src" / "index.tsx")
    tree = _parse(source, file_path)
    import_map = build_import_map(ext, {file_path: tree})

    assert import_map.get(file_path, {}) == {}


def test_build_import_map_empty_when_no_imports(tmp_path) -> None:
    """Files with no imports produce empty maps."""
    ext = TypeScriptImportExtractor(source_root=str(tmp_path))
    source = "export function hello() { return 'hi'; }\n"
    file_path = str(tmp_path / "src" / "util.ts")
    tree = _parse(source, file_path)
    import_map = build_import_map(ext, {file_path: tree})

    assert import_map.get(file_path) is None or import_map.get(file_path) == {}


def test_jsonc_comments_inside_strings_preserved(tmp_path) -> None:
    """Comments inside JSON string values must not be stripped."""
    tsconfig = tmp_path / "tsconfig.json"
    tsconfig.write_text(
        '{\n'
        '  "compilerOptions": {\n'
        '    "paths": {"@/*": ["./src/*"]},\n'
        '    "baseUrl": ".//weird"\n'
        '  }\n'
        '}'
    )
    ext = TypeScriptImportExtractor(source_root=str(tmp_path))
    source = "import { Nav } from '@/components/Nav';\n"
    file_path = str(tmp_path / "src" / "App.tsx")
    result = ext.extract(file_path, _parse(source, file_path))
    modules = [m for m, _ in result]
    assert "src/components/Nav" in modules
