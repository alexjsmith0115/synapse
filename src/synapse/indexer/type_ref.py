from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TypeRef:
    owner_full_name: str
    type_name: str
    line: int
    col: int
    ref_kind: str  # "parameter", "return_type", "property_type", "field_type"
