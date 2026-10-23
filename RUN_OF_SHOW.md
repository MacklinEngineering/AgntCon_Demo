# The Locked Door — run of show (10:45 · ~7 minutes + buffer)

All names are fictional; the data is synthetic. Every agent on stage is read-only.

**Screens:**

- **LEFT TERMINAL** — `before-silo/go.sh`: the helpline agent whose memory is only its own
  conversation. It will send the caller to the locked door.
- **RIGHT TERMINAL** — `after-graph/go.sh`: the same helpline agent, same model, same question —
  but before answering it follows what it's about to recommend through the shared graph.
- **BROWSER** — tab 1 your slides, tabs 2–7 the NAMS console with every query already run.
  Switch tabs with Cmd+1 … Cmd+7. Switch windows with Cmd+Tab or a click.

---

## 1. Set up (tonight to rehearse, again at T-15)

**TERMINALS** — two Terminal windows side by side (hover the green button → *Tile Window to Left
of Screen* / *Right of Screen*). Font ≥ 18 pt.

1. Left window: `~/AgntCon_Demo/before-silo/go.sh`. Right window: `~/AgntCon_Demo/after-graph/go.sh`.
2. The first launch of each asks whether you trust the folder → Enter. (Once, tonight.)
3. In each: type `/mcp`, wait for `agent-memory · ✔ connected`, press Esc. Leave both at an
   empty prompt. Between rehearsals, `/clear` in both.
4. Copy the caller's question (section 3) to the clipboard.

**BROWSER** (Chrome, one window, close other tabs, zoom 125–150%)

| Tab | Page | Set it up like this |
|---|---|---|
| 1 | **Your slides** | The three slides from `SLIDES.md`. Present with Cmd+Enter; → to advance; Esc after slide 3. |
| 2 | **Dashboard** | Shows **Community helpline** and **Pantry coordination**. Scroll the *System — Status unavailable* box off screen. |
| 3 | **Build → Query Console** | Query 1, run, click **Graph**. Drag nodes apart so names are readable. |
| 4 | **Build → Query Console** | Query 2, run (Table). Expect one row: Wrenfield Pantry, 2. |
| 5 | **Build → Query Console** | Query 3, run (Table). Expect **no rows** — that's the point. |
| 6 *(optional)* | **Build → Query Console** | Query 4, run (Table). Who's in the graph: only roles. |
| 7 *(optional)* | **Memory → Entity Resolution Review** | The pending duplicate: Wrenfield Pantry (Organization vs Location). |

Query 1 — the evidence path (Graph tab):
```cypher
MATCH (old:Entity)<-[r1:MENTIONS]-(mb:Message)-[r2:MENTIONS]->(p:Entity)<-[r3:MENTIONS]-(ma:Message)-[r4:MENTIONS]->(new:Entity)
WHERE toLower(old.name) = 'brightwater hall' AND toLower(p.name) = 'wrenfield pantry' AND toLower(new.name) = 'alder branch library'
MATCH (cb:Conversation)-[h1:HAS_MESSAGE]->(mb)
MATCH (ca:Conversation)-[h2:HAS_MESSAGE]->(ma)
RETURN old, r1, mb, r2, p, r3, ma, r4, new, cb, h1, ca, h2
LIMIT 10
```

Query 2 — what connects the two conversations? (Table):
```cypher
MATCH (c:Conversation)-[:HAS_MESSAGE]->(:Message)-[:MENTIONS]->(e:Entity)
WITH e, count(DISTINCT c) AS conversations
WHERE conversations > 1
RETURN e.name AS connects, e.type AS type, conversations
```

Query 3 — recorded decisions: what did any agent record about what it used? (Table; no rows):
```cypher
MATCH (s) WHERE any(l IN labels(s) WHERE l CONTAINS 'Step' OR l CONTAINS 'Trace' OR l = 'ToolCall')
RETURN labels(s) AS recorded_decision, count(*) AS n
```

Query 4 — who is in this graph? (Table; optional):
```cypher
MATCH (e:Entity)
RETURN e.type AS type, collect(e.name) AS names
ORDER BY type
```

If Query 1's Graph tab says "No graph data", use the "both addresses at once" query in
`queries/demo.cypher`, or a screenshot.

---

## 2. Before you go on

- [ ] T-30: `cd ~/AgntCon_Demo/seed && ../.venv/bin/python seed_workspace.py --verify` → PASS.
      `curl -s https://memory.neo4jlabs.com/v1/version` still says 2.0.0.
