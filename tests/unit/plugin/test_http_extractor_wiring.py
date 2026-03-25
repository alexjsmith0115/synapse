from __future__ import annotations

from synapse.plugin.csharp import CSharpPlugin
from synapse.plugin.typescript import TypeScriptPlugin
from synapse.plugin.python import PythonPlugin
from synapse.plugin.java import JavaPlugin


def test_csharp_plugin_has_http_extractor() -> None:
    plugin = CSharpPlugin()
    extractor = plugin.create_http_extractor()
    assert extractor is not None


def test_typescript_plugin_has_http_extractor() -> None:
    plugin = TypeScriptPlugin()
    extractor = plugin.create_http_extractor()
    assert extractor is not None


def test_python_plugin_has_http_extractor() -> None:
    plugin = PythonPlugin()
    extractor = plugin.create_http_extractor()
    assert extractor is not None


def test_java_plugin_no_http_extractor_yet() -> None:
    plugin = JavaPlugin()
    assert not hasattr(plugin, "create_http_extractor")
