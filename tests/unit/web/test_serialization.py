from __future__ import annotations

from unittest.mock import MagicMock

from synapps.web.serialization import serialize_result


def test_plain_dict_passthrough() -> None:
    data = {"a": 1, "b": "hello"}
    assert serialize_result(data) == {"a": 1, "b": "hello"}


def test_neo4j_node_converted_to_dict() -> None:
    node = MagicMock()
    node.element_id = "4:abc:1"
    node.items.return_value = [("name", "MyClass"), ("kind", "Class")]

    result = serialize_result(node)

    assert result == {"name": "MyClass", "kind": "Class"}


def test_nested_list_of_dicts() -> None:
    data = [{"x": 1}, {"x": 2}]
    assert serialize_result(data) == [{"x": 1}, {"x": 2}]


def test_none_passthrough() -> None:
    assert serialize_result(None) is None


def test_primitive_passthrough() -> None:
    assert serialize_result(42) == 42
    assert serialize_result(3.14) == 3.14
    assert serialize_result(True) is True
    assert serialize_result("hello") == "hello"


def test_nested_neo4j_node_in_dict() -> None:
    node = MagicMock()
    node.element_id = "4:abc:1"
    node.items.return_value = [("name", "MyClass")]

    data = {"symbol": node, "count": 5}
    result = serialize_result(data)

    assert result == {"symbol": {"name": "MyClass"}, "count": 5}


def test_list_with_neo4j_nodes() -> None:
    node = MagicMock()
    node.element_id = "4:abc:2"
    node.items.return_value = [("full_name", "Foo.Bar")]

    result = serialize_result([node, "plain"])

    assert result == [{"full_name": "Foo.Bar"}, "plain"]
