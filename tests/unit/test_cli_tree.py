from __future__ import annotations

from synapse.cli.tree import TreeNode, render_tree, callers_tree, callees_tree


class TestRenderTree:
    def test_single_node_no_children(self) -> None:
        root = TreeNode(label="Root", children=[])
        assert render_tree(root) == "Root"

    def test_single_node_with_annotation(self) -> None:
        root = TreeNode(label="Root", children=[], annotation="info")
        assert render_tree(root) == "Root [info]"

    def test_flat_children(self) -> None:
        root = TreeNode(label="Root", children=[
            TreeNode(label="A", children=[]),
            TreeNode(label="B", children=[]),
            TreeNode(label="C", children=[]),
        ])
        expected = "\n".join([
            "Root",
            "├── A",
            "├── B",
            "└── C",
        ])
        assert render_tree(root) == expected

    def test_nested_children(self) -> None:
        root = TreeNode(label="Root", children=[
            TreeNode(label="A", children=[
                TreeNode(label="A1", children=[]),
            ]),
            TreeNode(label="B", children=[]),
        ])
        expected = "\n".join([
            "Root",
            "├── A",
            "│   └── A1",
            "└── B",
        ])
        assert render_tree(root) == expected

    def test_deep_nesting(self) -> None:
        root = TreeNode(label="Root", children=[
            TreeNode(label="A", children=[
                TreeNode(label="B", children=[
                    TreeNode(label="C", children=[
                        TreeNode(label="D", children=[]),
                    ]),
                ]),
            ]),
        ])
        expected = "\n".join([
            "Root",
            "└── A",
            "    └── B",
            "        └── C",
            "            └── D",
        ])
        assert render_tree(root) == expected

    def test_child_with_annotation(self) -> None:
        root = TreeNode(label="Root", children=[
            TreeNode(label="A", children=[], annotation="depth 2"),
        ])
        expected = "\n".join([
            "Root",
            "└── A [depth 2]",
        ])
        assert render_tree(root) == expected

    def test_complex_tree(self) -> None:
        root = TreeNode(label="Service.Process()", children=[
            TreeNode(label="Repo.Query()", children=[
                TreeNode(label="Db.Execute()", children=[]),
            ]),
            TreeNode(label="Logger.Info()", children=[]),
            TreeNode(label="Cache.Get()", children=[
                TreeNode(label="Redis.Connect()", children=[]),
                TreeNode(label="Redis.Read()", children=[]),
            ]),
        ])
        expected = "\n".join([
            "Service.Process()",
            "├── Repo.Query()",
            "│   └── Db.Execute()",
            "├── Logger.Info()",
            "└── Cache.Get()",
            "    ├── Redis.Connect()",
            "    └── Redis.Read()",
        ])
        assert render_tree(root) == expected


class TestCallersTree:
    def test_basic(self) -> None:
        data = [
            {"full_name": "Controller.GetUser", "file_path": "controller.cs", "line": 10},
            {"full_name": "Handler.Process", "file_path": "handler.cs", "line": 20},
        ]
        root = callers_tree("Service.FindUser", data)
        assert root.label == "Service.FindUser"
        assert len(root.children) == 2
        assert root.children[0].label == "Controller.GetUser"
        assert root.children[1].label == "Handler.Process"
        assert root.children[0].children == []

    def test_empty_list(self) -> None:
        root = callers_tree("Service.FindUser", [])
        assert root.label == "Service.FindUser"
        assert root.children == []

    def test_with_annotation(self) -> None:
        data = [{"full_name": "A", "file_path": "a.cs", "line": 1}]
        root = callers_tree("Target", data, annotation="showing 1 of 50")
        assert root.annotation == "showing 1 of 50"

    def test_single_caller(self) -> None:
        data = [{"full_name": "Caller.Method", "file_path": "caller.cs", "line": 5}]
        root = callers_tree("Target.Method", data)
        assert len(root.children) == 1
        assert root.children[0].label == "Caller.Method"


class TestCalleesTree:
    def test_basic(self) -> None:
        data = [
            {"full_name": "Repo.Query", "name": "Query", "file_path": "repo.cs", "line": 10},
            {"full_name": "Logger.Info", "name": "Info", "file_path": "logger.cs", "line": 20},
        ]
        root = callees_tree("Service.FindUser", data)
        assert root.label == "Service.FindUser"
        assert len(root.children) == 2
        assert root.children[0].label == "Repo.Query"
        assert root.children[1].label == "Logger.Info"

    def test_empty_list(self) -> None:
        root = callees_tree("Service.FindUser", [])
        assert root.label == "Service.FindUser"
        assert root.children == []
