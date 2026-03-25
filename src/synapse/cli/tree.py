from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TreeNode:
    label: str
    children: list[TreeNode] = field(default_factory=list)
    annotation: str | None = None


def render_tree(root: TreeNode) -> str:
    lines: list[str] = []
    label = root.label
    if root.annotation:
        label += f" [{root.annotation}]"
    lines.append(label)
    _render_children(lines, root.children, prefix="")
    return "\n".join(lines)


def _render_children(lines: list[str], children: list[TreeNode], prefix: str) -> None:
    for i, child in enumerate(children):
        is_last = i == len(children) - 1
        connector = "└── " if is_last else "├── "
        label = child.label
        if child.annotation:
            label += f" [{child.annotation}]"
        lines.append(f"{prefix}{connector}{label}")
        extension = "    " if is_last else "│   "
        _render_children(lines, child.children, prefix + extension)


def _flat_tree(symbol_name: str, data: list[dict], annotation: str | None = None) -> TreeNode:
    children = [TreeNode(label=item.get("full_name", "?")) for item in data]
    return TreeNode(label=symbol_name, children=children, annotation=annotation)


def callers_tree(symbol_name: str, data: list[dict], annotation: str | None = None) -> TreeNode:
    return _flat_tree(symbol_name, data, annotation)


def callees_tree(symbol_name: str, data: list[dict], annotation: str | None = None) -> TreeNode:
    return _flat_tree(symbol_name, data, annotation)
