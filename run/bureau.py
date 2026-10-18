"""Run Shresth's agents.

    .venv/bin/python -m run.bureau front   # Last Mile Home (the coordinator ASI:One talks to), port 8200
    .venv/bin/python -m run.bureau team    # Space Builder + the four specialists, port 8201
    .venv/bin/python -m run.bureau all     # everything in one process (tests, or a single-machine fallback)

With front and team as two processes, every hand-off (coordinator -> Space Builder ->
specialists) travels through the agents' Agentverse mailboxes: real agent-to-agent
messages that Agentverse can see and count.

Only the chosen group's agents are imported: creating an Agent registers it with the
in-process dispatcher, and messages to a registered address are delivered locally, so
importing an agent that runs in the other process would swallow its messages.
"""
import sys

from shared import config
from uagents import Bureau


def coordinator_agents():
    from agents.coordinator.agent import coordinator
    return [coordinator]


def team_agents():
    from agents.space_builder.agent import agent as space_builder
    from agents.specialists.baby.agent import agent as baby
    from agents.specialists.claim.agent import agent as claim
    from agents.specialists.elder.agent import agent as elder
    from agents.specialists.transformer.agent import agent as transformer
    return [space_builder, elder, baby, transformer, claim]


def agents_for(group: str):
    if group == "front":
        return coordinator_agents(), config.port("coordinator", 8200)
    if group == "team":
        return team_agents(), config.port("team", 8201)
    return coordinator_agents() + team_agents(), config.port("coordinator", 8200)


if __name__ == "__main__":
    agents, port = agents_for(sys.argv[1] if len(sys.argv) > 1 else "all")
    bureau = Bureau(port=port)
    for a in agents:
        bureau.add(a)
    bureau.run()
