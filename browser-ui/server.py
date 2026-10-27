#!/usr/bin/env python3
"""Small local web wrapper for the two existing Locked Door agents."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).resolve().parent / "static"
AGENTS = {
    "before": ROOT / "before-silo" / "go.sh",
    "after": ROOT / "after-graph" / "go.sh",
}
FILES = {
    "/": ("index.html", "text/html"),
    "/styles.css": ("styles.css", "text/css"),
    "/app.js": ("app.js", "text/javascript"),
    "/favicon.svg": ("favicon.svg", "image/svg+xml"),
}
MAX_PROMPT = 1500
TIMEOUT = 120
STATE = ROOT / "seed" / "seeded.json"


def tool_payload(content: object) -> dict:
    """Decode the JSON text returned by an MCP tool in Claude's event stream."""
    for _ in range(4):
        if isinstance(content, dict):
            if any(key in content for key in ("messages", "results", "history")):
                return content
            content = content.get("result", content.get("content", content.get("text", content.get("structuredContent"))))
        elif isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        elif isinstance(content, str):
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                return {}
        else:
            return {}
    return content if isinstance(content, dict) else {}


def source_from_conversation(payload: dict, conversation_id: str, kind: str) -> dict | None:
    messages = payload.get("messages") or []
    if not isinstance(messages, list):
        return None
    phrase = "Brightwater Hall" if kind == "helpline" else "Alder Branch Library"
    candidates = [message for message in messages
                  if isinstance(message, dict) and phrase.lower() in str(message.get("content", "")).lower()]
    if not candidates:
        return None
    preferred = "Referral logged" if kind == "helpline" else "Saved to shared memory"
    message = next((item for item in candidates if preferred in str(item.get("content", ""))), candidates[-1])
    return {
        "kind": kind,
        "conversationId": conversation_id,
        "messageId": str(message.get("id") or ""),
        "text": str(message.get("content") or "")[:500],
    }


def observed_proof(calls: list[dict], results: dict[str, dict]) -> dict:
    """Build proof solely from actual tool inputs and tool responses."""
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
        conversations = state["conversations"]
        helpline_id = conversations["helpline-referral"]["id"]
        pantry_id = conversations["pantry-coordination"]["id"]
    except (OSError, KeyError, TypeError, ValueError):
        helpline_id = pantry_id = ""

    safe_calls = []
    sources = []
    bridge_ids = set()
    pantry_read = False
    for call in calls:
        name = call["tool"]
        args = call["input"]
        safe_input = {key: args[key] for key in ("session_id", "entity_id", "query", "memory_types")
                      if key in args and isinstance(args[key], (str, list))}
        safe_calls.append({"tool": name, "input": safe_input})
        payload = results.get(call["id"], {})

        if name == "search":
            entities = (payload.get("results") or {}).get("entities") or []
            for entity in entities:
                if isinstance(entity, dict) and str(entity.get("name", "")).lower() == "wrenfield pantry":
                    bridge_ids.add(str(entity.get("id") or ""))
        elif name == "get_conversation":
            conversation_id = str(payload.get("session_id") or args.get("session_id") or "")
            kind = "helpline" if conversation_id == helpline_id else "pantry" if conversation_id == pantry_id else ""
            if kind:
                source = source_from_conversation(payload, conversation_id, kind)
                if source and not any(item["kind"] == kind for item in sources):
                    sources.append(source)
                    if kind == "pantry":
                        pantry_read = True

    bridge = None
    for call in calls:
        entity_id = str(call["input"].get("entity_id") or "")
        if call["tool"] != "get_entity_history" or entity_id not in bridge_ids:
            continue
        raw_history = json.dumps(results.get(call["id"], {}), ensure_ascii=False).lower()
        spans_both = bool(helpline_id and pantry_id
                          and helpline_id.lower() in raw_history and pantry_id.lower() in raw_history)
        candidate = {"name": "Wrenfield Pantry", "entityId": entity_id,
                     "verified": bool(spans_both and pantry_read)}
        if bridge is None or candidate["verified"]:
            bridge = candidate
        if candidate["verified"]:
            break

    return {"calls": safe_calls, "sources": sources, "bridge": bridge}


