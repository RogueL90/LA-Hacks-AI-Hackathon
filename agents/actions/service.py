"""Shared shell for the four action agents, matching the specialists: an Agentverse mailbox,
a published protocol manifest and a README, so each one is listed and reachable on its own.
"""

from __future__ import annotations

from pathlib import Path

from shared import config  # loads .env and the CA bundle before uagents opens connections
from uagents import Agent


def make_action_agent(key: str, name: str, description: str, folder: Path, port: int) -> Agent:
    """`port` is only used when the agent runs on its own; in a Bureau the Bureau's port is used."""
    return Agent(
        name=name,
        seed=config.seed(key),
        port=port,
        mailbox=True,
        handle_messages_concurrently=True,  # one slow job must not block the others
        publish_agent_details=True,
        readme_path=str(folder / "README.md"),
        description=description,
    )
