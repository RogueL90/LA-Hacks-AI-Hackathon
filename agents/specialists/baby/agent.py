"""Baby-Proofing Inspector (Maestro specialist): ModeRequest in, ModeResult out."""
from pathlib import Path

from agents.specialists.base import make_specialist
from agents.specialists.baby.logic import analyze

agent = make_specialist(
    key="baby",
    name="Baby-Proofing Inspector",
    mode="baby",
    description="Maestro baby-proofing: finds hazards within a toddler's reach in a 3D model of a home (outlets, tip-over furniture, corners, cords) with fixes.",
    analyze=analyze,
    folder=Path(__file__).parent,
)

if __name__ == "__main__":
    agent.run()
