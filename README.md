# Maestro

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

Send **Maestro** a 30-second video of a home in **ASI:One**. It turns the video into a 3D model where every object is real data (type, size, position), checks the home for the job you need, finds real products that fit the measured space, puts them in one cart within your budget, and checks it out with Stripe, all inside the ASI:One chat.

Built for LA Hacks AI 2026 (Fetch.ai track) with Fetch.ai uAgents, Agentverse, ASI:One and Anthropic Claude.

| Link | |
|---|---|
| Demo video | _add before submitting_ |
| ASI:One shared chat | _add before submitting_ |
| Devpost | _add before submitting_ |
| Maestro on Agentverse | https://agentverse.ai/agents/details/agent1qvm538zn9uf29vfhpjel0za46e6h6wvedfzqcwk2tvpu67xfsch3ys8xwhn/profile |

## What it does

| Mode | What it checks | What you get |
|---|---|---|
| Elder safety | Fall hazards, walker or cane clearance at doors and paths, the night walk from bed to bathroom, stairs and handrails | Findings pinned in 3D, a fix plan (grab bars, night lights, rug grippers...) sized to the home |
| Baby-proofing | Hazards within a child's reach for their age: outlets, tip-over furniture, sharp corners, cords, stairs | Findings pinned in 3D, a fix plan (anchors, gates that fit the measured stair width...) |
| Space transformer | Repurposes a room, for example a bedroom into a home office: what stays, moves or goes, and what fits on the free walls | A layout plan and products that fit the measured space (desks, monitors, chairs...) |
| Insurance claim | Lists every item in the home with evidence frames | An inventory priced at today's replacement cost, a spreadsheet and a cover letter |

Then, in the same chat:
1. Pick the fixes you want and tap **Find products**. Maestro searches real stores, checks each product page and price, and builds one cart within your budget (most important fixes first).
2. Tap **Pay**: one Stripe checkout for the whole cart, every product plus a $1 service fee, through the Fetch.ai Payment Protocol.
3. After the payment is confirmed you get a wrap-up: a summary, what was ordered (with store links), next steps, and a link to your home in 3D where every finding is pinned on its object.

Payments run in **Stripe test mode**: use card `4242 4242 4242 4242`, any future date and any CVC. It's a demo order; nothing is really charged or shipped.

## Try it in ASI:One