- [ ] T-15, on the venue Wi-Fi: `cd ~/AgntCon_Demo/checks && ../.venv/bin/python ab_test.py 1`
      → 2/2 passed. Otherwise switch to your hotspot now and re-run. Never switch mid-demo.
- [ ] T-15: set up the screens (section 1). Re-run each Query Console tab once.
- [ ] T-3: both terminals at an empty prompt with `/mcp` connected, question in the clipboard,
      notifications off. **Never paste before `/mcp` shows connected.**
- [ ] Start on **BROWSER tab 1 (slides)**.

---

## 3. The caller's question (in the clipboard)

> Hi. Where can I get free groceries this Saturday? I don't have a car.

---

## 4. On stage, beat by beat

**Beat 0 · 0:00–1:15 · BROWSER tab 1 (slides 1–3)**
Present the three slides with their speaker lines. Esc after slide 3.

**Beat 1 · 1:15–1:35 · BROWSER tab 2 (Dashboard)**
*Say:* "Two assistants share this memory: a community helpline, and a food pantry's coordination
assistant. They never talk to each other. Two days ago the pantry's coordinator told their
assistant that the Saturday site was moving."

**Beat 2 · 1:35–2:15 · BOTH TERMINALS**
*Say:* "Same helpline agent, twice. Same model, same question. On the left, its memory is only its
own conversation — the usual setup, every agent in its own silo. On the right, before it
answers, it checks what it's about to recommend against the shared graph."
*Do:* click LEFT, Cmd+V, Enter. Click RIGHT, Cmd+V, Enter.
*Say, while they run (10–20 s):* "The model doesn't remember anything itself. Both reach memory
through the open-source Agent Memory MCP server, with read-only tools."

**Beat 3 · 2:15–3:00 · BOTH TERMINALS (the answers)**
*Do:* point LEFT. *Say:* "Brightwater Hall. That's a locked door — the site moved."
*Do:* point RIGHT. *Say:* "Alder Branch Library. And it tells us why: the coordinator's update from
October 14. Nothing else changed — only retrieval. The correction lived in another assistant's
conversation, and the only way to it was through the pantry."

**Beat 3b · 3:00–3:30 · BOTH TERMINALS — prove it isn't scripted (recommended)**
*Say:* "Fair question: is this canned? Let's ask something else."
*Do:* type in both: `Is the place you'd send me wheelchair accessible?` → Enter in each.
*Expect:* LEFT: "I don't have any information on whether Brightwater Hall is wheelchair
accessible." RIGHT: "Yes… step-free entrance and an elevator" — a fact that only exists in the
coordinator's conversation.
*Say:* "Different question, different answer — and the right one only knows because the graph got
it into the other conversation." (If someone shouts out a question instead, type theirs: the
agents answer from memory or say they don't have that information.)

**Beat 4 · 3:30–4:00 · BROWSER tab 3 (Query 1, Graph)**
*Do:* Cmd+Tab to BROWSER, Cmd+3. Point left to right.
*Say:* "Here's the evidence path the right answer rests on: the locked door, the helpline message
that names it, the pantry, the coordinator's message, the new site. Two conversations, joined by
one entity. Every line from a message to a place or the pantry was written by extraction —
nobody wrote those links. Similarity search might surface the coordinator's message too; what
the graph adds is an explicit path back to the sources that you can check."

**Beat 5 · 4:00–4:25 · BROWSER tab 4 (Query 2)**
*Say:* "What connects the two conversations? One entity: the pantry. That's a property of the data,
not access control — anyone with this workspace's key can read both."

**Beat 6 · 4:25–5:30 · RIGHT TERMINAL, then BROWSER tab 5**
*Do:* point at the right agent's **Checked:** line.
*Say:* "The right agent told us what it checked — in a chat window."
*Do:* Cmd+Tab, Cmd+5 (no rows).
*Say:* "In memory, recorded decisions: none. And the left agent? We can't even ask what it
consulted. Extraction links are automatic; a record of what an agent actually used is
provenance your application has to write on purpose. Same lookup, two moments: before the
answer it's prevention — you just watched it. After a bad answer, it's how you debug."

**Beat 7 (optional, only if the clock shows under 5:30)** — pick one:
- BROWSER tab 7: "A real memory bug, found while building this: the pantry also got extracted as a
  place. NAMS didn't merge the two; it flagged them for a person to confirm, right here."
- BROWSER tab 6: "Who's in this graph? Only roles. We wrote the data that way; the graph makes
  that easy to check, it doesn't enforce it."

