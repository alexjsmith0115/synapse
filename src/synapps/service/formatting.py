from __future__ import annotations


def _p(node) -> dict:
    """Extract properties from a neo4j graph Node (including labels) or pass through a plain dict."""
    if hasattr(node, "element_id"):
        result = dict(node)
        if node.labels:
            result["_labels"] = list(node.labels)
        return result
    return node


def _slim(node, *fields: str) -> dict:
    """Extract only the specified fields from a neo4j Node or plain dict."""
    if hasattr(node, "element_id"):
        return {f: node.get(f) for f in fields if node.get(f) is not None}
    if isinstance(node, dict):
        return {f: node[f] for f in fields if f in node}
    return {}


def _apply_limit(items: list, limit: int) -> list | dict:
    """Return items directly if within limit, or a truncated wrapper if over."""
    if limit <= 0 or len(items) <= limit:
        return items
    return {"results": items[:limit], "_total": len(items), "_truncated": True}


def _short_ref(full_name: str) -> str:
    """Shorten a fully qualified reference to Class.method form.

    'com.example.Foo.bar(int, String)' -> 'Foo.bar'
    'com.example.Foo' -> 'Foo'
    """
    # Strip parameter signature
    paren = full_name.find("(")
    name = full_name[:paren] if paren > 0 else full_name
    parts = name.rsplit(".", 2)
    if len(parts) >= 2:
        return f"{parts[-2]}.{parts[-1]}"
    return parts[-1]


def _member_line(m) -> str:
    mp = _p(m)
    sig = mp.get("signature") or mp.get("type_name") or ""
    return f"  {mp.get('name', '?')}: {sig}"
