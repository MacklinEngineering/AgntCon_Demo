#!/usr/bin/env bash
# Launches the open-source neo4j-agent-memory MCP server against the NAMS
# workspace. Reads MEMORY_API_KEY from ../seed/.env so the editor does not need
# it exported. stdout is the MCP channel: nothing here may print to it.
set -euo pipefail
DEMO="$(cd "$(dirname "$0")/.." && pwd)"
set -a
# shellcheck disable=SC1091
source "$DEMO/seed/.env"
set +a
exec "$DEMO/.venv/bin/neo4j-agent-memory" mcp serve \
  --backend nams \
  --transport stdio \
  --profile extended \
  --session-strategy per_conversation \
  --no-auto-preferences