**Beat 8 · ~5:45 · BROWSER tab 2 or either terminal (close)**
*Say:* "A shared graph memory can show where a fact came from, across agents and sessions. Your
application still decides what to retrieve, what to expose, and records what it actually used.
Use an ID when questions always start in the same place; use a graph when they can start
anywhere. And memory like this must never be used to track who visits, ration food, or share
anything with landlords, police or immigration. The code is at github.com/neo4j-labs/agent-memory."

**6:45–8:00 · questions / buffer**

---

## 5. If something breaks

| Symptom | Do this |
|---|---|
| One agent slow (> 45 s) | Esc in that window; say "here's what it finds" and go to Beat 4 |
| `agent-memory` not connected at T-3 | `/mcp` → Reconnect once; else play clip 1, then continue live from Beat 4 |
| Left agent *doesn't* say Brightwater Hall | Say "it hedged — but notice it never mentions the new site" and continue |
| Network down | Play both backup clips and narrate the beats |
| Query 1 shows "No graph data" | Backup table version in `queries/demo.cypher`, or the screenshot |
| Console logged out | Log in again at T-15; screenshots if it happens on stage |

**Backup clips (record tonight):** clip 1 = Beats 2–3 (both terminals); clip 2 = Beats 4–6
(browser). Screenshot tabs 3–5. Download the slides as PDF too.

**Debug-after-the-fact backup:** `~/AgntCon_Demo/stage/go.sh` is the auditor from the earlier
version. Ask it: "A caller phoned our helpline back: they went to Brightwater Hall for free
groceries last Saturday and the doors were locked. Why did our assistant send them there, and
where should they have gone? Cite the earlier conversations." Use it in Q&A if someone asks how
you'd debug a miss that already happened.

## 6. If the data ever needs a reset

Delete both conversations (console, or `clear_session` in the SDK; since NAMS 1.1.0 deleting a
conversation also removes its extracted entities), delete `seed/seeded.json`, re-run the seed,
then copy the new helpline conversation id from `seed/seeded.json` into `before-silo/CLAUDE.md`
and `after-graph/CLAUDE.md` (it replaces `1679b2a3-2dff-4830-a73d-a009cc7ddafa`), relaunch both
terminals, and run `checks/ab_test.py 1`. About 10 minutes. Untested — only if `--verify` fails.

## 7. Questions you may get

- **"Is the answer scripted?"** "No. Each agent reads memory every time and answers the question
  it's asked — ask either one something memory doesn't cover, like a haircut, and it says it
  doesn't have that information."
- **"Isn't the left agent rigged?"** "It's the common setup: each agent remembers its own
  conversations — in Neo4j's words, 'its own memory, its own context, its own silo.' The right one
  is identical except for what it retrieves before answering."
- **"Would memory have prevented this?"** "Not by itself — the helpline didn't look. The right
  agent shows the check it should have run; the graph is what makes that check possible across
  conversations. Same lookup: before the answer it's prevention, after it's debugging."
- **"Couldn't vector search find this?"** "It might surface related text. The graph adds an
  explicit, entity-resolved path back to the source messages that you can inspect and check."
- **"Is the agent reasoning on its own?"** "It's guided by a retrieval rule — check what you're
  about to recommend — and four or fewer read-only tools. It's a careful assistant, not magic."
- **"Does the graph show what the agent actually did?"** "No — the graph is the evidence path. A
  record of what an agent used only exists if the application writes one; here there are none."
- **"Why NAMS instead of building it yourself?"** In Neo4j's words: "You call a REST API or connect
  an MCP client and NAMS handles storage, entity extraction, deduplication, embedding, background
  compression, and context retrieval." The trade-off: you give up some control, and flagged
  duplicates still need a person.
- **"Why did Neo4j build it?"** Publicly: to move that upkeep out of the agent, and "to enable
  integrations with other platforms such as the Salesforce Agentforce platform."
- **"Is this supported?"** "Agent Memory is a Neo4j Labs project: actively maintained, but not
  officially supported, with no SLAs."
- **"Can I run it on my own Neo4j?"** "Yes — the same Python package runs against your own Neo4j
  over Bolt. Then you run extraction and embeddings yourself, and some features differ."
- **"Is the workspace open source?"** "The client and MCP server are open source (Apache 2.0);
  NAMS is a managed service."

## Status (checked this morning)

Claude Code updated itself overnight to 2.1.309; the launch scripts now set
`DISABLE_AUTOUPDATER=1`. Seed verify PASS · smoke test ALL PASS · A/B: left says Brightwater
Hall, right says Alder Branch Library with the Oct 14 update · auditor (`stage/`) 2/2.
