from __future__ import annotations


def serialize_result(obj: object) -> object:
    """Convert neo4j Node/Relationship objects to plain Python dicts.

    SynappsService methods may return neo4j driver types that are not
    JSON-serializable. This function walks the result and converts them
    to plain dicts/lists/primitives suitable for FastAPI JSON responses.
    """
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj

    # neo4j Node and Relationship expose .items() and have element_id
    if hasattr(obj, "element_id") and hasattr(obj, "items"):
        return dict(obj.items())

    if isinstance(obj, dict):
        return {k: serialize_result(v) for k, v in obj.items()}

    if isinstance(obj, (list, tuple)):
        return [serialize_result(item) for item in obj]

    return obj
