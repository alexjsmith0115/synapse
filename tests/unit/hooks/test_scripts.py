"""Tests for hook script string constants."""
from __future__ import annotations


class TestScriptConstants:
    def test_common_script_defines_is_synapps_project(self) -> None:
        from synapps.hooks.scripts import COMMON_SH

        assert "is_synapps_project" in COMMON_SH

    def test_common_script_defines_emit_reminder(self) -> None:
        from synapps.hooks.scripts import COMMON_SH

        assert "emit_reminder" in COMMON_SH

    def test_common_script_checks_config_json(self) -> None:
        from synapps.hooks.scripts import COMMON_SH

        assert ".synapps/config.json" in COMMON_SH

    def test_claude_gate_sources_common(self) -> None:
        from synapps.hooks.scripts import CLAUDE_GATE_SH

        assert "common.sh" in CLAUDE_GATE_SH

    def test_claude_gate_exits_zero(self) -> None:
        from synapps.hooks.scripts import CLAUDE_GATE_SH

        assert "exit 0" in CLAUDE_GATE_SH

    def test_cursor_gate_sources_common(self) -> None:
        from synapps.hooks.scripts import CURSOR_GATE_SH

        assert "common.sh" in CURSOR_GATE_SH

    def test_copilot_gate_emits_allow_json(self) -> None:
        from synapps.hooks.scripts import COPILOT_GATE_SH

        assert '"permissionDecision":"allow"' in COPILOT_GATE_SH

    def test_copilot_gate_reads_tool_name(self) -> None:
        from synapps.hooks.scripts import COPILOT_GATE_SH

        assert "toolName" in COPILOT_GATE_SH

    def test_all_scripts_have_shebang(self) -> None:
        from synapps.hooks.scripts import (
            COMMON_SH,
            CLAUDE_GATE_SH,
            CURSOR_GATE_SH,
            COPILOT_GATE_SH,
        )

        for script in [COMMON_SH, CLAUDE_GATE_SH, CURSOR_GATE_SH, COPILOT_GATE_SH]:
            assert script.startswith("#!/bin/bash\n")
