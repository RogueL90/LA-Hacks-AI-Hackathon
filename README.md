# Last Mile Home

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

Upload a 30-second video or a few photos of a home in **ASI:One**. Last Mile Home turns it into a realistic 3D "dollhouse" model in which every object is real data (type, size, position, color), then helps with four jobs:

| Mode | What it does |
|---|---|
| Elder safety | Fall hazards, walker clearance, the 2 am walk to the bathroom |
| Baby-proofing | Hazards at toddler eye level: outlets, corners, cords, stairs, reachable items |
| Space transformer | Repurposes a room (for example, a bedroom into a home office): new layout, what stays or moves, and real products found online that fit the measured space |
| Insurance claim | Lists and values every object with evidence, and builds the claim package |

Built for LA Hacks AI 2026 (Fetch.ai track) with Fetch.ai uAgents, Agentverse, ASI:One, Anthropic Claude and Sentry.

## Team
| Person | Area |
|---|---|
| Aditya | Space Service (video/photos → Space JSON), 3D viewer |
| Shresth | Coordinator, Space Builder agent, specialist agents, Agentverse deployment |
| Pranay | Product Finder, Cart, Payment Verifier, Insurance Filer agents |
| Kenil | Observability (Sentry), Recovery agent, evals |

## Repository layout
```
shared/            models.py, addresses.json, config.py
observability/     Sentry setup, tracing, evals
space_service/     FastAPI: build, store, overlays, snapshots
viewer/            React + three.js 3D viewer
agents/coordinator/
agents/space_builder/
agents/specialists/{elder,baby,transformer,claim}/
agents/actions/{product_finder,cart,payment_verifier,insurance_filer}/
agents/recovery/
run/bureau.py      runs all agents in one process
evals/rooms/       test rooms and expected findings
```

## Setup
1. Python 3.11. Create a virtual environment and install dependencies:
   ```bash
   python3.11 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and fill in the keys. Never commit `.env`.

## Contributing
Work on your own branch (`shresth`, `aditya`, `pranay`, `kenil`) and open a pull request into `main`. Shresth merges.

## Agents
Agent names, addresses and Agentverse profile links will be listed here once they are deployed.
