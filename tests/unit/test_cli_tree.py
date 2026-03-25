from __future__ import annotations

from synapse.cli.tree import TreeNode, render_tree, callers_tree, callees_tree, call_depth_tree, hierarchy_tree, trace_tree, entry_points_tree, dependencies_tree


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


class TestCallDepthTree:
    def test_flat_depth_one(self) -> None:
        data = {
            "root": "Service.Process",
            "callees": [
                {"full_name": "Repo.Query", "file_path": "repo.cs", "depth": 1},
                {"full_name": "Logger.Info", "file_path": "log.cs", "depth": 1},
            ],
            "depth_limit": 3,
        }
        root = call_depth_tree(data)
        assert root.label == "Service.Process"
        assert len(root.children) == 2
        assert root.children[0].label == "Repo.Query"
        assert root.children[1].label == "Logger.Info"

    def test_nested_depths(self) -> None:
        data = {
            "root": "A",
            "callees": [
                {"full_name": "B", "file_path": "b.cs", "depth": 1},
                {"full_name": "C", "file_path": "c.cs", "depth": 2},
                {"full_name": "D", "file_path": "d.cs", "depth": 1},
            ],
            "depth_limit": 3,
        }
        root = call_depth_tree(data)
        assert root.label == "A"
        assert len(root.children) == 2
        assert root.children[0].label == "B"
        assert len(root.children[0].children) == 1
        assert root.children[0].children[0].label == "C"
        assert root.children[1].label == "D"
        assert root.children[1].children == []

    def test_deep_chain(self) -> None:
        data = {
            "root": "A",
            "callees": [
                {"full_name": "B", "file_path": "b.cs", "depth": 1},
                {"full_name": "C", "file_path": "c.cs", "depth": 2},
                {"full_name": "D", "file_path": "d.cs", "depth": 3},
            ],
            "depth_limit": 3,
        }
        root = call_depth_tree(data)
        assert root.children[0].label == "B"
        assert root.children[0].children[0].label == "C"
        assert root.children[0].children[0].children[0].label == "D"

    def test_empty_callees(self) -> None:
        data = {"root": "A", "callees": [], "depth_limit": 3}
        root = call_depth_tree(data)
        assert root.label == "A"
        assert root.children == []

    def test_siblings_at_depth_two(self) -> None:
        data = {
            "root": "A",
            "callees": [
                {"full_name": "B", "file_path": "b.cs", "depth": 1},
                {"full_name": "C", "file_path": "c.cs", "depth": 2},
                {"full_name": "D", "file_path": "d.cs", "depth": 2},
            ],
            "depth_limit": 3,
        }
        root = call_depth_tree(data)
        assert root.children[0].label == "B"
        assert len(root.children[0].children) == 2
        assert root.children[0].children[0].label == "C"
        assert root.children[0].children[1].label == "D"


class TestHierarchyTree:
    def test_all_categories(self) -> None:
        data = {
            "parents": [{"full_name": "Base.Entity", "file_path": "base.cs"}],
            "children": [
                {"full_name": "Domain.User", "file_path": "user.cs"},
                {"full_name": "Domain.Order", "file_path": "order.cs"},
            ],
            "implements": [{"full_name": "IRepository", "file_path": "interface.cs"}],
        }
        root = hierarchy_tree("MyClass", data)
        assert root.label == "MyClass"
        assert len(root.children) == 3
        assert root.children[0].label == "Parents"
        assert root.children[0].children[0].label == "Base.Entity"
        assert root.children[1].label == "Children"
        assert len(root.children[1].children) == 2
        assert root.children[2].label == "Implements"
        assert root.children[2].children[0].label == "IRepository"

    def test_empty_categories_omitted(self) -> None:
        data = {"parents": [], "children": [{"full_name": "Child", "file_path": "c.cs"}], "implements": []}
        root = hierarchy_tree("MyClass", data)
        assert len(root.children) == 1
        assert root.children[0].label == "Children"

    def test_all_empty(self) -> None:
        data = {"parents": [], "children": [], "implements": []}
        root = hierarchy_tree("MyClass", data)
        assert root.label == "MyClass"
        assert root.children == []

    def test_missing_implements_key(self) -> None:
        data = {"parents": [{"full_name": "Base", "file_path": "b.cs"}], "children": []}
        root = hierarchy_tree("MyClass", data)
        assert len(root.children) == 1
        assert root.children[0].label == "Parents"


