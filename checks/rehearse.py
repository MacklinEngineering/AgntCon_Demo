"""Run the stage gate: N fresh, timed runs of the on-stage agent through stage/go.sh.

Same model, tools and permissions as the show (go.sh passes ``-p`` through), so
a pass here means the agent's part is ready; what it can't check is how the
answer looks on the projector. Each run must finish in 60 s or less, use at
most 10 tool calls, and name the new site, the date the correction was
recorded, and the stale directory.

    ../.venv/bin/python rehearse.py      # the 5-run gate
    ../.venv/bin/python rehearse.py 1    # one run, with the full answer
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

DEMO = Path(__file__).resolve().parent.parent
GO = DEMO / "stage" / "go.sh"
QUESTION = (
    "A caller phoned our helpline back: they went to Brightwater Hall for free groceries "
    "last Saturday and the doors were locked. Why did our assistant send them there, and "
    "where should they have gone? Cite the earlier conversations."
)
#: What a correct answer has to name, as patterns that tolerate "Oct 14" / "Sept 2026".
MUST_NAME = {
    "Alder Branch Library": r"alder branch library",
    "correction recorded Oct 14": r"oct(ober|\.)?\s+14",
    "September 2026 directory": r"sept(ember|\.)?\s+2026",
}


def run_once() -> dict[str, Any]:
    # A run started from inside another Claude Code session must not inherit its markers.
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}
    start = time.monotonic()
    try:
        proc = subprocess.run(
            [str(GO), "-p", QUESTION, "--output-format", "stream-json", "--verbose"],
            capture_output=True,
            text=True,
            env=env,
            stdin=subprocess.DEVNULL,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return {"seconds": time.monotonic() - start, "mcp": "connected (hung)", "calls": [],
                "errors": ["run hung for 120 s"], "answer": "", "missing": [], "ok": False}
    calls: list[str] = []
    errors: list[str] = []
    answer = ""
    mcp = "?"
    for line in proc.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "system" and event.get("subtype") == "init":
            servers = event.get("mcp_servers") or []
            tools = [t for t in event.get("tools", []) if t.startswith("mcp__")]
            mcp = f"{', '.join(s.get('status', '?') for s in servers) or 'no server'}, {len(tools)} tools"
        elif event.get("type") == "assistant":
            for part in event["message"].get("content", []):
                if part.get("type") == "tool_use":
                    calls.append(part["name"].split("__")[-1].removeprefix("memory_"))
        elif event.get("type") == "user":
            for part in event.get("message", {}).get("content") or []:
                if isinstance(part, dict) and part.get("type") == "tool_result" and part.get("is_error"):
                    errors.append(str(part.get("content"))[:120])
        elif event.get("type") == "result":
            answer = str(event.get("result") or "")
    missing = [label for label, pattern in MUST_NAME.items() if not re.search(pattern, answer, re.I)]
    return {
        "seconds": time.monotonic() - start,
        "mcp": mcp,
        "calls": calls,
        "errors": errors,
        "answer": answer,
        "missing": missing,
        "ok": proc.returncode == 0 and bool(answer),
    }


def main() -> int:
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    passed = 0
    for i in range(1, runs + 1):
        # Headless mode can send the prompt before the MCP server finishes its NAMS
        # probe; the model then has no tools and types fake calls. On stage you wait
        # for /mcp to show connected, so retry those starts instead of failing them.
        for _ in range(3):
            r = run_once()
            if r["mcp"].startswith("connected"):
                break
            print(f"run {i}: retrying — MCP was still connecting when the prompt was sent")
        ok = r["ok"] and r["seconds"] <= 60 and len(r["calls"]) <= 10 and not r["missing"] and not r["errors"]
        passed += ok
        print(
            f"run {i}: {'PASS' if ok else 'FAIL'}  {r['seconds']:.0f}s  [mcp at start: {r['mcp']}]  "
            f"{len(r['calls'])} calls: {' → '.join(r['calls'])}"
        )
        for problem in r["missing"]:
            print(f"   answer does not name: {problem}")
        for error in r["errors"]:
            print(f"   tool error: {error}")
        if runs == 1 or not ok:
            print(r["answer"] + "\n")
    print(f"\n{passed}/{runs} passed (each run: ≤ 60 s, ≤ 10 tool calls, names the new site, Oct 14, and the Sept 2026 directory)")
    return 0 if passed == runs else 1


if __name__ == "__main__":
    raise SystemExit(main())
