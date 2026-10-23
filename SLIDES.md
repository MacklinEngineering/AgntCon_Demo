# Three concept slides (about 90 seconds, before the live demo)

Paste into your deck template. Quotes are Neo4j's own published wording; the URLs are at the bottom.
Google Slides can't place SVG files reliably: open an SVG link in Chrome and screenshot it
(Cmd+Shift+4), or use the PNG.

---

## Slide 1 — "Most agents you build today are amnesiacs."

*Small line at the top of the slide:* Demo data is synthetic — no real people or recipients.

- The model keeps nothing between sessions. Anything an agent "remembers" was stored outside the
  model and put back into its context.
- Often a lookup is enough: save a value with the ID of the message it came from.
- But per-agent memory "falls apart the moment you need two agents to collaborate on the same
  problem."

**Visual:** `multi-agent-boundaries.svg` — several agents, each writing its own conversation,
all pointing at shared entities.
https://neo4j.com/labs/agent-memory/_images/diagrams/multi-agent-boundaries.svg

**Say (start with the first sentence):** "Everything you'll see is synthetic — no real people, no
real recipients. Here's the scenario: a helpline assistant sent a caller to a food pantry site
that had moved. Let's debug it."

---

## Slide 2 — How Agent Memory works

*One line across the top:* save messages → NAMS extracts and resolves entities (in the
background) → graph → MCP read tools → the agent reads the original messages → you inspect the path

- MCP is the tool interface; NAMS is the memory. The model doesn't remember anything on its own.
- **Short-term:** conversations and messages. **Long-term:** entities and their relationships.
  **Reasoning:** the steps and tool calls an application chooses to record.
- NAMS stores each message and, in the background, extracts the people, organizations and places
  it mentions — each one linked back to the messages it came from.
- Message search works inside one conversation; entities are shared across the workspace.
  So you cross conversations through an entity.

**Visual:** `the-three-layer-memory-architecture.png` (crop off the bottom Bolt/NAMS row).
https://neo4j.com/labs/agent-memory/_images/diagrams/the-three-layer-memory-architecture.png

Or, if you'd rather draw the demo's own setup:

```
 Community helpline ─┐                ┌────────── Neo4j Agent Memory (NAMS) ──────────┐
                     ├─ save messages ▶ Conversations → Messages ─extraction─▶ Entities │
 Pantry coordination ┘                │  same entity, same type, two conversations     │
                                      │  → one shared node (Wrenfield Pantry)          │
                                      └──────────▲──────────────────────────▲─────────┘
                                                 │ MCP                      │ console
                    Agent (Claude Code) ─────────┘ search · entity history ·  You: graph + Cypher
                                                   read conversation · provenance
```

**Say:** "Agents save messages; the service turns them into a graph. In Neo4j's words, it
'handles storage, entity extraction, deduplication, embedding, background compression, and
context retrieval.' An agent with the workspace key queries it through MCP — today through the
open-source Agent Memory MCP server — and I can inspect it in the console."

---

## Slide 3 — Two kinds of links

- **Extraction links — automatic.** "This entity came from these messages."
- **Decision record — deliberate.** "This answer used these memories." In Agent Memory that's
  reasoning memory, and only your application writes it.
- An ID is enough when questions start in the same place. Similarity search finds related text.
  A graph gives you an explicit path back to the sources that you can inspect.

**Visual:** two diagrams side by side — left `message-chain.svg` (label: *automatic*), right
`reasoning-touched-audit.svg` (label: *only if your app writes it*).
https://neo4j.com/labs/agent-memory/_images/diagrams/message-chain.svg
https://neo4j.com/labs/agent-memory/_images/diagrams/reasoning-touched-audit.svg

**Say:** "Watch for both in the demo. One of them will be missing."

---

**Footer for the deck:** All names in the demo are fictional. Agent Memory is a Neo4j Labs
project: actively maintained, not officially supported.

**Sources**
- "Most agents you build today are amnesiacs." and "handles storage, entity extraction,
  deduplication, embedding, background compression, and context retrieval" — *A Tour of the Neo4j
  Agent Memory Service*, https://neo4j.com/blog/genai/a-tour-of-the-neo4j-agent-memory-service-nams/
- "falls apart the moment you need two agents to collaborate on the same problem" — *When your
  agents share a brain*, https://neo4j.com/blog/developer/when-your-agents-share-a-brain-building-multi-agent-memory-with-neo4j/
- Memory layers and "the presence of the three layers does not populate them automatically" —
  https://neo4j.com/labs/agent-memory/explanation/memory-types/
