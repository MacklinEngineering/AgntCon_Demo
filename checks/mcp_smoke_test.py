"""Walk the on-stage audit path through the real MCP server, without a model.

Spawns ../stage/memory-mcp.sh over stdio (the command the agent uses) and calls
the four allowed tools in the order ../stage/CLAUDE.md gives the agent:
Brightwater Hall → helpline conversation → Wrenfield Pantry → pantry
coordination conversation → the move to Alder Branch Library → decision record.
It also checks that every tool the server exposes is either allowed or denied in
../stage/.claude/settings.json. If this passes, the only untested piece on
stage is the model.

    ../.venv/bin/python mcp_smoke_test.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

DEMO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DEMO / "seed"))

from seed_workspace import BRIDGE, STATE_FILE, conversations_in  # noqa: E402

SERVER = DEMO / "stage" / "memory-mcp.sh"
SETTINGS = DEMO / "stage" / ".claude" / "settings.json"
START = "Brightwater Hall"

failures: list[str] = []


def check(ok: bool, label: str, detail: str = "") -> bool:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))
    if not ok:
        failures.append(label)
    return ok


async def call(session: ClientSession, tool: str, **arguments: Any) -> dict[str, Any]:
    result = await session.call_tool(tool, arguments)
    text = "".join(getattr(part, "text", "") for part in result.content)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {"error": text or "empty response"}
    return parsed if isinstance(parsed, dict) else {"value": parsed}


async def find_entities(session: ClientSession, name: str) -> list[dict[str, Any]]:
    """Every exact-name match from an entities-only search (type-strict resolution can split one name)."""
    found = await call(session, "memory_search", query=name, memory_types=["entities"])
    entities = (found.get("results") or {}).get("entities") or []
    return [e for e in entities if str(e.get("name", "")).lower() == name.lower()]


async def read_conversation(session: ClientSession, conversation_id: str) -> str:
    conversation = await call(session, "memory_get_conversation", session_id=conversation_id)
    return " ".join(str(m.get("content", "")) for m in conversation.get("messages", []))


async def main() -> int:
    if not STATE_FILE.exists():
        print(f"Seed first: {STATE_FILE} not found.")
        return 1
    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    helpline = state["conversations"]["helpline-referral"]["id"]
    pantry = state["conversations"]["pantry-coordination"]["id"]
    permissions = json.loads(SETTINGS.read_text(encoding="utf-8"))["permissions"]

    params = StdioServerParameters(command=str(SERVER), args=[])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            print("1. Tool surface vs stage permissions")
            names = {tool.name for tool in (await session.list_tools()).tools}
            ruled = set(permissions["allow"]) | set(permissions["deny"])
            unlisted = sorted(n for n in names if f"mcp__agent-memory__{n}" not in ruled)
            allowed = sorted(n for n in names if f"mcp__agent-memory__{n}" in permissions["allow"])
            check(
                not unlisted,
                f"all {len(names)} tools are allowed or denied",
                f"unlisted: {', '.join(unlisted)}" if unlisted else f"allowed: {', '.join(allowed)}",
            )

            print(f"2. Start where the question starts: {START}")
            starts = await find_entities(session, START)
            if check(bool(starts), f"memory_search finds {START}", f"{len(starts)} match(es)"):
                seen: set[str] = set()
                for entity in starts:
                    history = await call(session, "memory_get_entity_history", entity_id=entity["id"])
                    seen |= conversations_in(history, state)
                check(seen == {"helpline-referral"}, f"{START} is mentioned only in the helpline conversation")

            print("3. Read the helpline conversation")
            text = await read_conversation(session, helpline)
            check(
                BRIDGE in text and "September 2026 edition" in text,
                "it sends the caller to Wrenfield Pantry from the September 2026 directory",
            )

            print(f"4. Cross through {BRIDGE}")
            bridge = None
            candidates = await find_entities(session, BRIDGE)
            if check(bool(candidates), f"memory_search finds {BRIDGE}", f"{len(candidates)} match(es)"):
                for entity in candidates:
                    history = await call(session, "memory_get_entity_history", entity_id=entity["id"])
                    if conversations_in(history, state) == {"helpline-referral", "pantry-coordination"}:
                        bridge = entity
                check(bridge is not None, f"one {BRIDGE} node's history spans both conversations")

            print("5. Read the pantry coordination conversation")
            text = await read_conversation(session, pantry)
            check(
                "Alder Branch Library" in text and "October 17" in text,
                "it records the move to Alder Branch Library from October 17",
            )

            print("6. Decision record (app-recorded provenance)")
            if bridge is not None:
                provenance = await call(session, "memory_get_entity_provenance", entity_id=bridge["id"])
                # NAMS answers {entityId, provenance: [...]}; the client docs say {entityId, steps: [...]}.
                check(
                    provenance.get("provenance", provenance.get("steps")) == [],
                    f"no recorded steps for {BRIDGE} (the closing line depends on this)",
                    json.dumps(provenance)[:160],
                )

    print("\nALL PASS" if not failures else f"\n{len(failures)} FAILED: {'; '.join(failures)}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
