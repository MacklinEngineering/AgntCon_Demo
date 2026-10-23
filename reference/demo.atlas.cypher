// Wake Up, Neo — Query Console script. Paste one block at a time.
// STATUS: DRAFT. Relationship names below follow the open-source bolt schema
// (Conversation-[:HAS_MESSAGE]->Message-[:MENTIONS]->Entity). Run
// ../checks/inspect_graph.py against the workspace and fix them before stage.
// Query 1 is schema-agnostic and works either way.

// 1. Start from the entity the question named: how does Helios reach Frankfurt?
MATCH (h:Entity), (f:Entity)
WHERE toLower(h.name) = 'helios' AND toLower(f.name) = 'frankfurt'
MATCH p = shortestPath((h)-[*..8]-(f))
RETURN p;

// 2. Atlas → the messages it was extracted from → their conversations.
MATCH p = (c:Conversation)-[:HAS_MESSAGE]->(m:Message)-[:MENTIONS]->(e:Entity)
WHERE toLower(e.name) = 'atlas'
RETURN p;

// 3. Start from a message instead: the us-east-1 question → what it reaches
//    in other conversations, and through which entity.
MATCH (q:Message) WHERE q.content CONTAINS 'us-east-1'
MATCH (q)<-[:HAS_MESSAGE]-(convB:Conversation)-[:HAS_MESSAGE]->(:Message)-[:MENTIONS]->(bridge:Entity)
MATCH (bridge)<-[:MENTIONS]-(ma:Message)<-[:HAS_MESSAGE]-(convA:Conversation)
WHERE convA <> convB
OPTIONAL MATCH (ma)-[:MENTIONS]->(other:Entity) WHERE other <> bridge
RETURN bridge.name AS via, left(ma.content, 90) AS earlier_message,
       collect(DISTINCT other.name) AS also_mentions;
