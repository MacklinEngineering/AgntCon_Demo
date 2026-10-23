"""Run the before/after helpline agents on the same caller question and compare answers.

before-silo/ can read only its own conversation; after-graph/ can also follow entities
through the shared graph. The demo depends on the first sending the caller to Brightwater
Hall (the locked door) and the second to Alder Branch Library.

    ../.venv/bin/python ab_test.py        # 3 runs of each
    ../.venv/bin/python ab_test.py 1      # one run of each, with both answers
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

DEMO = Path(__file__).resolve().parent.parent
QUESTION = "Hi. Where can I get free groceries this Saturday? I don't have a car."
EXPECT = {"before-silo": "brightwater hall", "after-graph": "alder branch library"}


def run(agent: str) -> dict[str, Any]:
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}
    for _ in range(3):  # retry starts where the MCP server was still connecting
        start = time.monotonic()
        try:
            proc = subprocess.run(
                [str(DEMO / agent / "go.sh"), "-p", QUESTION, "--output-format", "stream-json", "--verbose"],
                capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL, timeout=120,
            )
        except subprocess.TimeoutExpired:
            return {"seconds": 120.0, "calls": [], "answer": "(hung for 120 s)", "connected": True}
        calls, answer, connected = [], "", False
        for line in proc.stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "system" and event.get("subtype") == "init":
                connected = any(s.get("status") == "connected" for s in event.get("mcp_servers") or [])
            elif event.get("type") == "assistant":
                calls += [p["name"].split("__")[-1].removeprefix("memory_")
                          for p in event["message"].get("content", []) if p.get("type") == "tool_use"]
            elif event.get("type") == "result":
                answer = str(event.get("result") or "")
        if connected:
            break
    return {"seconds": time.monotonic() - start, "calls": calls, "answer": answer, "connected": connected}


def main() -> int:
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    ok = 0
    for i in range(1, runs + 1):
        for agent, expected in EXPECT.items():
            r = run(agent)
            good = expected in r["answer"].lower() and (agent == "after-graph" or "alder" not in r["answer"].lower())
            ok += good
            print(f"run {i} {agent:12} {'PASS' if good else 'FAIL'}  {r['seconds']:.0f}s  "
                  f"{len(r['calls'])} calls: {' → '.join(r['calls'])}")
            if runs == 1 or not good:
                print("   " + r["answer"].replace("\n", "\n   ") + "\n")
    total = runs * len(EXPECT)
    print(f"\n{ok}/{total} passed (before-silo must say Brightwater Hall; after-graph must say Alder Branch Library)")
    return 0 if ok == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
