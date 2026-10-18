"""Insurance Claim Inventory (Maestro specialist): ModeRequest in, ModeResult out."""
from pathlib import Path

from agents.specialists.base import make_specialist
from agents.specialists.claim.logic import analyze

agent = make_specialist(
    key="claim",
    name="Insurance Claim Inventory",
    mode="claim",
    description="Maestro insurance claim: lists every item in a 3D model of a home, with evidence, ready to price for a contents claim.",
    analyze=analyze,
    folder=Path(__file__).parent,
)

if __name__ == "__main__":
    agent.run()