class TestTraceTree:
    def test_single_path(self) -> None:
        data = {"paths": [["A", "B", "C"]], "start": "A", "end": "C"}
        root = trace_tree(data)
        assert root.label == "A"
        assert len(root.children) == 1
        assert root.children[0].label == "B"
        assert root.children[0].children[0].label == "C"

    def test_shared_prefix(self) -> None:
        data = {"paths": [["A", "B", "C"], ["A", "D", "C"]], "start": "A", "end": "C"}
        root = trace_tree(data)
        assert root.label == "A"
        assert len(root.children) == 2
        labels = {c.label for c in root.children}
        assert labels == {"B", "D"}

    def test_fully_shared_prefix_then_diverge(self) -> None:
        data = {"paths": [["A", "B", "C", "D"], ["A", "B", "E", "D"]], "start": "A", "end": "D"}
        root = trace_tree(data)
        assert root.label == "A"
        assert len(root.children) == 1
        b = root.children[0]
        assert b.label == "B"
        assert len(b.children) == 2
        labels = {c.label for c in b.children}
        assert labels == {"C", "E"}

    def test_no_paths(self) -> None:
        data = {"paths": [], "start": "A", "end": "B"}
        root = trace_tree(data)
        assert root.label == "A"
        assert root.children == []

    def test_single_step_path(self) -> None:
        data = {"paths": [["A", "B"]], "start": "A", "end": "B"}
        root = trace_tree(data)
        assert root.label == "A"
        assert len(root.children) == 1
        assert root.children[0].label == "B"


class TestEntryPointsTree:
    def test_single_entry_point(self) -> None:
        data = {
            "entry_points": [
                {"entry": "Controller.Get", "path": ["Controller.Get", "Service.Find", "Repo.Query"]},
            ],
            "target": "Repo.Query",
            "max_depth": 8,
        }
        root = entry_points_tree(data)
        assert root.label == "Repo.Query"
        assert root.children[0].label == "Service.Find"
        assert root.children[0].children[0].label == "Controller.Get"

    def test_multiple_entry_points_shared_intermediate(self) -> None:
        data = {
            "entry_points": [
                {"entry": "Controller.Get", "path": ["Controller.Get", "Service.Find", "Repo.Query"]},
                {"entry": "Controller.Post", "path": ["Controller.Post", "Service.Find", "Repo.Query"]},
            ],
            "target": "Repo.Query",
            "max_depth": 8,
        }
        root = entry_points_tree(data)
        assert root.label == "Repo.Query"
        assert len(root.children) == 1
        assert root.children[0].label == "Service.Find"
        assert len(root.children[0].children) == 2
        labels = {c.label for c in root.children[0].children}
        assert labels == {"Controller.Get", "Controller.Post"}

    def test_no_entry_points(self) -> None:
        data = {"entry_points": [], "target": "Repo.Query", "max_depth": 8}
        root = entry_points_tree(data)
        assert root.label == "Repo.Query"
        assert root.children == []

    def test_direct_caller(self) -> None:
        data = {
            "entry_points": [
                {"entry": "Controller.Get", "path": ["Controller.Get", "Repo.Query"]},
            ],
            "target": "Repo.Query",
            "max_depth": 8,
        }
        root = entry_points_tree(data)
        assert root.label == "Repo.Query"
        assert len(root.children) == 1
        assert root.children[0].label == "Controller.Get"


class TestDependenciesTree:
    def test_flat_depth_one(self) -> None:
        data = [
            {"type": {"full_name": "Logger"}, "depth": 1},
            {"type": {"full_name": "IRepository"}, "depth": 1},
        ]
        root = dependencies_tree("Service", data)
        assert root.label == "Service"
        assert len(root.children) == 2
        assert root.children[0].label == "Logger"
        assert root.children[1].label == "IRepository"

    def test_nested_depths(self) -> None:
        data = [
            {"type": {"full_name": "A"}, "depth": 1},
            {"type": {"full_name": "B"}, "depth": 2},
            {"type": {"full_name": "C"}, "depth": 1},
        ]
        root = dependencies_tree("Root", data)
        assert len(root.children) == 2
        assert root.children[0].label == "A"
        assert root.children[0].children[0].label == "B"
        assert root.children[1].label == "C"

    def test_empty(self) -> None:
        root = dependencies_tree("Root", [])
        assert root.label == "Root"
        assert root.children == []

    def test_with_annotation(self) -> None:
        data = [{"type": {"full_name": "A"}, "depth": 1}]
        root = dependencies_tree("Root", data, annotation="showing 1 of 60")
        assert root.annotation == "showing 1 of 60"
