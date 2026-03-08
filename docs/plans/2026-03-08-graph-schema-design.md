# Graph Schema Design

**Date:** 2026-03-08
**Status:** Approved

## Overview

Defines the complete node and edge schema for the Synapse graph, covering all relationships needed to represent a codebase's physical structure, logical structure, type hierarchy, and call graph. Designed to be language-agnostic — terminology avoids language-specific concepts (e.g. "Package" rather than "Namespace").

---

## Node Labels

| Label | Represents | Notes |
|---|---|---|
| `Repository` | Root of the project | |
| `Directory` | Filesystem directory | |
| `File` | Source file | |
| `Package` | Organizational unit (namespace, package, module) | Replaces `Namespace`; language-agnostic |
| `Class` | Class, abstract class, enum, record, struct | `kind` property retained as discriminator |
| `Interface` | Interface | Promoted from `Class {kind:'interface'}` to first-class label |
| `Method` | Function or method | |
| `Property` | Property or accessor | |
| `Field` | Field or member variable | |

---

## Edge Types

### Physical containment (filesystem)

Models where code lives on disk.

```
Directory  -[CONTAINS]-> Directory
Directory  -[CONTAINS]-> File
File       -[CONTAINS]-> Class | Interface      (top-level types only)
Class      -[CONTAINS]-> Method | Property | Field
Interface  -[CONTAINS]-> Method | Property
```

> `File -[CONTAINS]->` must use the hierarchical LSP symbol tree (`root_symbols`/`children`), not the flat `iter_symbols()` iterator, to avoid incorrectly linking File to nested symbols.

### Logical containment (code structure)

Models how code is organized by the language's module/package system.

```
Package  -[CONTAINS]-> Package
Package  -[CONTAINS]-> Class | Interface
```

Both hierarchies share the `CONTAINS` edge type. The source node type disambiguates:
- `(File)-[:CONTAINS]->(Class)` — physical
- `(Package)-[:CONTAINS]->(Class)` — logical

### Import

```
File  -[IMPORTS]-> Package
```

### Type relationships

```
Class      -[INHERITS]->   Class
Interface  -[INHERITS]->   Interface
Class      -[IMPLEMENTS]-> Interface
Method     -[OVERRIDES]->  Method
```

### Call graph

```
Method  -[CALLS]->  Method
```

Resolved via Phase 2 (tree-sitter + LSP `request_defining_symbol`). Existing implementation unchanged.

---

## Design Decisions

**Single `CONTAINS` edge type for both hierarchies.** Source node type is always sufficient to disambiguate physical vs. logical containment. A separate edge type (e.g. `OWNS`) would add cognitive overhead without a practical query benefit.

**`Interface` promoted to first-class label.** Previously stored as `Class {kind:'interface'}`, which required kind-filtering in every query involving interfaces. Separate label enables clean pattern matching: `(c:Class)-[:IMPLEMENTS]->(i:Interface)`.

**`Package` replaces `Namespace`.** Language-agnostic term that maps to C# namespaces, Java/Go packages, and Python packages without implying language-specific semantics. Multi-language support is an explicit goal.

**`base_types` population is currently broken.** `CSharpLSPAdapter._convert()` never sets `base_types` on `IndexSymbol`, so `INHERITS` and `IMPLEMENTS` edges are no-ops today. This must be fixed as part of implementing the new schema.

---

## Out of Scope

- `REFERENCES` edge (field/parameter type dependencies) — defined in `edges.py` but excluded from this design; revisit if type dependency queries become needed.
- External package/dependency nodes (e.g. NuGet, npm) — `File -[IMPORTS]-> Package` targets only packages within the indexed repository.
