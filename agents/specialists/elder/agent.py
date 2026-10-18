"""Elder Safety Inspector (Last Mile Home specialist): ModeRequest in, ModeResult out."""
from pathlib import Path

from agents.specialists.base import make_specialist
from agents.specialists.elder.logic import analyze

agent = make_specialist(
    key="elder",
    name="Elder Safety Inspector",
    mode="elder",
    description="Last Mile Home elder safety: finds fall hazards on the night path from bed to bathroom in a 3D model of a home, with measured clearances and fixes.",
    analyze=analyze,
    folder=Path(__file__).parent,
)

if __name__ == "__main__":
    agent.run()
