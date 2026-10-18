# MASTER.md — Last Mile Home (working name) · LA Hacks AI 2026

> Read this first. Everyone builds against the **contracts in Section 5**. If you need to change a contract, tell Shresth first — he owns `shared/models.py`.

---

## 1. What we are building (one paragraph)

In **ASI:One**, a user uploads a **30-second video or photos** of a home. The **Space Builder** turns it into a realistic **3D "dollhouse" model** where every object is real data (type, size, position, color). **Interactive cards** then offer four modes:

| Mode | Specialist agent | What it does |
|---|---|---|
| Elder Safety | `elder_agent` | Fall hazards, walker clearance, the 2am night walk to the bathroom |
| Baby-proofing | `baby_agent` | Hazards at toddler eye level (~2.5 ft): outlets, corners, cords, stairs, reachable items |
| Interior Design | `interior_agent` | New layout + style, real products that fit the measured space |
| Insurance Claim | `claim_agent` | Itemize and value every object, evidence per item, build the claim package |

Specialists call **generic action agents**: Product Finder → Cart → Payment, and Insurance Filer. **Sentry** traces every agent, scores their quality (evals), and a **Recovery agent** retries failures and tells the user.

**The primary workflow must complete fully inside ASI:One** (Fetch rule). The 3D viewer is a companion page opened from a card.

---

## 2. Tracks and hard requirements

| Track | Must have | Owner |
|---|---|---|
| **Fetch.ai** (primary) | Agents on Agentverse · Chat Protocol · usable in ASI:One · real tool use / multi-agent · full workflow in ASI:One · public GitHub + run instructions · Submission Agent + Devpost · ASI:One shared chat URL · every Agentverse profile URL · README badges · 3–5 min video | Shresth |
| **Fetch.ai bonus** | Multi-agent · Payment Protocol with real monetization · Interactive Cards · error recovery · real-time data · runs after hackathon | Everyone |
| **Sentry** | 2+ products beyond errors (we use: tracing, AI agent monitoring, logs, profiling, Session Replay, uptime) + a story of how Sentry changed what we built | Kenil |
| **Best design (Paper)** | Judged on UI/UX. Paper tool optional. Must look calm, premium, accessible | Aditya (3D) + Shresth (cards) |
| **Gemini (MLH)** | Gemini used for real: vision, structured output, grounding | Aditya, Shresth, Pranay |

README badges (required):
```
![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)
```

Deadline: **Sunday Oct 18, 12:00 PDT** (Devpost + ASI:One Submission Agent). Judging 12:30.

---

## 3. Team and ownership

| Person | Owns | Hands off to |
|---|---|---|
| **Aditya** | Space Service (video/photos → Space JSON), 3D viewer website, snapshot images for cards | Shresth (via GitHub + a hosted URL) |
| **Shresth** | Coordinator agent, Space Builder agent wrapper, 4 specialist agents, cards, Payment Protocol in the Coordinator, **all Agentverse deployment**, submission | — |
| **Pranay** | Product Finder, Cart, Payment Verifier, Insurance Filer agents | Shresth (via GitHub) |
| **Kenil** | `observability/` package, Sentry setup everywhere, Recovery agent, evals, Session Replay + uptime, Sentry story for Devpost | Shresth (via GitHub) + everyone imports his package |

**Rule:** only Shresth deploys to Agentverse. Everyone else runs their agents **locally** with the test harness and pushes to GitHub.

---

## 4. Architecture

