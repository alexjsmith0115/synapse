from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

import synapps

_ROOT = Path(__file__).resolve().parents[2]


def _load_pyproject() -> dict:
    with open(_ROOT / "pyproject.toml", "rb") as f:
        return tomllib.load(f)


def test_pyproject_name() -> None:
    data = _load_pyproject()
    assert data["project"]["name"] == "synapps-mcp"


def test_pyproject_version() -> None:
    data = _load_pyproject()
    assert data["project"]["version"] == "1.4.1"


def test_pyproject_readme() -> None:
    data = _load_pyproject()
    assert data["project"]["readme"] == "PYPI_README.md"


def test_pyproject_urls() -> None:
    data = _load_pyproject()
    urls = data["project"]["urls"]
    for key in ("Homepage", "Source", "Issues", "Changelog"):
        assert key in urls, f"Missing project.urls.{key}"


def test_version_attribute() -> None:
    assert hasattr(synapps, "__version__")
    assert isinstance(synapps.__version__, str)
    assert len(synapps.__version__) > 0


def test_version_not_dev() -> None:
    assert synapps.__version__ != "dev", (
        "__version__ resolved to 'dev' — run 'uv sync' after pyproject.toml rename"
    )


def test_wheel_packages_include_solidlsp() -> None:
    data = _load_pyproject()
    packages = data["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    assert "src/solidlsp" in packages


def test_publish_workflow_exists() -> None:
    workflow = _ROOT / ".github" / "workflows" / "publish.yml"
    assert workflow.exists(), f"Expected {workflow} to exist"


def test_pypi_readme_exists() -> None:
    readme = _ROOT / "PYPI_README.md"
    assert readme.exists(), f"Expected {readme} to exist"
    content = readme.read_text()
    assert "pip install synapps-mcp" in content
