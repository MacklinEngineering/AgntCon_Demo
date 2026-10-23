// The Locked Door — Query Console script. Paste one query at a time.
// The Graph tab draws only node and relationship columns (not paths or lists),
// so query 1 returns each node and relationship as its own column.
// Relationship names come from the NAMS docs; confirm them tonight with
// ../checks/inspect_graph.py before relying on this file on stage.

// 1. GRAPH TAB — the old door, the pantry, the new door, and the two
//    conversations they came from.
MATCH (old:Entity)<-[r1:MENTIONS]-(mb:Message)-[r2:MENTIONS]->(p:Entity)
      <-[r3:MENTIONS]-(ma:Message)-[r4:MENTIONS]->(new:Entity)
WHERE toLower(old.name) = 'brightwater hall'
  AND toLower(p.name) = 'wrenfield pantry'
  AND toLower(new.name) = 'alder branch library'
MATCH (cb:Conversation)-[h1:HAS_MESSAGE]->(mb)
MATCH (ca:Conversation)-[h2:HAS_MESSAGE]->(ma)
RETURN old, r1, mb, r2, p, r3, ma, r4, new, cb, h1, ca, h2
LIMIT 10;

// 2. TABLE — link or leak? Every entity mentioned in more than one conversation.
MATCH (c:Conversation)-[:HAS_MESSAGE]->(:Message)-[:MENTIONS]->(e:Entity)
WITH e, count(DISTINCT c) AS conversations
WHERE conversations > 1
RETURN e.name AS connects, e.type AS type, conversations
ORDER BY conversations DESC;

// 3. TABLE — who is in this graph? No caller anywhere.
MATCH (e:Entity)
RETURN e.type AS type, collect(e.name) AS names
ORDER BY type;

// Backup — one node or two? Each name should come back once.
MATCH (e:Entity)
WHERE any(w IN ['wrenfield', 'brightwater', 'alder'] WHERE toLower(e.name) CONTAINS w)
RETURN e.name AS name, e.type AS type
ORDER BY name;

// Backup — query 1 as a table, if the Graph tab shows "No graph data".
MATCH (old:Entity)<-[:MENTIONS]-(mb:Message)-[:MENTIONS]->(p:Entity)
      <-[:MENTIONS]-(ma:Message)-[:MENTIONS]->(new:Entity)
WHERE toLower(old.name) = 'brightwater hall'
  AND toLower(p.name) = 'wrenfield pantry'
  AND toLower(new.name) = 'alder branch library'
RETURN old.name AS old_door, left(mb.content, 70) AS referral, p.name AS via,
       left(ma.content, 70) AS update, new.name AS new_door
LIMIT 5;

// Optional — GRAPH TAB: both addresses at once. Extraction attached the pantry
// to the old hall (from the helpline) and the new room (from the coordinator);
// only the dates say which one is current.
MATCH (p:Entity)-[r:LOCATED_AT]->(place:Entity)
WHERE toLower(p.name) = 'wrenfield pantry'
RETURN p, r, place;

// Optional — GRAPH TAB: the real memory bug. One pantry, two nodes (Organization
// and Location), held apart by type-strict resolution and filed for review.
MATCH (a:Entity)-[s:SAME_AS]->(b:Entity)
WHERE toLower(a.name) = 'wrenfield pantry' AND toLower(b.name) = 'wrenfield pantry'
RETURN a, s, b
LIMIT 1;
