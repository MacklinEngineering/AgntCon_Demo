#!/usr/bin/env bash
# Launches the on-stage agent. Use this exact command for every rehearsal and
# for the show, so timing in rehearsal is timing on stage.
#   - Sonnet at medium effort: answers in ~30-40 s and reliably reads both
#     conversations (low effort was faster but skipped the full read).
#   - No built-in tools and no tool-search step: only the four memory tools
#     allowed in .claude/settings.json; the other sixteen are denied, which
#     removes them from the model's context.
#   - dontAsk: anything not allowed is refused silently, so no permission
#     prompt can reach the projector.
set -euo pipefail
cd "$(dirname "$0")"
export ENABLE_TOOL_SEARCH=false   # memory tools load up front; no ToolSearch turn
export DISABLE_AUTOUPDATER=1      # no Claude Code self-updates before the show
export MCP_TIMEOUT=60000          # server start, incl. its NAMS probe, on venue Wi-Fi
export MCP_TOOL_TIMEOUT=20000     # a hung NAMS call fails in 20 s instead of stalling
exec claude \
  --model "${STAGE_MODEL:-sonnet}" \
  --effort "${STAGE_EFFORT:-medium}" \
  --tools "" \
  --strict-mcp-config --mcp-config .mcp.json \
  --settings .claude/settings.json \
  --permission-mode dontAsk \
  --allowedTools "mcp__agent-memory__memory_get_conversation,mcp__agent-memory__memory_search,mcp__agent-memory__memory_get_entity_history" \
  "$@"