```
                    USER in ASI:One  (uploads video/photos)
                              │  Chat Protocol + Interactive Cards + Payment Protocol
                              ▼
                 ┌──────────────────────────────┐
                 │  COORDINATOR  (Shresth)      │  ASI:One reasoning, routing,
                 │  session state, approvals    │  cards, RequestPayment
                 └──────────────┬───────────────┘
                                ▼
                 ┌──────────────────────────────┐        ┌───────────────────────────┐
                 │  SPACE BUILDER agent         │──HTTP─▶│  SPACE SERVICE (Aditya)   │
                 │  (Shresth wraps)             │        │  Gemini → Space JSON,     │
                 └──────────────┬───────────────┘        │  scale, layout, store,    │
                                │ space_id               │  overlays, snapshots      │
        ┌───────────────┬───────┴───────┬───────────────┐└────────────┬──────────────┘
        ▼               ▼               ▼               ▼             │
   ELDER agent     BABY agent     INTERIOR agent   CLAIM agent        │  3D VIEWER
   (Shresth)       (Shresth)      (Shresth)        (Shresth)          │  (Aditya, three.js)
        └───────────────┴───────┬───────┴───────────────┘             │  opened from a card
                                ▼   post overlays ─────────────────────┘
        ┌────────────────────── ACTION AGENTS (Pranay) ─────────────────────┐
        │ PRODUCT FINDER → CART → PAYMENT VERIFIER    INSURANCE FILER       │
        └───────────────────────────────────────────────────────────────────┘

  ═════════════ SENTRY (Kenil) wraps EVERY agent + service + viewer ═════════════
  tracing (one trace per user job, across agents) · AI agent monitoring · logs ·
  profiling (Space Service) · Session Replay (viewer) · uptime · evals ·
  RECOVERY agent: receives AgentError, retries, sends user-facing notice
```

**Runtime layout (recommended):**
- All uAgents run in **one Bureau process on one cloud VM** (fast agent-to-agent calls, ~ms instead of 5–10 s mailbox hops). Each agent still has its own address and is registered on Agentverse (mailbox) so it is discoverable. Only the Coordinator needs to talk to ASI:One.
- **Space Service** (FastAPI) runs on the same VM (GPU not required for the dollhouse approach).
- **3D Viewer** on Vercel.
- Secrets in `.env` on the VM, never in git.

---

## 5. Shared contracts (`shared/models.py`) — build against these from minute one

All agent messages are `uagents.Model` (pydantic). Units: **meters**, **USD**, coordinates **x right, y up, z forward**, origin = room corner.

