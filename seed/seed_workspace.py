"""Seed the Locked Door demo: two earlier conversations from two different assistants.

Adapted from neo4j-labs/agent-memory ``examples/claude-code-team-memory``
(Apache-2.0); the unmodified original and the earlier Atlas/Helios version are
in ``../reference/``. Two assistants that never talked to each other each wrote
one conversation into the same workspace, and the only thing both mention is
the pantry:

    A  pantry coordination (Oct 14): Wrenfield Pantry moves its Saturday
       distribution to Alder Branch Library from October 17.
    B  community helpline (Oct 16): a caller is sent to Wrenfield Pantry at
       Brightwater Hall — "site taken from the ... September 2026 edition."

On stage, the audit starts from the locked door (Brightwater Hall, only in B)
and has to cross through Wrenfield Pantry to find the fix (only in A).

All organizations and places are fictional, and no conversation holds personal
details about the caller.

What it does
------------
1. ``create_conversation`` + ``bulk_add_messages`` — A first, then B, so the
   server's order matches the story. Conversations are tagged with
   ``metadata.demo`` and their ids saved to ``seeded.json`` (no secrets), so a
   re-run skips what already exists and re-creates anything missing or empty.
2. Wait for each conversation's extraction to finish.
3. ``verify`` — poll until entity history shows Wrenfield Pantry in both
   conversations, Brightwater Hall only in B and Alder Branch Library only in A,
   each as a single node. This is the check the demo depends on; ``--verify``
   runs it alone.

Usage
-----
::

    ../.venv/bin/python seed_workspace.py            # seed, then verify
    ../.venv/bin/python seed_workspace.py --dry-run  # print the transcripts, write nothing
    ../.venv/bin/python seed_workspace.py --verify   # only re-run the checks

To start over, use a fresh workspace and delete ``seeded.json``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any

from _shared import EXAMPLE_DIR, connect_nams, load_env

from neo4j_agent_memory.core.exceptions import (
    AuthenticationError,
    RateLimitError,
    TransportError,
)

DEMO_TAG = "locked-door"
STATE_FILE = EXAMPLE_DIR / "seeded.json"

#: The one entity both conversations mention, and the two that must stay on one side.
BRIDGE = "Wrenfield Pantry"
ONLY_IN = {
    "Brightwater Hall": "helpline-referral",
    "Alder Branch Library": "pantry-coordination",
}

#: Seeded in this order. Conversation B avoids A's words for the day and hours
#: ("tomorrow morning", not "Saturday, 10 AM to 1 PM") so the pantry stays the
#: only thing extraction can connect them by.
CONVERSATIONS: list[dict[str, Any]] = [
    {
        "key": "pantry-coordination",
        "title": "Pantry coordination",
        "messages": [
            {
                "role": "user",
                "content": (
                    "Pantry coordinator here with an update for Wrenfield Pantry. The hall "
                    "that Wrenfield Pantry normally uses failed its boiler inspection on "
                    "Monday, October 12, 2026, so Wrenfield Pantry cannot hold its Saturday "
                    "distribution there until the boiler is replaced."
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "Recorded for Wrenfield Pantry: its usual hall is unavailable from "
                    "Monday, October 12, 2026, after a failed boiler inspection, until the "
                    "boiler is replaced."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Starting Saturday, October 17, the Wrenfield Pantry Saturday "
                    "distribution moves to the Alder Branch Library community room. Same "
                    "hours, 10 AM to 1 PM, through December 31."
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "Recorded: from Saturday, October 17 through December 31, 2026, "
                    "Wrenfield Pantry holds its Saturday distribution in the Alder Branch "
                    "Library community room, 10 AM to 1 PM."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Alder Branch Library has a step-free entrance and an elevator to the "
                    "community room. Nobody has to show ID."
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "Noted: Alder Branch Library has a step-free entrance and an elevator to "
                    "the community room, and Wrenfield Pantry asks no one for ID."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Please make sure every assistant that gives out pantry locations uses "
                    "the new site from October 17."
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "Saved to shared memory for partner assistants on Wednesday, October 14, "
                    "2026. Wrenfield Pantry Saturday site from October 17 to December 31, "
                    "2026: Alder Branch Library community room, 10 AM to 1 PM."
                ),
            },
        ],
    },
    {
        "key": "helpline-referral",
        "title": "Community helpline",
        "messages": [
            {
                "role": "user",
                "content": "Hi. Where can I get free groceries tomorrow? I don't have a car.",
            },
            {
                "role": "assistant",
                "content": (
                    "Hi, you've reached the Eastside Community Helpline. Today is Friday, "
                    "October 16, 2026. Wrenfield Pantry gives out free groceries tomorrow "
                    "morning at Brightwater Hall. You don't need to give your name."
                ),
            },
            {"role": "user", "content": "Do I need to bring anything or show papers?"},
            {
                "role": "assistant",
                "content": (
                    "Bring bags if you can. Wrenfield Pantry won't ask you for any paperwork."
                ),
            },
            {"role": "user", "content": "Is Brightwater Hall near a bus stop?"},
            {
                "role": "assistant",
                "content": "Yes. Brightwater Hall is one block from the nearest bus stop.",
            },
            {"role": "user", "content": "Great, I'll go tomorrow. Thank you."},
            {
                "role": "assistant",
                "content": (
                    "Referral logged on Friday, October 16, 2026: caller sent to Wrenfield "
                    "Pantry at Brightwater Hall for free groceries the next morning. Site "
                    "taken from the community resource directory, September 2026 edition. "
                    "No personal details recorded."
                ),
            },
        ],
    },
]

#: Off on purpose. NAMS entity resolution is type-strict, so a pre-created
#: ORGANIZATION that extraction types as LOCATION leaves an orphan node with the
#: same name for the agent to find first. If verify reports a split, add the
#: entity here with the type extraction chose and reseed into a fresh workspace.
ENTITIES: list[tuple[str, str, str]] = []

#: Every entity mentioned in more than one conversation. On stage this is the
#: "link or leak?" query; here it catches a second, unplanned connection.
LINK_OR_LEAK = (
    "MATCH (c:Conversation)-[:HAS_MESSAGE]->(:Message)-[:MENTIONS]->(e:Entity) "
    "WITH e, count(DISTINCT c) AS conversations WHERE conversations > 1 "
    "RETURN e.name AS connects, e.type AS type, conversations ORDER BY conversations DESC"
)


def load_state() -> dict[str, Any]:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"demo": DEMO_TAG, "conversations": {}}


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


async def find_existing(client: Any) -> dict[str, str]:
    """Conversation ids already tagged with ``DEMO_TAG``, keyed by conversation key."""
    found: dict[str, str] = {}
    for conv in await client.short_term.list_conversations(limit=200):
        meta = conv.metadata or {}
        if meta.get("demo") == DEMO_TAG and meta.get("key"):
            found.setdefault(meta["key"], str(conv.id))  # newest first
    return found


async def has_messages(client: Any, conversation_id: str) -> bool:
    """False if the conversation is gone (stale seeded.json) or was left empty."""
    try:
        conversation = await client.short_term.get_conversation(conversation_id)
    except Exception:
        return False
    return bool(conversation.messages)


async def seed(client: Any, *, timeout: float) -> int:
    state = load_state()
    live = await find_existing(client)

    # 1. Conversations, A before B --------------------------------------
    for conv in CONVERSATIONS:
        key, title = conv["key"], conv["title"]
        conversation_id = live.get(key) or state["conversations"].get(key, {}).get("id")
        if conversation_id and await has_messages(client, conversation_id):
            print(f"Skipping {title!r}: already seeded as {conversation_id}")
        else:
            if conversation_id:
                print(f"{title!r}: {conversation_id} is missing or empty; seeding it again")
            created = await client.short_term.create_conversation(
                f"{DEMO_TAG}-{key}",
                metadata={"demo": DEMO_TAG, "key": key, "title": title},
            )
            conversation_id = str(created.id)
            stored = await client.short_term.bulk_add_messages(conversation_id, conv["messages"])
            print(f"Conversation {title!r} → {conversation_id} ({len(stored)} messages)")
        state["conversations"][key] = {"id": conversation_id, "title": title}
        save_state(state)

    for name, entity_type, description in ENTITIES:
        if await client.long_term.get_entity_by_name(name) is None:
            entity = await client.long_term.add_entity(name, entity_type, description=description)
            print(f"Entity: {entity.display_name} ({entity.full_type})")

    # 2. Await the asynchronous extraction pipeline ------------------------
    for conv in CONVERSATIONS:
        conversation_id = state["conversations"][conv["key"]]["id"]
        settled = await client.long_term.wait_for_extraction(
            session_id=conversation_id, timeout=timeout
        )
        print(f"Extraction finished for {conv['title']!r}: {settled}")

    state["seeded_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    save_state(state)

    # 3. Prove the cross-conversation path exists --------------------------
    return 0 if await verify(client, state, wait=timeout) else 1


def conversations_in(history: Any, state: dict[str, Any]) -> set[str]:
    """Keys of the seeded conversations an entity's history points into.

    Matches on conversation id, or on the opening words of a seeded message in
    case the history entries carry message text but no conversation id.
    """
    raw = json.dumps(history, default=str, ensure_ascii=False)
    found = set()
    for conv in CONVERSATIONS:
        conversation_id = state["conversations"].get(conv["key"], {}).get("id", "")
        if (conversation_id and conversation_id in raw) or any(
            m["content"][:40] in raw for m in conv["messages"]
        ):
            found.add(conv["key"])
    return found


async def check(client: Any, state: dict[str, Any]) -> tuple[bool, list[str]]:
    titles = {conv["key"]: conv["title"] for conv in CONVERSATIONS}
    lines = ["", "Seeded conversations:"]
    lines += [f"   {c['title']}: {c['id']}" for c in state["conversations"].values()]
    lines += ["", "Where each entity is mentioned (entity history):"]
    problems: list[str] = []

    for name in [BRIDGE, *ONLY_IN]:
        hits = await client.long_term.search_entities(name, limit=10)
        matches = [e for e in hits if e.name.lower() == name.lower()]
        if not matches:
            lines.append(f"   {name}: not found")
            problems.append(f"{name} not found yet")
            continue
        # Resolution is type-strict, so one name can come back as several nodes
        # (e.g. ORGANIZATION and LOCATION). That is survivable as long as one
        # node carries the cross-conversation link the demo needs.
        per_node: list[set[str]] = []
        for entity in matches:
            found = conversations_in(await client.long_term.get_entity_history(entity.id), state)
            per_node.append(found)
            lines.append(
                f"   {name} [{entity.full_type}]: "
                f"{', '.join(titles[k] for k in sorted(found)) or 'no seeded conversation'}"
            )
        if len(matches) > 1:
            lines.append(
                f"   WARN: {name} is {len(matches)} nodes (type-strict resolution; NAMS lists the "
                "pair as a pending SAME_AS in Entity Resolution Review)"
            )
        if name == BRIDGE:
            if not any(found == set(titles) for found in per_node):
                problems.append(f"no single {name} node is in both conversations")
        elif set().union(*per_node) != {ONLY_IN[name]}:
            problems.append(f"{name} should be only in: {titles[ONLY_IN[name]]}")

    try:
        rows = await client.query.cypher(LINK_OR_LEAK)
    except Exception as exc:  # some keys may not have the query endpoint
        lines.append(f"\n(link-or-leak query unavailable: {exc})")
    else:
        shared = ", ".join(f"{r.get('connects')} [{r.get('type')}]" for r in rows) or "none"
        lines.append(f"\nEntities in more than one conversation: {shared}")
        if any(str(r.get("connects", "")).lower() != BRIDGE.lower() for r in rows):
            lines.append(
                "   WARN: something besides the pantry connects them. On stage say "
                "'what connects them', not 'the only thing'."
            )

    if problems:
        lines += ["", "FAIL:"] + [f"   - {p}" for p in problems]
    else:
        lines += ["", f"PASS: {BRIDGE} is the link between the two conversations."]
    return not problems, lines


async def verify(client: Any, state: dict[str, Any], *, wait: float = 0.0) -> bool:
    """Run ``check``, retrying for up to ``wait`` seconds while extraction and embeddings settle."""
    deadline = time.monotonic() + wait
    while True:
        ok, lines = await check(client, state)
        if ok or time.monotonic() >= deadline:
            break
        await asyncio.sleep(5)
    print("\n".join(lines))
    return ok


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seed the Locked Door demo workspace.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the transcripts and exit without writing anything.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Skip seeding; only re-run the cross-conversation checks.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="Seconds to wait for extraction, and then for verify to pass (default: 120).",
    )
    return parser


async def main(argv: list[str] | None = None) -> int:
    load_env()
    args = build_parser().parse_args(argv)

    if args.dry_run:
        for conv in CONVERSATIONS:
            print(f"\n{conv['title']!r} ({len(conv['messages'])} messages):")
            for message in conv["messages"]:
                print(f"   {message['role']:>9}: {message['content'][:88]}…")
        print("\nNothing was written. Re-run without --dry-run to seed.")
        return 0

    client = None
    try:
        client = await connect_nams()
        if args.verify:
            state = load_state()
            if not state["conversations"]:
                print(f"Nothing seeded yet ({STATE_FILE.name} not found).")
                return 1
            return 0 if await verify(client, state) else 1
        return await seed(client, timeout=args.timeout)
    except AuthenticationError as exc:
        print(f"Rejected by NAMS: {exc}\nCheck MEMORY_API_KEY (use a Workspace key).")
        return 1
    except (RateLimitError, TransportError) as exc:
        print(f"Request failed: {exc}")
        return 1
    except Exception as exc:
        print(f"Unexpected error: {exc!r}\nIf seeded.json is from another workspace, delete it and re-run.")
        return 1
    finally:
        if client is not None:
            await client.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
