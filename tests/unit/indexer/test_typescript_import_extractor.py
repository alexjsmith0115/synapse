import os

import pytest

from synapse.indexer.typescript_import_extractor import TypeScriptImportExtractor


@pytest.fixture()
def extractor() -> TypeScriptImportExtractor:
    return TypeScriptImportExtractor()


# ---------------------------------------------------------------------------
# Named imports
# ---------------------------------------------------------------------------


def test_named_import(extractor: TypeScriptImportExtractor) -> None:
    source = "import { Dog, Cat } from './animals';"
    result = extractor.extract("src/index.ts", source)
    assert ("animals", "Dog") in result
    assert ("animals", "Cat") in result
    assert len(result) == 2


def test_named_import_single(extractor: TypeScriptImportExtractor) -> None:
    source = "import { Dog } from './animals';"
    result = extractor.extract("src/index.ts", source)
    assert result == [("animals", "Dog")]


# ---------------------------------------------------------------------------
# Default imports
# ---------------------------------------------------------------------------


def test_default_import(extractor: TypeScriptImportExtractor) -> None:
    source = "import Animal from '../animal';"
    result = extractor.extract("src/services/index.ts", source)
    assert ("animal", None) in result


# ---------------------------------------------------------------------------
# Namespace imports
# ---------------------------------------------------------------------------


def test_namespace_import(extractor: TypeScriptImportExtractor) -> None:
    source = "import * as Utils from './utils';"
    result = extractor.extract("src/index.ts", source)
    assert ("utils", None) in result


# ---------------------------------------------------------------------------
# Type imports (treated identically to value imports)
# ---------------------------------------------------------------------------


def test_type_import(extractor: TypeScriptImportExtractor) -> None:
    source = "import type { IAnimal } from './types';"
    result = extractor.extract("src/index.ts", source)
    assert ("types", "IAnimal") in result


# ---------------------------------------------------------------------------
# CommonJS require()
# ---------------------------------------------------------------------------


def test_require(extractor: TypeScriptImportExtractor) -> None:
    source = "const fs = require('./fs');"
    result = extractor.extract("src/index.ts", source)
    assert ("fs", None) in result


def test_require_package(extractor: TypeScriptImportExtractor) -> None:
    source = "const path = require('path');"
    result = extractor.extract("src/index.ts", source)
    assert ("path", None) in result


# ---------------------------------------------------------------------------
# Re-exports (named)
# ---------------------------------------------------------------------------


def test_reexport_named(extractor: TypeScriptImportExtractor) -> None:
    source = "export { Foo, Bar } from './foo';"
    result = extractor.extract("src/index.ts", source)
    assert ("foo", "Foo") in result
    assert ("foo", "Bar") in result
    assert len(result) == 2


def test_reexport_named_single(extractor: TypeScriptImportExtractor) -> None:
    source = "export { Foo } from './foo';"
    result = extractor.extract("src/index.ts", source)
    assert result == [("foo", "Foo")]


# ---------------------------------------------------------------------------
# Re-exports (star)
# ---------------------------------------------------------------------------


def test_reexport_star(extractor: TypeScriptImportExtractor) -> None:
    source = "export * from './barrel';"
    result = extractor.extract("src/index.ts", source)
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
    result = extractor.extract(file_path, source)
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
    result = extractor.extract(file_path, source)
    assert len(result) == 1
    module_path, symbol = result[0]
    assert symbol is None
    assert module_path == "src/animal"


# ---------------------------------------------------------------------------
# Package imports passed through unchanged
# ---------------------------------------------------------------------------


def test_package_import_unchanged(extractor: TypeScriptImportExtractor) -> None:
    source = "import React from 'react';"
    result = extractor.extract("src/index.ts", source)
    assert ("react", None) in result


def test_scoped_package_import_unchanged(extractor: TypeScriptImportExtractor) -> None:
    source = "import { Component } from '@angular/core';"
    result = extractor.extract("src/index.ts", source)
    assert ("@angular/core", "Component") in result


# ---------------------------------------------------------------------------
# Aliased imports use original name
# ---------------------------------------------------------------------------


def test_aliased_import_uses_original_name(extractor: TypeScriptImportExtractor) -> None:
    source = "import { Dog as D } from './animals';"
    result = extractor.extract("src/index.ts", source)
    # Must use original name "Dog", not alias "D"
    assert ("animals", "Dog") in result
    assert ("animals", "D") not in result


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_source_returns_empty(extractor: TypeScriptImportExtractor) -> None:
    result = extractor.extract("src/index.ts", "")
    assert result == []


def test_whitespace_only_returns_empty(extractor: TypeScriptImportExtractor) -> None:
    result = extractor.extract("src/index.ts", "   \n  ")
    assert result == []


def test_deduplicates(extractor: TypeScriptImportExtractor) -> None:
    source = "import { Dog } from './animals';\nimport { Dog } from './animals';"
    result = extractor.extract("src/index.ts", source)
    assert result.count(("animals", "Dog")) == 1


# ---------------------------------------------------------------------------
# File type handling
# ---------------------------------------------------------------------------


def test_tsx_file_parses(extractor: TypeScriptImportExtractor) -> None:
    source = "import React from 'react';\nimport { useState } from 'react';"
    result = extractor.extract("src/App.tsx", source)
    assert ("react", None) in result
    assert ("react", "useState") in result


def test_jsx_file_parses(extractor: TypeScriptImportExtractor) -> None:
    source = "import React from 'react';"
    result = extractor.extract("src/App.jsx", source)
    assert ("react", None) in result


def test_js_file_parses(extractor: TypeScriptImportExtractor) -> None:
    source = "const path = require('path');"
    result = extractor.extract("src/index.js", source)
    assert ("path", None) in result


def test_ts_file_parses(extractor: TypeScriptImportExtractor) -> None:
    source = "import { Dog } from './animals';"
    result = extractor.extract("src/index.ts", source)
    assert ("animals", "Dog") in result


# ---------------------------------------------------------------------------
# Mixed import styles in one file
# ---------------------------------------------------------------------------


def test_mixed_import_styles(extractor: TypeScriptImportExtractor) -> None:
    source = "\n".join([
        "import React from 'react';",
        "import { useState, useEffect } from 'react';",
        "import type { FC } from 'react';",
        "export { Dog } from './animals';",
        "export * from './barrel';",
    ])
    result = extractor.extract("src/index.ts", source)
    assert ("react", None) in result
    assert ("react", "useState") in result
    assert ("react", "useEffect") in result
    assert ("react", "FC") in result
    assert ("animals", "Dog") in result
    assert ("barrel", None) in result