```python
# shared/models.py
from typing import Literal, Optional
from uagents import Model

Mode = Literal["elder", "baby", "interior", "claim"]

class TraceCtx(Model):                    # Kenil: used to stitch one trace across agents
    sentry_trace: Optional[str] = None
    baggage: Optional[str] = None

class Evidence(Model):
    frame_url: Optional[str] = None       # image of the frame the object/hazard was seen in
    timestamp_s: Optional[float] = None   # seconds into the video
    note: Optional[str] = None

class SpaceObject(Model):
    id: str                               # "obj_rug_01"
    type: str                             # from the 30-type catalog (see Aditya.md)
    label: str                            # "Living room rug"
    room_id: str
    position: list[float]                 # [x, y, z] center, meters
    size: list[float]                     # [w, h, d] meters
    rotation_y: float = 0.0               # radians
    color: Optional[str] = None           # "#a3825f"
    material: Optional[str] = None
    attributes: dict = {}                 # brand_guess, model_guess, height_from_floor, is_loose, ...
    confidence: float = 0.5
    evidence: list[Evidence] = []

class Door(Model):
    id: str
    room_id: str
    position: list[float]
    width_m: float

class Room(Model):
    id: str
    name: str                             # "Hallway"
    polygon: list[list[float]]            # floor outline [[x,z], ...]
    height_m: float = 2.5

class Space(Model):
    space_id: str
    source_type: Literal["video", "photos"]
    rooms: list[Room]
    doors: list[Door] = []
    objects: list[SpaceObject]
    scale_method: str                     # "door_reference" | "depth_pro" | "user_confirmed" | "prebuilt"
    scale_confidence: float
    viewer_url: str                       # https://viewer.../s/{space_id}
    snapshot_url: str                     # PNG for cards

class SpaceBuildRequest(Model):
    job_id: str
    media_urls: list[str]
    trace: TraceCtx = TraceCtx()

class SpaceBuildResult(Model):
    job_id: str
    ok: bool
    space: Optional[Space] = None
    error: Optional[str] = None

class Profile(Model):                     # filled from the intake card; mode uses what it needs
    person: Optional[str] = None          # "Mom"
    age: Optional[int] = None
    mobility_aid: Optional[str] = None    # "walker" | "cane" | "wheelchair" | None
    night_trips: Optional[bool] = None
    child_age_months: Optional[int] = None
    style: Optional[str] = None           # interior: "japandi", "warm modern"...
    budget_usd: Optional[float] = None
    policy_type: Optional[str] = None     # claim: "replacement_cost" | "actual_cash_value"
    zip_code: Optional[str] = None

class Measurement(Model):
    name: str                             # "walkway_clearance"
    value: float
    unit: str                             # "in" | "m" | "lux_est"
    required: Optional[float] = None
    passes: Optional[bool] = None

class ProductQuery(Model):
    query: str                            # "adhesive non-slip rug gripper 5x7"
    max_price_usd: Optional[float] = None
    constraints: dict = {}                # {"length_in": 18, "toilet_shape": "elongated"}
    quantity: int = 1

class Finding(Model):
    id: str
    kind: Literal["hazard", "suggestion", "item"]
    title: str                            # "Loose rug in hallway"
    severity: int = 3                     # 1 low … 5 critical (hazards only)
    object_ids: list[str] = []
    evidence: list[Evidence] = []
    measurements: list[Measurement] = []
    fix_summary: Optional[str] = None
    product_query: Optional[ProductQuery] = None
    value_usd: Optional[float] = None     # claim mode
    value_basis: Optional[str] = None     # "receipt" | "measured" | "user_confirmed" | "estimate"

class Overlay(Model):                     # what the viewer draws
    type: Literal["pin", "path", "ghost_object", "tag", "highlight", "camera"]
    data: dict                            # see Aditya.md for each type's fields

class ModeRequest(Model):
    job_id: str
    mode: Mode
    space_id: str
    profile: Profile
    trace: TraceCtx = TraceCtx()

class ModeResult(Model):
    job_id: str
    mode: Mode
    ok: bool
    summary: str
    findings: list[Finding] = []
    overlay_set_id: Optional[str] = None  # stored in Space Service; viewer loads it
    viewer_url: Optional[str] = None      # deep link: /s/{space_id}?mode=elder&o={overlay_set_id}
    snapshot_url: Optional[str] = None
    error: Optional[str] = None

class ProductQuote(Model):
    title: str
    url: str
    merchant: str
    price_usd: float
    image_url: Optional[str] = None
    specs: dict = {}
    url_verified: bool = False            # we actually fetched the page and saw the product
    fit_note: Optional[str] = None        # "18 in bar fits 22 in wall stud span"
    finding_id: Optional[str] = None

class FindProductsRequest(Model):
    job_id: str
    queries: list[ProductQuery]
    trace: TraceCtx = TraceCtx()

class FindProductsResult(Model):
    job_id: str
    ok: bool
    quotes: list[ProductQuote] = []
    error: Optional[str] = None

class CartRequest(Model):
    job_id: str
    quotes: list[ProductQuote]
    budget_usd: Optional[float] = None
    trace: TraceCtx = TraceCtx()

class CartResult(Model):
    job_id: str
    ok: bool
    cart_id: str = ""
    items: list[ProductQuote] = []
    subtotal_usd: float = 0.0
    within_budget: bool = True
    checkout_links: list[str] = []        # merchant handoff — NOT a placed order (label it)
    service_fee_fet: str = "0"            # what the Coordinator will charge via Payment Protocol
    error: Optional[str] = None

class VerifyPaymentRequest(Model):
    job_id: str
    tx_hash: str
    expected_amount_fet: str
    recipient: str
    trace: TraceCtx = TraceCtx()

class VerifyPaymentResult(Model):
    job_id: str
    ok: bool
    verified: bool = False
    detail: str = ""

class ClaimRequest(Model):
    job_id: str
    space_id: str
    findings: list[Finding]               # kind="item" with value_usd + value_basis
    profile: Profile
    trace: TraceCtx = TraceCtx()

class ClaimPackage(Model):
    job_id: str
    ok: bool
    inventory_xlsx_url: Optional[str] = None
    inventory_csv_url: Optional[str] = None
    letter_pdf_url: Optional[str] = None  # cover letter / advance-payment request draft
    total_usd: float = 0.0
    item_count: int = 0
    error: Optional[str] = None

class AgentError(Model):                  # any agent → Recovery agent
    job_id: str
    agent: str
    step: str
    message: str
    retryable: bool
    sentry_event_id: Optional[str] = None
    retry_payload: dict = {}              # enough to redo the step

class RecoveryNotice(Model):              # Recovery → Coordinator (shown to user as a card)
    job_id: str
    step: str
    outcome: Literal["recovered", "fallback_used", "failed"]
    user_message: str                     # "Pricing service was slow — switched to backup. All good."
    sentry_trace_url: Optional[str] = None
```

