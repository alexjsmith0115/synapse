"""Bash gate script content for pre-tool hooks.

Each constant holds the full content of a script that gets written to
~/.synapps/hooks/ during ``synapps install``.
"""
from __future__ import annotations

COMMON_SH = """\
#!/bin/bash
# Synapps pre-tool hook helper — sourced by agent-specific gate scripts.

is_synapps_project() {
  local dir="$PWD"
  while [ "$dir" != "/" ]; do
    if [ -f "$dir/.synapps/config.json" ]; then
      return 0
    fi
    dir="$(dirname "$dir")"
  done
  return 1
}

emit_reminder() {
  echo "Reminder: This project is indexed by Synapps. For code discovery," >&2
  echo "prefer Synapps MCP tools (search_symbols, get_context_for, find_usages," >&2
  echo "find_callees) over grep/file search. They return structured results" >&2
  echo "with relationships, callers, and dependencies." >&2
}
"""

CLAUDE_GATE_SH = """\
#!/bin/bash
# Synapps advisory hook for Claude Code (PreToolUse).
source "$(dirname "$0")/common.sh"
if is_synapps_project; then
  emit_reminder
fi
exit 0
"""

CURSOR_GATE_SH = """\
#!/bin/bash
# Synapps advisory hook for Cursor (preToolUse).
source "$(dirname "$0")/common.sh"
if is_synapps_project; then
  emit_reminder
fi
exit 0
"""

COPILOT_GATE_SH = """\
#!/bin/bash
# Synapps advisory hook for GitHub Copilot (preToolUse).
# Copilot has no matcher field — tool name filtering happens here.
source "$(dirname "$0")/common.sh"

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | grep -o '"toolName": *"[^"]*"' | grep -o '"[^"]*"$' | tr -d '"')

if is_synapps_project && echo "$TOOL_NAME" | grep -qiE "grep|glob|find|search|read_file"; then
  emit_reminder
fi

echo '{"permissionDecision":"allow"}'
exit 0
"""
