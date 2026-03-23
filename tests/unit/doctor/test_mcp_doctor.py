from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from synapse.doctor.base import CheckResult


_ALL_CHECKS = [
    ("DockerDaemonCheck", "Docker daemon", "core"),
    ("MemgraphBoltCheck", "Memgraph", "core"),
    ("DotNetCheck", ".NET SDK", "csharp"),
    ("CSharpLSCheck", "csharp-ls", "csharp"),
    ("NodeCheck", "Node.js", "typescript"),
    ("TypeScriptLSCheck", "typescript-language-server", "typescript"),
    ("PythonCheck", "Python 3", "python"),
    ("PylspCheck", "pylsp", "python"),
    ("JavaCheck", "Java", "java"),
    ("JdtlsCheck", "Eclipse JDT LS", "java"),
]

_VALID_STATUSES = {"pass", "warn", "fail"}


def _make_result(name: str, status: str = "pass", group: str = "core", fix: str | None = None) -> CheckResult:
    return CheckResult(name=name, status=status, detail="ok", fix=fix, group=group)


def _invoke_check_environment() -> list:
    """Patch all 10 check classes in synapse.mcp.tools and call check_environment."""
    registered = {}
    mcp = MagicMock()
    mcp.tool.return_value = lambda f: registered.__setitem__(f.__name__, f) or f

    with ExitStack() as stack:
        mocks = [
            stack.enter_context(patch(f"synapse.mcp.tools.{cls}"))
            for cls, _, _ in _ALL_CHECKS
        ]
        for mock, (_, name, group) in zip(mocks, _ALL_CHECKS):
            mock.return_value.run.return_value = _make_result(name, group=group)

        from synapse.mcp.tools import register_tools
        register_tools(mcp, MagicMock())
        return registered["check_environment"]()


def test_check_environment_returns_a_list() -> None:
    result = _invoke_check_environment()
    assert isinstance(result, list), f"Expected list, got {type(result)}"


def test_check_environment_items_have_required_keys() -> None:
    result = _invoke_check_environment()
    assert len(result) > 0
    for item in result:
        assert set(item.keys()) == {"name", "status", "detail", "fix"}, (
            f"Item has unexpected keys: {set(item.keys())}"
        )


def test_check_environment_status_values_are_valid() -> None:
    result = _invoke_check_environment()
    for item in result:
        assert item["status"] in _VALID_STATUSES, (
            f"Invalid status {item['status']!r} for check {item['name']!r}"
        )


def test_check_environment_returns_ten_items() -> None:
    # One result per check — must match the 10-check list
    result = _invoke_check_environment()
    assert len(result) == 10, f"Expected 10 items, got {len(result)}"


def test_check_environment_fix_none_is_present_not_missing() -> None:
    """fix=None must appear as a key in the dict (not absent)."""
    registered = {}
    mcp = MagicMock()
    mcp.tool.return_value = lambda f: registered.__setitem__(f.__name__, f) or f

    with ExitStack() as stack:
        mocks = [
            stack.enter_context(patch(f"synapse.mcp.tools.{cls}"))
            for cls, _, _ in _ALL_CHECKS
        ]
        for mock, (_, name, group) in zip(mocks, _ALL_CHECKS):
            mock.return_value.run.return_value = _make_result(name, group=group, fix=None)

        from synapse.mcp.tools import register_tools
        register_tools(mcp, MagicMock())
        result = registered["check_environment"]()

    for item in result:
        assert "fix" in item, f"Key 'fix' missing from {item!r}"
        assert item["fix"] is None


def test_check_environment_result_is_not_a_string() -> None:
    """Result must be list[dict], not a formatted/Rich string."""
    result = _invoke_check_environment()
    assert not isinstance(result, str), "check_environment must not return a string"


def test_check_environment_uses_doctor_service() -> None:
    """DoctorService.run must be called when check_environment is invoked."""
    registered = {}
    mcp = MagicMock()
    mcp.tool.return_value = lambda f: registered.__setitem__(f.__name__, f) or f

    with ExitStack() as stack:
        mocks = [
            stack.enter_context(patch(f"synapse.mcp.tools.{cls}"))
            for cls, _, _ in _ALL_CHECKS
        ]
        for mock, (_, name, group) in zip(mocks, _ALL_CHECKS):
            mock.return_value.run.return_value = _make_result(name, group=group)

        mock_service_cls = stack.enter_context(patch("synapse.mcp.tools.DoctorService"))
        mock_service_instance = MagicMock()
        mock_service_instance.run.return_value = MagicMock(checks=[])
        mock_service_cls.return_value = mock_service_instance

        from synapse.mcp.tools import register_tools
        register_tools(mcp, MagicMock())
        registered["check_environment"]()

    mock_service_instance.run.assert_called_once()
