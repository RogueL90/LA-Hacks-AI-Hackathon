"""Space Transformer (Last Mile Home specialist): ModeRequest in, ModeResult out."""
from pathlib import Path

from agents.specialists.base import make_specialist
from agents.specialists.transformer.logic import analyze

agent = make_specialist(
    key="transformer",
    name="Space Transformer",
    mode="transform",
    description="Last Mile Home space transformer: plans how to repurpose a room (for example into a home office) from a 3D model, with products sized to fit the measured space.",
    analyze=analyze,
    folder=Path(__file__).parent,
)

if __name__ == "__main__":
    agent.run()
