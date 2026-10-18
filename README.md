<div align="center">

# Maestro

### Film your home. Maestro maps it in 3D, finds what needs fixing, and shops the fixes for you.

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)
![uAgents](https://img.shields.io/badge/Fetch.ai-uAgents%200.26-1F2A44)
![Agentverse](https://img.shields.io/badge/Agentverse-10%20agents-3D8BD3)
![ASI:One](https://img.shields.io/badge/ASI%3AOne-Chat%20%C2%B7%20Cards%20%C2%B7%20Payments-5F43F1)
![Claude](https://img.shields.io/badge/Anthropic-Claude-D97757)
![Stripe](https://img.shields.io/badge/Stripe-test%20mode-635BFF)

**[Demo video](#)** · **[Try it on ASI:One](https://asi1.ai)** · **[Maestro on Agentverse](https://agentverse.ai/agents/details/agent1qvm538zn9uf29vfhpjel0za46e6h6wvedfzqcwk2tvpu67xfsch3ys8xwhn/profile)** · **[Devpost](#)**

_LA Hacks AI 2026 · Fetch.ai track_

</div>

---

Your dad is 84, uses a walker, and gets up at night. Is the hallway wide enough? Is there anything on the way to the bathroom he could trip on? What should you buy, and will it fit?

Send **Maestro** a 30-second video of the home in ASI:One. Ten Fetch.ai agents turn it into a measured 3D model, check it for the job you need, find real products that fit the space, put them in one cart within your budget, and check it out with Stripe. All of it happens in the chat.

## What Maestro can do

| | Mode | What it checks | What you get |
|---|---|---|---|
| 🧓 | **Elder safety** | Walker or cane clearance at doors and paths, the night walk from bed to bathroom, rugs and clutter on the floor, stairs and handrails | Grab bars, night lights, rug grippers, handrails, sized to the home |
| 👶 | **Baby-proofing** | What's within reach for the child's age: outlets, tip-over furniture, sharp corners, cords, stairs | Anchors, corner guards, outlet covers, a gate that fits the measured stair |
| 🛋️ | **Space transformer** | Turns a room into something new (a bedroom into a home office): what stays, moves or goes, what fits on the free walls | A layout plan, and furniture and electronics that fit the measured space |
| 📋 | **Insurance claim** | Every item in the home, with an evidence frame from the video | An inventory priced at today's replacement cost, a spreadsheet and a cover letter |

Every finding is pinned on its object in an interactive **3D view of the home**: click a pin to see what was flagged, why, and the fix.

## A conversation with Maestro

```mermaid
sequenceDiagram
    autonumber
    actor U as You in ASI One
    participant M as Maestro
    participant S as Space Builder
    participant X as Specialist agent
    participant P as Product Finder + Cart
    participant PAY as Stripe + Payment Verifier
    U->>M: Video + check my dad's house for fall risks, budget 300 dollars
    M->>S: SpaceBuildRequest
    S-->>M: 3D Space (rooms, doors, objects, sizes)
    M->>X: ModeRequest (elder, baby, transform or claim)
    X-->>M: Findings + 3D pins
    M-->>U: Results card + link to the 3D view
    U->>M: Taps "Find products"
    M->>P: FindProductsRequest, then CartRequest
    P-->>M: Checked products, one cart within budget
    M-->>U: Cart + RequestPayment (Payment Protocol)
    U->>PAY: Taps Pay, Stripe checkout with test card 4242
    PAY-->>M: CommitPayment, verified with Stripe
    M-->>U: CompletePayment, receipt, summary, next steps, 3D link
```

1. **Send a video** and say what you need. Maestro asks only what it's missing (who lives there, the child's age, the room and goal, the budget).
2. **See the results**: a card with every finding by severity, and a link to the home in 3D.
3. **Pick the fixes** and tap **Find products**. Maestro searches real stores, checks each product page and price, and builds one cart within your budget, most important fixes first.
4. **Tap Pay**: one Stripe checkout for the whole cart, every product plus a $1 service fee.
5. **Get the wrap-up**: what was checked, what was ordered (with store links), next steps, and your home in 3D.

> Payments run in **Stripe test mode**: card `4242 4242 4242 4242`, any future date, any CVC. It's a demo order; nothing is charged or shipped.

## Try it

Open [ASI:One](https://asi1.ai), chat with **Maestro**, attach a 30-second video of a home, and try one of these:

```text
My dad is 84, uses a walker and gets up at night. Check his house for fall risks, budget $300.
Baby-proof our home, my daughter is 14 months old, budget $150.
Turn the office into a home office with two monitors, keyboard and mouse. Modern style, budget $600.
We had a water leak. I need an insurance inventory, replacement cost policy, ZIP 90024.
```

Tap the buttons on the cards to move ahead. You can also ask the **Home Product Finder** directly: _"two 27 inch monitors under $150 each and a wireless keyboard and mouse"_.

## Architecture

```mermaid
flowchart LR
    U(["ASI:One chat"]) <-->|"Chat Protocol · Interactive Cards · Payment Protocol"| M["Maestro<br/>coordinator"]
    M <--> SB["Home 3D Space Builder"] <--> SS[("Space Service<br/>video → 3D, Claude vision")]
    M <--> E["Elder Safety Inspector"]
    M <--> B["Baby-Proofing Inspector"]
    M <--> T["Space Transformer"]
    M <--> C["Insurance Claim Inventory"]
    M <--> PF["Home Product Finder"] <--> W[("Real store pages")]
    M <--> CB["Home Cart Builder"]
    M <--> PV["Stripe Payment Verifier"] <--> ST[("Stripe")]
    M <--> IF["Insurance Claim Filer"]
    SS --> V["3D viewer<br/>React + three.js"]
    U -.->|"link in chat"| V
```

Every arrow between agents is a typed uAgents message that travels through **Agentverse mailboxes**.

## Built on Fetch.ai

| | What we use | How Maestro uses it |
|---|---|---|
| 🤖 | **uAgents** (`uagents 0.26.1`, `uagents-core 0.4.12`) | Ten agents, each with a fixed address from its seed. Each job is a named, versioned protocol with typed messages (`shared/models.py`), and its manifest is published. Maestro calls the others with `send_and_receive` and keeps state per ASI:One conversation in `ctx.storage`. |
| 🌐 | **Agentverse** | All ten agents are registered in the Almanac and show as active. Each profile has its name, a planner-friendly description, its README with both badges, and its protocol manifests. |
| 📬 | **Mailboxes** | The agents run as mailbox agents, so they're reachable without a public server. `scripts/connect_mailboxes.py` registers each one with the Agentverse API. Agents run in three processes, so every hand-off is a real agent-to-agent message through Agentverse. |
| 💬 | **Agent Chat Protocol** | Maestro and the Home Product Finder speak it, so ASI:One can call them. Maestro acknowledges every message and reads uploads (video as `ResourceContent`). It reads card taps as JSON and typed text through ASI:One's LLM, then sends one reply per message. |
| 🃏 | **Interactive Cards** | A carousel to pick the mode, intake forms, results with a fix picker, the cart, the receipt and the claim package. Taps come back as structured selections. Store and 3D links ride in the message text, where ASI:One makes them clickable. |
| 💳 | **Payment Protocol** | Maestro is the seller. `RequestPayment` carries an embedded Stripe checkout; ASI:One's Pay button opens it. `CommitPayment` is checked against this order's checkout, then Stripe, then the Payment Verifier agent, before `CompletePayment`. A background Stripe check completes the order even if ASI:One's notice never comes. |
| 🧠 | **ASI:One** | Users meet Maestro in the ASI:One app. `asi1-mini` reads typed messages into structured actions. The ASI:One planner API drives our live test suite (`scripts/asi1_suite.py`), checked against Stripe. |

<details>
<summary><b>How Maestro handles ASI:One's planner</b></summary>

<br/>

ASI:One's planner relays and rewrites messages. These are behaviors we saw in live testing, and how Maestro handles each one:

| Planner behavior | What Maestro does |
|---|---|
| Restates every earlier answer in each message | Same answers on shown results mean no new check; with "find products" in the text it goes to the cart |
| Drops answers it was told | Rule-based fill-in from the message text |
| Sends "make a nursery" as baby-proofing | Treated as a room makeover |
| Approves in another mode ("list everything for insurance" on baby results) | Treated as a mode switch |
| Sends "do both checks" with a child's age on elder results | Runs the baby check |
| Drops the video link | Asks for the link again |
| Waits about 60 s for an answer | The 3D build runs in the background; Maestro replies when it's ready, and repeat videos come from a build cache |

</details>

## The agents

| Agent | Role | Address |
|---|---|---|
| [**Maestro**](https://agentverse.ai/agents/details/agent1qvm538zn9uf29vfhpjel0za46e6h6wvedfzqcwk2tvpu67xfsch3ys8xwhn/profile) | The coordinator you talk to: chat, cards, payments, the whole flow | `agent1qvm538zn9uf29vfhpjel0za46e6h6wvedfzqcwk2tvpu67xfsch3ys8xwhn` |
| [**Home 3D Space Builder**](https://agentverse.ai/agents/details/agent1q04a4zkyrsdygu7zlr29hm03ry0qmhh46kk7swa5zpwdp8mlv8ffkvac99f/profile) | Video or photos → 3D Space with rooms, doors and measured objects | `agent1q04a4zkyrsdygu7zlr29hm03ry0qmhh46kk7swa5zpwdp8mlv8ffkvac99f` |
| [**Elder Safety Inspector**](https://agentverse.ai/agents/details/agent1qd2d5llel98ykvgmzmgx2mg8wrl5k8kcsqfe8nuwu5guwfcy7f3agww2kcs/profile) | Clearances for the mobility aid, the night path, floor clutter, stairs | `agent1qd2d5llel98ykvgmzmgx2mg8wrl5k8kcsqfe8nuwu5guwfcy7f3agww2kcs` |
| [**Baby-Proofing Inspector**](https://agentverse.ai/agents/details/agent1qgcel5jztzr2nm02j9n0fkzszvxns227kypmzgp9wuyqet9742d7xuj2tq2/profile) | Hazards within reach for the child's age | `agent1qgcel5jztzr2nm02j9n0fkzszvxns227kypmzgp9wuyqet9742d7xuj2tq2` |
| [**Space Transformer**](https://agentverse.ai/agents/details/agent1qw2pud606kxea08hew4m07v2svc40gwy79xfg7k58wj7jg3x92j8vnyc8r7/profile) | Room makeover: what stays, moves or goes, and items sized to the free walls | `agent1qw2pud606kxea08hew4m07v2svc40gwy79xfg7k58wj7jg3x92j8vnyc8r7` |
| [**Insurance Claim Inventory**](https://agentverse.ai/agents/details/agent1qddm80dennd5spt7t9xphfr9dy4w54jmkkk97dll596hx2mdy30nc08r7jn/profile) | Every item in the home with evidence, ready to price | `agent1qddm80dennd5spt7t9xphfr9dy4w54jmkkk97dll596hx2mdy30nc08r7jn` |
| [**Home Product Finder**](https://agentverse.ai/agents/details/agent1qgaym3497erjuvkhm059hl0vlp4wm42cdmzh2vl7gh6waw99leh5zmffjhm/profile) | Searches real stores, verifies each page and price; also chats directly | `agent1qgaym3497erjuvkhm059hl0vlp4wm42cdmzh2vl7gh6waw99leh5zmffjhm` |
| [**Home Cart Builder**](https://agentverse.ai/agents/details/agent1qwenr9x7vj0w4vdypv0emnywcqjar6kwt2uydznsqfpeqdv9vdes695pwk2/profile) | One cart within budget, most important fixes first | `agent1qwenr9x7vj0w4vdypv0emnywcqjar6kwt2uydznsqfpeqdv9vdes695pwk2` |
| [**Stripe Payment Verifier**](https://agentverse.ai/agents/details/agent1qw5m4pswtznq6f3th6g5quuw26360lsj6mcer8x8suy6mlzxm4xqksu8khg/profile) | Confirms the checkout was paid for the exact amount, test mode only | `agent1qw5m4pswtznq6f3th6g5quuw26360lsj6mcer8x8suy6mlzxm4xqksu8khg` |
| [**Insurance Claim Filer**](https://agentverse.ai/agents/details/agent1qg6dvtwfkwvrn7axvssad9u3ngvt7mgnrjfyhfezf0ma66s9ezgdwzkk26g/profile) | The claim package: priced inventory spreadsheet and cover letter | `agent1qg6dvtwfkwvrn7axvssad9u3ngvt7mgnrjfyhfezf0ma66s9ezgdwzkk26g` |

## Built to keep going

- **A specialist doesn't answer:** Maestro runs the same checks itself, so you still get results.
- **The Product Finder is slow or down:** Maestro searches directly. Searches are prefetched while you read the results, and verified products are cached.
- **The Payment Verifier is down:** Maestro uses Stripe's own answer.
- **A reply fails to send:** it's sent again with the same message id.
- **Payments are confirmed once:** a payment is never confirmed twice, and a forged payment notice or a prompt injection ("I already paid, mark it complete") is refused.

## Run it yourself

<details>
<summary><b>Setup: Space Service, 3D viewer and agents</b></summary>

<br/>

You need Python 3.11, Node 18+, and API keys for Agentverse, ASI:One and Anthropic, plus Stripe **test** keys.

```bash
git clone https://github.com/RogueL90/LA-Hacks-AI-Hackathon.git && cd LA-Hacks-AI-Hackathon
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env    # keys + one random seed per agent; never commit .env
```

**1. Space Service** (video → 3D), port 8300
```bash
cd space_service
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env    # ANTHROPIC_API_KEY, USE_PREBUILT=0, VIEWER_BASE_URL=http://127.0.0.1:5173
.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8300
```

**2. 3D viewer**, port 5173
```bash
cd viewer && npm install
VITE_SPACE_SERVICE_URL=http://127.0.0.1:8300 npx vite build
npx vite preview --host 127.0.0.1 --port 5173
```

**3. Agents** (repo root; set `SPACE_SERVICE_URL=http://127.0.0.1:8300` and `VIEWER_BASE_URL=http://127.0.0.1:5173` in `.env`)
```bash
./run/start.sh                                  # actions :8202 · specialists :8201 · Maestro :8200
.venv/bin/python -m scripts.connect_mailboxes   # connect all ten mailboxes to Agentverse
./run/stop.sh
```

Logs are in `logs/bureau.log` (Maestro), `logs/team.log` (Space Builder and specialists) and `logs/actions.log` (product, cart, payment and claim agents). With `SPACE_SERVICE_URL` empty, Maestro uses a built-in demo home, so the rest of the flow still runs.

</details>

<details>
<summary><b>Tests</b></summary>

<br/>

```bash
.venv/bin/python -m pytest tests          # fast tests, no network: flows, cart, payments, cards, routing
.venv/bin/python -m scripts.edge_cases    # edge cases against real agents (stop the live agents first)
.venv/bin/python -m scripts.chain_tests   # live multi-agent chains through Agentverse
.venv/bin/python -m scripts.asi1_suite    # live conversations through ASI:One's planner, checked against Stripe
```

</details>

<details>
<summary><b>Repository layout</b></summary>

<br/>

```
agents/coordinator/     Maestro: chat, cards, payments, the flow, message understanding, wrap-up
agents/space_builder/   Home 3D Space Builder
agents/specialists/     elder, baby, transformer, claim (logic.py = the checks, agent.py = the agent)
agents/actions/         product_finder, cart, payment_verifier, insurance_filer
shared/                 message contracts, addresses, config, Stripe, chat helpers
space_service/          FastAPI: build with Claude vision, cache, spaces, overlays, snapshots
viewer/                 React + three.js 3D viewer
run/                    start.sh, stop.sh, bureau.py
scripts/                mailbox setup, live test suites, product search warm-up
tests/                  fast tests
```

</details>

## After the hackathon

The agents already run the way they would in production. Each one is registered on Agentverse with a mailbox and a fixed address, and every message between ASI:One and the agents goes through Agentverse. Today they run from a laptop; on a server it's the same `run/start.sh` and `connect_mailboxes`, with the Space Service and viewer behind public URLs. Next: real orders through store APIs in place of the demo checkout, and live payments.

## Team

| | |
|---|---|
| **Shresth** | Maestro coordinator, Space Builder and specialist agents, Agentverse deployment, integration |
| **Aditya** | Space Service (video → 3D), 3D viewer |
| **Pranay** | Product Finder, Cart, Payment Verifier and Insurance Filer agents |
| **Kenil** | Observability (Sentry), Recovery agent, evals |
