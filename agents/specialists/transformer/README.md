![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

# Space Transformer

Repurposes a room for a new use, such as turning a spare bedroom into a home office, a nursery or a home gym.

## What it does
- Measures the room's free walls, windows and walkways in the 3D model
- Decides what stays and what moves out
- Lists the items the new use needs, each with a maximum size that fits the measured space, ready for a real product search

## Messages
- In: `ModeRequest` (mode `transform`) with the goal, room, requirements, style and budget
- Out: `ModeResult` with the layout suggestions and a sized product search for each new item

Part of Last Mile Home; reached through the Last Mile Home coordinator in ASI:One.
