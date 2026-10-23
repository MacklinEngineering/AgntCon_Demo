"""Check the NAMS graph schema and the on-stage queries against the seeded workspace.

Runs read-only Cypher through ``client.query.cypher`` (POST /v1/query), the
endpoint the console's Query Console uses. Research on the NAMS docs says
(Conversation)-[:HAS_MESSAGE]->(Message)-[:MENTIONS]->(Entity); the first
sections confirm it before ../queries/demo.cypher is trusted on stage.

    ../.venv/bin/python inspect_graph.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "seed"))

from _shared import connect_nams, load_env  # noqa: E402
from seed_workspace import LINK_OR_LEAK  # noqa: E402

SECTIONS: list[tuple[str, str]] = [
    (
        "Relationship patterns",
        "MATCH (a)-[r]->(b) RETURN labels(a) AS source, type(r) AS rel, labels(b) AS target, "
        "count(*) AS n ORDER BY n DESC LIMIT 40",
    ),
    ("Node labels", "MATCH (n) RETURN labels(n) AS labels, count(*) AS n ORDER BY n DESC LIMIT 20"),
    ("Conversation keys", "MATCH (n:Conversation) RETURN keys(n) AS keys LIMIT 1"),
    ("Message keys", "MATCH (n:Message) RETURN keys(n) AS keys LIMIT 1"),
    ("Entity keys", "MATCH (n:Entity) RETURN keys(n) AS keys LIMIT 1"),
    (
        "One node or two? (each name must appear once)",
        "MATCH (e:Entity) WHERE any(w IN ['wrenfield', 'brightwater', 'alder'] "
        "WHERE toLower(e.name) CONTAINS w) RETURN e.name AS name, e.type AS type ORDER BY name",
    ),
    ("Link or leak? (entities in more than one conversation)", LINK_OR_LEAK),
    (
        "Old door → pantry → new door (names; stage query 1 draws this as a graph)",
        "MATCH (old:Entity)<-[:MENTIONS]-(mb:Message)-[:MENTIONS]->(p:Entity)"
        "<-[:MENTIONS]-(ma:Message)-[:MENTIONS]->(new:Entity) "
        "WHERE toLower(old.name) = 'brightwater hall' AND toLower(p.name) = 'wrenfield pantry' "
        "AND toLower(new.name) = 'alder branch library' "
        "RETURN old.name AS old_door, left(mb.content, 70) AS referral, p.name AS via, "
        "left(ma.content, 70) AS update, new.name AS new_door LIMIT 5",
    ),
    (
        "Who is in this graph? (entity inventory; there should be no caller)",
        "MATCH (e:Entity) RETURN e.type AS type, collect(e.name) AS names ORDER BY type",
    ),
    (
        "Recorded decisions (reasoning steps, traces, tool calls)",
        "MATCH (s) WHERE any(l IN labels(s) WHERE l CONTAINS 'Step' OR l CONTAINS 'Trace' "
        "OR l = 'ToolCall') RETURN labels(s) AS node, count(*) AS n",
    ),
]


async def main() -> int:
    load_env(quiet=True)
    client = await connect_nams()
    try:
        for title, query in SECTIONS:
            print(f"\n=== {title} ===")
            try:
                rows: list[dict[str, Any]] = await client.query.cypher(query)
            except Exception as exc:  # report and keep going; one bad guess should not hide the rest
                print(f"  error: {exc}")
                continue
            if not rows:
                print("  (no rows)")
            for row in rows[:40]:
                print(f"  {json.dumps(row, default=str, ensure_ascii=False)}")
    finally:
        await client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
