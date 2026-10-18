"""Run all of Shresth's agents in one process: fast in-process messages, one Agentverse mailbox each.

Run: .venv/bin/python -m run.bureau
"""
from shared import config
from uagents import Bureau

from agents.coordinator.agent import coordinator
from agents.space_builder.agent import agent as space_builder
from agents.specialists.baby.agent import agent as baby
from agents.specialists.claim.agent import agent as claim
from agents.specialists.elder.agent import agent as elder
from agents.specialists.transformer.agent import agent as transformer

AGENTS = [coordinator, space_builder, elder, baby, transformer, claim]

bureau = Bureau(port=config.port("coordinator", 8200))
for a in AGENTS:
    bureau.add(a)

if __name__ == "__main__":
    bureau.run()