def run_agent(agent: str, prompt: str) -> dict:
    """Run the original launcher and return its answer and memory tool names."""
    launcher = AGENTS[agent]
    env = {key: value for key, value in os.environ.items()
           if key not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}
    started = time.monotonic()
    try:
        process = subprocess.Popen(
            [str(launcher), "-p", prompt, "--output-format", "stream-json", "--verbose"],
            cwd=launcher.parent,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            start_new_session=True,
        )
    except OSError:
        return {"error": "The local agent could not start."}

    try:
        output, _ = process.communicate(timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.communicate()
        return {"error": "The agent timed out after two minutes."}

    answer = ""
    calls = []
    tool_results = {}
    connected = False
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "system" and event.get("subtype") == "init":
            connected = any(server.get("status") == "connected"
                            for server in event.get("mcp_servers") or []
                            if isinstance(server, dict))
        elif event.get("type") == "assistant":
            message = event.get("message") or {}
            for part in message.get("content") or []:
                if isinstance(part, dict) and part.get("type") == "tool_use":
                    calls.append({
                        "id": str(part.get("id") or ""),
                        "tool": str(part.get("name") or "").split("__")[-1].removeprefix("memory_"),
                        "input": part.get("input") if isinstance(part.get("input"), dict) else {},
                    })
        elif event.get("type") == "user":
            message = event.get("message") or {}
            for part in message.get("content") or []:
                if isinstance(part, dict) and part.get("type") == "tool_result" and not part.get("is_error"):
                    tool_results[str(part.get("tool_use_id") or "")] = tool_payload(part.get("content"))
        elif event.get("type") == "result":
            answer = str(event.get("result") or "").strip()

    if not connected:
        return {"error": "Agent Memory did not connect. Check the existing MCP setup."}
    if process.returncode != 0 or not answer:
        return {"error": "The agent did not return an answer. Try again."}
    return {
        "answer": answer,
        "tools": [call["tool"] for call in calls],
        "proof": observed_proof(calls, tool_results),
        "seconds": round(time.monotonic() - started, 1),
    }


class Handler(BaseHTTPRequestHandler):
    def headers_common(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; frame-ancestors 'none'")

    def local_request(self, *, mutation: bool = False) -> bool:
        host = self.headers.get("Host", "")
        allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        origin = self.headers.get("Origin")
        if host in allowed and (not mutation or not origin or origin == f"http://{host}"):
            return True
        self.send_json(HTTPStatus.FORBIDDEN, {"error": "Use this demo from its local browser page."})
        return False

    def send_json(self, status: HTTPStatus, data: dict) -> None:
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.headers_common()
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        if not self.local_request():
            return
        route = FILES.get(urlsplit(self.path).path)
        if route is None:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        filename, content_type = route
        payload = (STATIC / filename).read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.headers_common()
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:
        if not self.local_request(mutation=True):
            return
        path = urlsplit(self.path).path
        agent = path.removeprefix("/api/run/")
        if path != f"/api/run/{agent}" or agent not in AGENTS:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if self.headers.get("Content-Type", "").split(";", 1)[0].lower() != "application/json":
            self.send_json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "Expected JSON."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4096:
                raise ValueError
            body = json.loads(self.rfile.read(length))
            prompt = body.get("prompt")
        except (ValueError, AttributeError, TypeError):
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Enter a question."})
            return
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > MAX_PROMPT:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Enter a question under 1,500 characters."})
            return
        self.send_json(HTTPStatus.OK, run_agent(agent, prompt.strip()))


def main() -> None:
    parser = argparse.ArgumentParser(description="Local browser UI for the Locked Door demo")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"Neo4j Agent Memory demo → {url}", flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
