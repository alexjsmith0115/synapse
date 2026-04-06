from __future__ import annotations

from synapps.plugin import LanguagePlugin
from synapps.plugin.java import JavaPlugin


def test_create_call_extractor_returns_none():
    """create_call_extractor() returning None is the migration gate for ReferencesResolver dispatch (LANG-03)."""
    extractor = JavaPlugin().create_call_extractor()
    assert extractor is None


def test_name_returns_java():
    assert JavaPlugin().name == "java"


def test_is_language_plugin():
    assert isinstance(JavaPlugin(), LanguagePlugin)
