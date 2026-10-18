"""Ask anything: answer any question or run any other check on the mapped home with Claude.

The four fixed modes cover their checks with deterministic rules. Everything else ("will a
7 ft sofa fit in the living room?", "pet-proof it for a puppy", "is it wheelchair friendly?")
comes here: Claude reads the measured home and the request, answers in plain words, and, when
the request is a check, returns findings tied to real object ids so they get pins in the 3D
view and can go through the same products -> cart -> payment flow.
"""
import os
from typing import Literal, Optional

import anthropic
from pydantic import BaseModel, Field

from agents.specialists.geometry import M_TO_IN, bounds, inches, pin
from shared.models import Finding, Overlay, ProductQuery, Profile, Space

MODEL = os.getenv("GENERAL_MODEL", "claude-sonnet-5-5")  # fast enough to answer inside ASI:One's ~60 s wait
EFFORT = os.getenv("GENERAL_EFFORT", "low")
TIMEOUT_S = 40.0
MAX_FINDINGS = 10

PROMPT = """You are the home advisor in Last Mile Home. A real home was mapped in 3D from the user's video; its
measurements are below. Do what the user asks, using only this data.

- A question (will something fit, how big is a room, how many of something, where to put something): answer it
  directly with numbers in feet and inches. If it depends on something the video doesn't show, say so.
- A check (pet-proofing, wheelchair access, earthquake or fire safety, allergies, Airbnb readiness, a move...):
  list concrete findings, most serious first, each tied to the objects it is about by their exact ids. Give a
  short fix, and a shop query when buying something fixes it (a product a store sells, e.g. "pet gate 30 in
  tall pressure mounted"). At most 10 findings; merge repeats of the same issue into one finding.
- Never invent objects or ids. Positions are meters (x right, z forward); sizes are width x height x depth.
  Objects with low confidence may be misidentified: say "looks like" for those.
- answer: at most 90 words, plain sentences, no markdown headings.
- title: 2 to 4 words naming what you did ("Pet-proofing", "Sofa fit check", "Wheelchair access").

{budget}User's request: {request}

The home:
{home}"""


class AdvisorFinding(BaseModel):
    title: str = Field(description="Short, specific: 'Cords behind the TV stand within a puppy's reach'")
    kind: Literal["hazard", "suggestion"]
    severity: int = Field(ge=1, le=5, description="5 critical ... 1 minor; suggestions are 1 or 2")
    object_ids: list[str]
    fix: str
    shop_query: Optional[str] = None
    quantity: int = 1


class AdvisorAnswer(BaseModel):
    title: str
    answer: str
    findings: list[AdvisorFinding]


def describe_home(space: Space) -> str:
    """A compact text version of the Space for the prompt (rooms, doors, objects with sizes)."""
    names = {r.id: r.name for r in space.rooms}
    lines = ["Rooms:"]
    for r in space.rooms:
        x0, x1, z0, z1 = bounds(r)
        w, d = x1 - x0, z1 - z0
        lines.append(f"- {r.id} '{r.name}': {_feet(w)} x {_feet(d)} ({w * d * 10.764:.0f} sq ft), ceiling {_feet(r.height_m)}")
    if space.doors:
        lines.append("Doors:")
        lines += [f"- {d.id} in {names.get(d.room_id, d.room_id)}: {inches(d.width_m):g} in wide" for d in space.doors]
    lines.append("Objects (id | type | label | room | size W x H x D in | position m | notes):")
    for o in space.objects:
        notes = [k for k, v in o.attributes.items() if v is True]
        notes += [f"{k}={v}" for k, v in o.attributes.items() if isinstance(v, (int, float, str)) and not isinstance(v, bool) and v not in ("", 0)]
        if o.confidence < 0.6:
            notes.append(f"confidence {o.confidence:.1f}")
        size = " x ".join(f"{s * M_TO_IN:.0f}" for s in o.size)
        pos = ", ".join(f"{p:.1f}" for p in o.position)
        lines.append(f"- {o.id} | {o.type} | {o.label} | {names.get(o.room_id, o.room_id)} | {size} | {pos} | {'; '.join(notes)}")
    return "\n".join(lines)


def _feet(m: float) -> str:
    total = round(m * M_TO_IN)
    return f"{total // 12}'{total % 12}\""


async def analyze(space: Space, profile: Profile) -> tuple[str, list[Finding], list[Overlay], str]:
    """(summary, findings, overlays, title). The summary is the answer shown to the user."""
    request = (profile.requirements or "").strip() or "Give me a quick overview of this home."
    budget = f"Budget for fixes: ${profile.budget_usd:,.0f}.\n" if profile.budget_usd else ""
    client = anthropic.AsyncAnthropic(timeout=TIMEOUT_S, max_retries=1)
    response = await client.beta.messages.parse(
        model=MODEL,
        max_tokens=4000,
        messages=[{"role": "user", "content": PROMPT.format(budget=budget, request=request, home=describe_home(space))}],
        output_format=AdvisorAnswer,
        output_config={"effort": EFFORT},
    )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        return "I can't help with that request about this home.", [], [], "Ask anything"
    out: AdvisorAnswer = response.parsed_output
    objects = {o.id: o for o in space.objects}
    findings: list[Finding] = []
    overlays: list[Overlay] = []
    for i, a in enumerate(out.findings[:MAX_FINDINGS]):
        ids = [x for x in a.object_ids if x in objects]  # drop any id the model made up
        f = Finding(
            id=f"general_{i}", kind=a.kind, title=a.title,
            severity=a.severity, object_ids=ids, fix_summary=a.fix,
            product_query=ProductQuery(query=a.shop_query, quantity=max(1, a.quantity),
                                       max_price_usd=profile.budget_usd) if a.shop_query else None,
            evidence=[e.copy(update={"note": a.title}) for e in objects[ids[0]].evidence[:1]] if ids else [],
        )
        findings.append(f)
        if ids:
            pin(overlays, f, objects[ids[0]].position)
    findings.sort(key=lambda f: -f.severity)
    return out.answer, findings, overlays, out.title
