"""Seed the demo workspace with two earlier conversations that share one entity.

Adapted from neo4j-labs/agent-memory ``examples/claude-code-team-memory``
(Apache-2.0); the unmodified original is in ``../reference/``. The original
writes one decision log into one conversation. This version splits it into two
conversations so that the only route from one to the other runs through the
entity they share, Atlas:

    Helios planning:  "Helios reads customer account data from Atlas"   (ADR-009)
    Atlas review:     "Atlas runs in Frankfurt only — EU residency"     (ADR-005)

The live question on stage ("can Helios cache customer data in us-east-1?")
starts in the Helios conversation, and the answer is in the Atlas one.

What it does
------------
1. ``add_entity`` — Atlas and Helios first, so extraction resolves onto them.
2. ``create_conversation`` + ``bulk_add_messages`` — one call per conversation,
   tagged with ``metadata.demo`` so a re-run skips what already exists.
3. ``wait_for_extraction`` — NAMS extracts asynchronously; await it per
   conversation instead of sleeping.
4. ``verify`` — read each entity's mention history back and confirm that one
   entity really does link both conversations. This is the check the demo
   depends on, so it is also available on its own as ``--verify``.

Conversation ids are written to ``seeded.json`` (no secrets) for
``../queries/inspect_graph.py`` and ``../stage/smoke_test.py``.

Usage
-----
::

    ../.venv/bin/python seed_workspace.py            # seed, then verify
    ../.venv/bin/python seed_workspace.py --dry-run  # print the transcripts, write nothing
    ../.venv/bin/python seed_workspace.py --verify   # only re-run the checks

To start over, use a fresh workspace (or delete the two conversations in the
console) and delete ``seeded.json``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from _shared import EXAMPLE_DIR, connect_nams, load_env

from neo4j_agent_memory.core.exceptions import (
    AuthenticationError,
    RateLimitError,
    TransportError,
)

DEMO_TAG = "wake-up-neo"
STATE_FILE = EXAMPLE_DIR / "seeded.json"

#: Two conversations. Atlas is the only entity both mention; Helios appears only
#: in the second and Frankfurt only in the first, so getting from the question
#: (Helios) to the answer (Frankfurt) means crossing conversations via Atlas.
#: Key sentences say "Atlas" on its own rather than "the Atlas API", so the
#: extractor resolves both mentions onto the same node.
CONVERSATIONS: list[dict[str, Any]] = [
    {
        "key": "atlas-review",
        "title": "Atlas platform review",
        "expected": ["Alice Nakamura", "Frankfurt"],
        "messages": [
            {
                "role": "user",
                "content": (
                    "Alice Nakamura: ADR-001 — we standardise on Neo4j 5.26 LTS for "
                    "Atlas. 5.26 is the long-term-support line, so we get security "
                    "patches without tracking monthly releases."
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "Recorded ADR-001: Atlas uses Neo4j 5.26 LTS. Rationale: LTS patch "
                    "cadence. Owner: Alice Nakamura."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Bob Okonkwo: ADR-002 — the Atlas ingest worker talks to Neo4j over "
                    "Bolt with the async driver. We rejected the HTTP API because batch "
                    "writes were three times slower in our load test."
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "Recorded ADR-002: Bolt + async driver for the Atlas ingest worker. "
                    "Rejected alternative: HTTP API (3x slower on batch writes). "
                    "Owner: Bob Okonkwo."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Alice Nakamura: ADR-005 — Atlas runs in Frankfurt only, because the "
                    "customer data residency clause names the EU. Customer data from "
                    "Atlas must not be stored outside the EU, and that includes caches "
                    "and replicas."
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "Recorded ADR-005: Atlas runs in Frankfurt only (EU data residency). "
                    "Customer data from Atlas, including caches and replicas, stays in "
                    "the EU. Owner: Alice Nakamura."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Bob Okonkwo: ADR-006 — we retired the Orion batch exporter in March. "
                    "Anything that needs its output reads from Atlas now."
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "Recorded ADR-006: Orion batch exporter retired; consumers read from "
                    "Atlas instead. Owner: Bob Okonkwo."
                ),
            },
        ],
    },
    {
        "key": "helios-planning",
        "title": "Helios assistant planning",
        "expected": ["Priya Raman", "Diego Ferreira"],
        "messages": [
            {
                "role": "user",
                "content": (
                    "Priya Raman: ADR-003 — agent memory for the Helios assistant goes "
                    "through the hosted Neo4j Agent Memory Service rather than a "
                    "self-managed database. We do not want to be on call for a graph."
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "Recorded ADR-003: Helios uses the hosted Neo4j Agent Memory "
                    "Service. Rationale: no on-call burden. Owner: Priya Raman."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Priya Raman: ADR-009 — Helios reads customer account data from "
                    "Atlas instead of keeping its own copy. Atlas stays the system of "
                    "record."
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "Recorded ADR-009: Helios reads customer accounts from Atlas; Atlas "
                    "remains the system of record. Owner: Priya Raman."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Diego Ferreira: ADR-004 — embeddings are text-embedding-3-small. "
                    "We benchmarked gemini-embedding-001 too; recall was comparable and "
                    "the cost difference did not justify a second provider."
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "Recorded ADR-004: text-embedding-3-small for Helios embeddings. "
                    "Evaluated: gemini-embedding-001. Owner: Diego Ferreira."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Diego Ferreira: open question — the sales team wants a Helios "
                    "response cache in us-east-1 to cut latency for US users. Nobody "
                    "has signed off on it yet."
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "Logged open question: proposed Helios response cache in us-east-1 "
                    "(requested by sales). Not approved. Owner: Diego Ferreira."
                ),
            },
        ],
    },
]

#: Written explicitly before the messages so extraction resolves its mentions
#: onto these nodes instead of minting near-duplicates.
ENTITIES = [
    (
        "Atlas",
        "ORGANIZATION",
        "Internal data platform service; system of record for customer accounts.",
    ),
    ("Helios", "ORGANIZATION", "Customer-facing assistant. Memory via hosted NAMS."),
]

#: Entity names whose mention history ``verify`` reports.
CHECK_NAMES = ["Atlas", "Helios", "Frankfurt"]


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


async def seed(client: Any, *, timeout: float) -> int:
    state = load_state()
    existing = await find_existing(client)
    existing.update({key: c["id"] for key, c in state["conversations"].items()})

    # 1. Entities first ----------------------------------------------------
    for name, entity_type, description in ENTITIES:
        entity = await client.long_term.add_entity(name, entity_type, description=description)
        print(f"Entity: {entity.display_name} ({entity.full_type}) {entity.id}")

    # 2. One conversation per transcript, skipping any already seeded -------
    for conv in CONVERSATIONS:
        key, title = conv["key"], conv["title"]
        if key in existing:
            print(f"Skipping {title!r}: already seeded as {existing[key]}")
            state["conversations"][key] = {"id": existing[key], "title": title}
            continue
        created = await client.short_term.create_conversation(
            f"{DEMO_TAG}-{key}",
            metadata={"demo": DEMO_TAG, "key": key, "title": title},
        )
        conversation_id = str(created.id)
        stored = await client.short_term.bulk_add_messages(conversation_id, conv["messages"])
        print(f"Conversation {title!r} → {conversation_id} ({len(stored)} messages)")
        state["conversations"][key] = {"id": conversation_id, "title": title}
        save_state(state)

    # 3. Await the asynchronous extraction pipeline ------------------------
    settled_all = True
    for conv in CONVERSATIONS:
        conversation_id = state["conversations"][conv["key"]]["id"]
        status = await client.short_term.get_extraction_status(conversation_id)
        print(f"{conv['title']!r}: {status.pending_count} message(s) pending extraction")
        settled = await client.long_term.wait_for_extraction(
            session_id=conversation_id,
            expected_names=conv["expected"],
            timeout=timeout,
        )
        print(f"   settled: {settled}")
        settled_all = settled_all and settled

    state["seeded_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    save_state(state)

    # 4. Prove the cross-conversation link exists --------------------------
    linked = await verify(client, state)
    return 0 if settled_all and linked else 1


async def verify(client: Any, state: dict[str, Any]) -> bool:
    """Report which seeded conversations mention each entity; True if one links both."""
    titles = {c["id"]: c["title"] for c in state["conversations"].values()}
    print("\nSeeded conversations:")
    for conversation_id, title in titles.items():
        print(f"   {title}: {conversation_id}")

    print("\nMention history (from get_entity_history):")
    seen_ids: set[str] = set()
    bridges: list[str] = []
    exact: dict[str, int] = {}
    sample: Any = None
    for name in CHECK_NAMES:
        for entity in await client.long_term.search_entities(name, limit=10):
            if name.lower() not in entity.name.lower() or str(entity.id) in seen_ids:
                continue
            seen_ids.add(str(entity.id))
            if entity.name.lower() == name.lower():
                exact[name] = exact.get(name, 0) + 1
            history = await client.long_term.get_entity_history(entity.id)
            raw = json.dumps(history, default=str)
            found_in = [title for conversation_id, title in titles.items() if conversation_id in raw]
            if history and sample is None:
                sample = history[0]
            print(
                f"   {entity.display_name} ({entity.full_type}) — {len(history)} mention(s); "
                f"in: {', '.join(found_in) or 'no seeded conversation'}"
            )
            if titles and len(found_in) == len(titles):
                bridges.append(entity.display_name)

    for name, count in exact.items():
        if count > 1:
            print(
                f"\nWARN: {count} separate entities are named {name!r}. Merge them in the "
                "console (HITL Resolution) or the cross-conversation path may split."
            )

    if bridges:
        print(f"\nPASS: {', '.join(bridges)} links both conversations.")
        return True
    print(
        "\nFAIL: no entity links both conversations yet. Extraction may still be "
        "running — re-run with --verify in a minute."
    )
    if sample is not None:
        print(f"   (one raw history entry, to check its shape: {json.dumps(sample, default=str)[:400]})")
    return False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seed the Wake Up, Neo demo workspace.")
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
        help="Seconds to wait for server-side extraction per conversation (default: 120).",
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
        print(f"\nPlus {len(ENTITIES)} entity write(s): {', '.join(e[0] for e in ENTITIES)}.")
        print("Nothing was written. Re-run without --dry-run to seed.")
        return 0

    client = await connect_nams()
    try:
        if args.verify:
            state = load_state()
            if not state["conversations"]:
                print(f"Nothing seeded yet ({STATE_FILE.name} not found).")
                return 1
            return 0 if await verify(client, state) else 1
        return await seed(client, timeout=args.timeout)
    except AuthenticationError as exc:
        print(f"Rejected by NAMS: {exc}\nCheck MEMORY_API_KEY and MEMORY_WORKSPACE_ID.")
        return 1
    except (RateLimitError, TransportError) as exc:
        print(f"Request failed: {exc}")
        return 1
    finally:
        await client.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
