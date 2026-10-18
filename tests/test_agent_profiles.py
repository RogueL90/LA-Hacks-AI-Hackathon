"""Agentverse rejects a profile whose description is over 300 characters (the agent's /connect
then fails with a 500), so every agent's description must fit."""
import importlib

import pytest

AGENTS = [
    ("agents.coordinator.agent", "coordinator"),
    ("agents.space_builder.agent", "agent"),
    ("agents.specialists.elder.agent", "agent"),
    ("agents.specialists.baby.agent", "agent"),
    ("agents.specialists.transformer.agent", "agent"),
    ("agents.specialists.claim.agent", "agent"),
    ("agents.actions.product_finder.agent", "agent"),
    ("agents.actions.cart.agent", "agent"),
    ("agents.actions.payment_verifier.agent", "agent"),
    ("agents.actions.insurance_filer.agent", "agent"),
]


@pytest.mark.parametrize("module, name", AGENTS)
def test_description_fits_agentverse(module, name):
    agent = getattr(importlib.import_module(module), name)
    description = agent._description or ""
    assert 0 < len(description) <= 300, f"{agent.name}: {len(description)} characters"
    assert "lmh" not in agent.name.lower()
