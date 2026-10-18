"""Load a repo-root .env without overriding variables already set."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(ROOT))

# Loads .env and points SSL_CERT_FILE at certifi before any connection opens: the python.org
# build of Python ships without CA certificates, so Agentverse and Stripe calls fail otherwise.
from shared import config  # noqa: E402,F401


def ensure_event_loop() -> None:
    """uAgents asks for a loop at construction. asyncio.run() leaves none behind."""
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())


def load_env() -> None:
    path = ROOT / ".env"
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
