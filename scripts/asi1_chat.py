"""Talk to our coordinator through ASI:One itself (planner mode), the way the chat app does.

Run: .venv/bin/python -m scripts.asi1_chat "message" [--session ID] [--history file.json]
Prints the planner's progress (which agent it called, what it sent, what came back) and
the final answer, and saves the conversation so the next turn can continue it.
"""
import argparse
import json
import uuid
from pathlib import Path

import httpx

from shared import config

COORDINATOR = json.loads((config.ROOT / "shared" / "addresses.json").read_text())["coordinator"]
STATE = config.ROOT / "logs" / "asi1_chat_state.json"


def merge(into: dict, update: dict):
    for k, v in update.items():
        if isinstance(v, dict) and isinstance(into.get(k), dict):
            merge(into[k], v)
        else:
            into[k] = v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("message")
    ap.add_argument("--new", action="store_true", help="start a new session")
    args = ap.parse_args()

    state = {} if args.new or not STATE.exists() else json.loads(STATE.read_text())
    session = state.get("session") or str(uuid.uuid4())
    messages = state.get("messages", []) + [{"role": "user", "content": args.message}]

    body = {"model": "asi1", "messages": messages, "planner_mode": True, "agents": [COORDINATOR], "stream": True}
    headers = {"Authorization": f"Bearer {config.ASI_ONE_API_KEY}", "x-session-id": session}
    plan: dict = {}
    answer = []
    seen_lines = set()
    with httpx.stream("POST", "https://api.asi1.ai/v1/chat/completions", json=body, headers=headers, timeout=600) as r:
        print(f"HTTP {r.status_code}  session={session}")
        for line in r.iter_lines():
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            chunk = json.loads(data)
            meta = chunk.get("metadata")
            if meta:
                merge(plan, meta)
                status = plan.get("plan_status")
                key = f"status:{status}"
                if key not in seen_lines:
                    seen_lines.add(key)
                    print(f"  [plan] {status}")
            for choice in chunk.get("choices", []):
                delta = choice.get("delta", {}).get("content")
                if delta:
                    answer.append(delta)

    (config.ROOT / "logs" / "asi1_plan.json").write_text(json.dumps(plan, indent=2))
    for pid, phase in sorted(plan.get("phases", {}).items()):
        for tid, task in sorted(phase.get("tasks", {}).items()):
            interesting = {k: v for k, v in task.items() if k != "status"}
            print(f"  phase {pid} task {tid}: {task.get('status')}  {json.dumps(interesting)[:900]}")
    text = "".join(answer)
    print("\n=== ASI:One answer ===\n" + text)
    STATE.write_text(json.dumps({"session": session, "messages": messages + [{"role": "assistant", "content": text}]}))


if __name__ == "__main__":
    main()