1. Open [ASI:One](https://asi1.ai), start a chat with **Maestro** (search for it, or use the address below), and attach a 30-second video of a home.
2. Say what you need, for example:
   - "My dad is 84, uses a walker and gets up at night. Check his house for fall risks, budget $300."
   - "Baby-proof our home, my daughter is 14 months old, budget $150."
   - "Turn the office into a home office with two monitors, keyboard and mouse. Modern style, budget $600."
   - "We had a water leak. I need an insurance inventory, replacement cost policy, ZIP 90024."
3. Tap the buttons on each card to move ahead. Typed replies work too, but card taps go straight to Maestro.

You can also chat with the **Home Product Finder** directly: "two 27 inch monitors under $150 each and a wireless keyboard and mouse" returns checked product links.

## Agents

All ten agents are registered on Agentverse (mailbox agents) and publish their manifests and READMEs. Maestro is the one users talk to; the others are reached through it with typed messages (`shared/models.py`).

| Agent | Role | Address | Agentverse |
|---|---|---|---|
| **Maestro** | Coordinator: Chat Protocol, Interactive Cards, Payment Protocol (seller). Understands each message, runs the flow, keeps state per conversation | `agent1qvm538zn9uf29vfhpjel0za46e6h6wvedfzqcwk2tvpu67xfsch3ys8xwhn` | [profile](https://agentverse.ai/agents/details/agent1qvm538zn9uf29vfhpjel0za46e6h6wvedfzqcwk2tvpu67xfsch3ys8xwhn/profile) |
| **Home 3D Space Builder** | Video or photos → 3D Space (rooms, doors, objects with measurements) through the Space Service | `agent1q04a4zkyrsdygu7zlr29hm03ry0qmhh46kk7swa5zpwdp8mlv8ffkvac99f` | [profile](https://agentverse.ai/agents/details/agent1q04a4zkyrsdygu7zlr29hm03ry0qmhh46kk7swa5zpwdp8mlv8ffkvac99f/profile) |
| **Elder Safety Inspector** | Fall hazards, clearances for the mobility aid, night path, stairs | `agent1qd2d5llel98ykvgmzmgx2mg8wrl5k8kcsqfe8nuwu5guwfcy7f3agww2kcs` | [profile](https://agentverse.ai/agents/details/agent1qd2d5llel98ykvgmzmgx2mg8wrl5k8kcsqfe8nuwu5guwfcy7f3agww2kcs/profile) |
| **Baby-Proofing Inspector** | Hazards within reach for the child's age | `agent1qgcel5jztzr2nm02j9n0fkzszvxns227kypmzgp9wuyqet9742d7xuj2tq2` | [profile](https://agentverse.ai/agents/details/agent1qgcel5jztzr2nm02j9n0fkzszvxns227kypmzgp9wuyqet9742d7xuj2tq2/profile) |
| **Space Transformer** | Room makeover plan: what stays, moves or goes, and items sized to the free space | `agent1qw2pud606kxea08hew4m07v2svc40gwy79xfg7k58wj7jg3x92j8vnyc8r7` | [profile](https://agentverse.ai/agents/details/agent1qw2pud606kxea08hew4m07v2svc40gwy79xfg7k58wj7jg3x92j8vnyc8r7/profile) |
| **Insurance Claim Inventory** | Every item in the home with evidence, ready to price | `agent1qddm80dennd5spt7t9xphfr9dy4w54jmkkk97dll596hx2mdy30nc08r7jn` | [profile](https://agentverse.ai/agents/details/agent1qddm80dennd5spt7t9xphfr9dy4w54jmkkk97dll596hx2mdy30nc08r7jn/profile) |
| **Home Product Finder** | Searches real stores (Claude with web search), verifies each product page and price; also answers chat directly | `agent1qgaym3497erjuvkhm059hl0vlp4wm42cdmzh2vl7gh6waw99leh5zmffjhm` | [profile](https://agentverse.ai/agents/details/agent1qgaym3497erjuvkhm059hl0vlp4wm42cdmzh2vl7gh6waw99leh5zmffjhm/profile) |
| **Home Cart Builder** | One cart within budget: merges duplicates, most important fixes first | `agent1qwenr9x7vj0w4vdypv0emnywcqjar6kwt2uydznsqfpeqdv9vdes695pwk2` | [profile](https://agentverse.ai/agents/details/agent1qwenr9x7vj0w4vdypv0emnywcqjar6kwt2uydznsqfpeqdv9vdes695pwk2/profile) |
| **Stripe Payment Verifier** | Confirms the Stripe checkout was paid, for the exact amount, in test mode only | `agent1qw5m4pswtznq6f3th6g5quuw26360lsj6mcer8x8suy6mlzxm4xqksu8khg` | [profile](https://agentverse.ai/agents/details/agent1qw5m4pswtznq6f3th6g5quuw26360lsj6mcer8x8suy6mlzxm4xqksu8khg/profile) |
| **Insurance Claim Filer** | Builds the claim package: priced inventory spreadsheet and cover letter | `agent1qg6dvtwfkwvrn7axvssad9u3ngvt7mgnrjfyhfezf0ma66s9ezgdwzkk26g` | [profile](https://agentverse.ai/agents/details/agent1qg6dvtwfkwvrn7axvssad9u3ngvt7mgnrjfyhfezf0ma66s9ezgdwzkk26g/profile) |

Addresses come from each agent's seed (`.env`) and are kept in `shared/addresses.json`; `python -m scripts.print_addresses` prints them.

## How it works

```
ASI:One chat ──Chat Protocol──▶ Maestro (coordinator) ──▶ Home 3D Space Builder ──▶ Space Service (FastAPI, Claude vision)
      ▲                            │
      │ Interactive Cards          ├──▶ Elder / Baby-Proofing / Space Transformer / Insurance Claim Inventory
      │ Payment Protocol           ├──▶ Home Product Finder ──▶ real store pages (Claude web search)
      │                            ├──▶ Home Cart Builder
      │                            ├──▶ Stripe Payment Verifier ──▶ Stripe (test mode)
      │                            └──▶ Insurance Claim Filer
      └──────── results, cart, payment request, wrap-up ◀──┘           3D viewer (React + three.js) ◀── pins per finding
```

- **Chat Protocol** (`uagents_core.contrib.protocols.chat`): Maestro and the Home Product Finder speak it, so ASI:One can call them.
- **Interactive Cards**: results, forms, cart and receipts are cards in the chat; card taps come back to Maestro as structured selections.
- **Payment Protocol** (`uagents_core.contrib.protocols.payment`): Maestro sends `RequestPayment` with an embedded Stripe checkout; ASI:One's Pay button opens it; `CommitPayment` is verified with Stripe and the Payment Verifier before `CompletePayment`.
- **Agent-to-agent messages**: typed `uagents` models (`shared/models.py`) over Agentverse mailboxes.
- **Understanding**: ASI:One (`asi1-mini`) reads each message into a structured action, with rule-based fallbacks for answers it misses.
- **3D**: the Space Service extracts rooms, doors and objects from video frames with Claude, caches builds, and stores overlay sets; the viewer animates the home in and pins every finding on its object (click a pin for what was flagged, why, and the fix). It follows new checks from the same conversation live.

## Reliability and error recovery

- If a specialist agent doesn't answer, Maestro runs the same checks itself, so the user still gets results.
- If the Product Finder is slow or down, Maestro searches directly; product searches are prefetched while you read the results, and verified products are pooled and cached.
- If the 3D build takes longer than ASI:One waits, Maestro replies when it's ready instead of timing out.
- A reply that fails to send is sent again (same message id); payments are confirmed with Stripe first, then the Payment Verifier, and a payment is never confirmed twice.
- Prompt injection and forged payment confirmations are refused (see `scripts/edge_cases.py`).

## Run it yourself

Requirements: Python 3.11, Node 18+, an Agentverse API key, an ASI:One API key, an Anthropic API key and Stripe **test** keys.

```bash
git clone https://github.com/RogueL90/LA-Hacks-AI-Hackathon.git && cd LA-Hacks-AI-Hackathon
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # fill in the keys and one random seed per agent; never commit .env
```

**1. Space Service** (video → 3D Space), port 8300:
```bash
cd space_service
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # ANTHROPIC_API_KEY, USE_PREBUILT=0, VIEWER_BASE_URL=http://127.0.0.1:5173
.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8300
```

**2. 3D viewer**, port 5173:
```bash
cd viewer
npm install
VITE_SPACE_SERVICE_URL=http://127.0.0.1:8300 npx vite build
npx vite preview --host 127.0.0.1 --port 5173
```

**3. Agents** (in the repo root; `.env` needs `SPACE_SERVICE_URL=http://127.0.0.1:8300` and `VIEWER_BASE_URL=http://127.0.0.1:5173`):
```bash
./run/start.sh                              # actions on 8202, specialists on 8201, Maestro on 8200
.venv/bin/python -m scripts.connect_mailboxes   # registers all ten mailboxes with Agentverse
./run/stop.sh                               # stop
```
Logs: `logs/bureau.log` (Maestro), `logs/team.log` (Space Builder and specialists), `logs/actions.log` (product, cart, payment, claim agents).

Without the Space Service (`SPACE_SERVICE_URL` empty), Maestro uses a built-in demo home so the rest of the flow still runs.

## Tests

```bash
.venv/bin/python -m pytest tests                    # fast tests, no network (flows, cart, payments, cards, routing)
.venv/bin/python -m scripts.edge_cases              # edge cases against real agents (stop the live agents first)
.venv/bin/python -m scripts.chain_tests             # live multi-agent chains through Agentverse
.venv/bin/python -m scripts.asi1_suite              # live conversations through ASI:One's planner, checked against Stripe
```

## After the hackathon

The agents already run the way they would in production: each is registered on Agentverse with a mailbox and a fixed address from its seed, and every message between ASI:One and the agents goes through Agentverse. Today they run from a laptop; running them on a server is the same `run/start.sh` and `connect_mailboxes` there, with the Space Service and viewer behind public URLs (`SPACE_SERVICE_URL`, `VIEWER_BASE_URL`). Next steps: real orders through store APIs instead of the demo checkout, and live Stripe keys.

## Repository layout
```
agents/coordinator/          Maestro: chat, cards, payments, flow (agent.py), message understanding, wrap-up
agents/space_builder/        Home 3D Space Builder
agents/specialists/          elder, baby, transformer, claim (logic.py = the checks; agent.py = the agent)
agents/actions/              product_finder, cart, payment_verifier, insurance_filer
shared/                      models.py (message contracts), addresses.json, config, Stripe, chat helpers
space_service/               FastAPI: build (Claude vision), cache, spaces, overlays, snapshots
viewer/                      React + three.js 3D viewer
run/                         start.sh, stop.sh, bureau.py
scripts/                     mailbox setup, live test suites, product search warm-up
tests/                       fast tests
```

## Team
| Person | Area |
|---|---|
| Shresth | Maestro coordinator, Space Builder and specialist agents, Agentverse deployment, integration |
| Aditya | Space Service (video → 3D Space), 3D viewer |
| Pranay | Product Finder, Cart, Payment Verifier, Insurance Filer agents |
| Kenil | Observability (Sentry), Recovery agent, evals |
