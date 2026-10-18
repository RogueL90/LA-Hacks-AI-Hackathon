"""Connect every running agent to its Agentverse mailbox (safe to run again).

Run after run/start.sh: .venv/bin/python -m scripts.connect_mailboxes
Each agent's local /connect endpoint registers the mailbox with our Agentverse key; in a
Bureau, the x-uagents-address header picks the agent.
"""
import json

import httpx

from shared import config

ADDRESSES = json.loads((config.ROOT / "shared" / "addresses.json").read_text())
GROUPS = {
    config.port("coordinator", 8200): ["coordinator"],
    config.port("team", 8201): ["space_builder", "elder", "baby", "transformer", "claim"],
    config.port("actions", 8202): ["product_finder", "cart", "payment_verifier", "insurance_filer"],
}


def main():
    if not config.AGENTVERSE_API_KEY:
        raise SystemExit("AGENTVERSE_API_KEY is not set in .env")
    for port, names in GROUPS.items():
        for name in names:
            address = ADDRESSES[name]
            try:
                r = httpx.post(f"http://127.0.0.1:{port}/connect", timeout=30,
                               headers={"x-uagents-address": address},
                               json={"user_token": config.AGENTVERSE_API_KEY, "agent_type": "mailbox"})
                status = f"{r.status_code} {r.text[:120]}"
            except httpx.HTTPError as exc:
                status = f"not running ({exc.__class__.__name__})"
            print(f"{name:17} {address[:18]}… port {port}: {status}")


if __name__ == "__main__":
    main()