**Addresses:** Shresth maintains `shared/addresses.json` (agent name → agent address). Agents read addresses from it, never hard-code.

---

## 6. End-to-end flow (what happens in ASI:One)

1. User: "@LastMileHome here's a video of my mom's place" + attachment (or a card link to our upload page if ASI:One can't take video — **test first**).
2. Coordinator → Space Builder → Space Service. Card: **3D snapshot + "Open 3D view" + four mode buttons**.
3. User taps **Elder Safety** → intake card (age, mobility aid, night trips, budget) → Coordinator → `elder_agent`.
4. Card: **hazard carousel** (each with the video frame, measurement, fix) + snapshot with pins + "Walk the 2am path in 3D".
5. User taps **Fix these** → Product Finder → Cart → card: **plan + prices + budget check**.
6. User taps **Approve** → Coordinator sends **RequestPayment** (service fee, testnet FET) → user pays in ASI:One → Payment Verifier checks tx → Coordinator **CompletePayment** → card: **receipt + merchant checkout links (labelled "handoff, not an order")**.
7. Any failure → AgentError → Recovery → RecoveryNotice card with Sentry trace link.
8. Same pattern for Baby, Interior (layout + products), Claim (items + values → Insurance Filer → claim package card with downloads).

---

## 7. Repo layout (one monorepo)

```
/shared/            models.py, addresses.json, config.py            (Shresth)
/observability/     sentry_setup.py, tracing.py, evals/             (Kenil)
/space_service/     FastAPI: build, store, overlays, snapshots      (Aditya)
/viewer/            React + three.js (react-three-fiber)            (Aditya)
/agents/coordinator/                                                (Shresth)
/agents/space_builder/                                              (Shresth)
/agents/specialists/{elder,baby,interior,claim}/                    (Shresth)
/agents/actions/{product_finder,cart,payment_verifier,insurance_filer}/  (Pranay)
/agents/recovery/                                                   (Kenil)
/run/bureau.py      runs all agents in one process                  (Shresth)
/evals/rooms/       test rooms + expected findings                  (Kenil + all)
README.md           badges, agent names + addresses, run instructions (Shresth)
```

**Git rules**
- Branch per person: `aditya/...`, `pranay/...`, `kenil/...`. PR into `main`. Shresth merges.
- Never commit `.env`, seeds or keys. Use `.env.example`.
- Every agent folder has `README.md` (what it does, messages in/out, how to run locally) and `test_local.py`.
- Python 3.11. Pin versions in `requirements.txt` (`uagents`, `uagents-core`, `google-genai`, `sentry-sdk`, `cosmpy`, `fastapi`, `pydantic`).

---

## 8. Conventions everyone follows

- **job_id** on every message; one user action = one job_id. Use it for logs, Sentry tags, storage keys.
- **Every handler** is wrapped with Kenil's `@traced_agent(...)` decorator and calls `report_error(...)` on failure (sends AgentError to Recovery).
- **Timeouts:** Space build ≤ 120 s; specialist ≤ 60 s; product search ≤ 30 s. Return `ok=False` with a clear `error` instead of hanging.
- **Gemini:** model name from env `GEMINI_MODEL` (use the newest available Flash for speed, Pro where quality matters). Always request structured JSON output.
- **No fake numbers.** Show measured values ("walkway 22 in, walker needs 32 in") and counts ("3 of 4 hazards fixed"), never invented risk percentages.
- **Label honestly:** testnet payment = real Fetch payment; merchant checkout = handoff link; anything mocked says so on the card.

---

## 9. Timeline (assumes Sat 6 PM start of build; shift if needed)

| Checkpoint | Time | Done means |
|---|---|---|
| **A — Contracts + hello** | Sat 9 PM | `shared/models.py` merged; every agent runs locally returning stub results; Coordinator answers in ASI:One; video-upload question answered |
| **B — Skeleton end to end** | Sun 12 AM | Upload → real Space JSON → viewer shows dollhouse → Elder mode returns real findings → cards in ASI:One; Sentry trace spans all agents |
| **C — All modes** | Sun 4 AM | Baby, Interior, Claim working; Product Finder + Cart + Payment Protocol + Insurance Filer working; Recovery demo works |
| **D — Freeze** | Sun 8 AM | No new features. Polish design, run evals, record ASI:One shared chat |
| **E — Submit** | Sun 11:30 AM | Video, Devpost, README, Agentverse profiles, Submission Agent — all done |

---

## 10. Three-minute demo script

1. **0:00–0:20** — Human hook: "We check on our parents, but we can't see the dangers in their homes."
2. **0:20–0:50** — Upload video in ASI:One → 3D dollhouse appears → four mode cards.
3. **0:50–1:30** — Elder: hazards with video evidence → 2am night walk in 3D, walker clips the coffee table (measured).
4. **1:30–2:00** — Fix plan → approve → Payment Protocol card → receipt + checkout handoff.
5. **2:00–2:20** — Quick tour: Baby (toddler-eye view), Interior (style swap), Claim (items float up with values, package ready).
6. **2:20–2:40** — Sentry: we break a tool live → Recovery card → trace + eval dashboard.
7. **2:40–3:00** — "One scan of your home. Every way to protect it."

---

## 11. Submission checklist (Shresth runs it, everyone verifies their part)

- [ ] Every agent registered on Agentverse; profile URLs collected
- [ ] Chat Protocol on Coordinator; usable from asi1.ai
- [ ] Public ASI:One shared chat URL with the full workflow
- [ ] Public GitHub repo, run/test instructions, agent names + addresses, both badges
- [ ] Submitted via ASI:One Submission Agent + Devpost
- [ ] 3–5 min demo video
- [ ] Sentry section: products used + "what Sentry found" screenshots (Kenil)
- [ ] Gemini MLH challenge ticked on Devpost
- [ ] "Real vs labelled" table in Devpost

---

## 12. Risks and fallbacks

| Risk | Fallback |
|---|---|
| ASI:One can't accept video uploads | Card links to our upload page; everything else stays in ASI:One |
| Live Space build slow or wrong on stage | Pre-built, hand-checked Space for the demo home (`scale_method="prebuilt"`) |
| Payment Protocol card not rendering | RequestPayment must be sent **before any LLM call** in that turn; test early |
| Mailbox latency | All internal calls inside the Bureau; mailbox only for ASI:One |
| A merchant link is wrong | Product Finder only returns `url_verified=True` items to the card |
