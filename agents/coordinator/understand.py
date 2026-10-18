"""Turn free text into a card selection with ASI:One.

Direct @mention chats send card selections as JSON, but when ASI:One's planner relays a
tap or a form it sends prose ("The user selected mode \"elder\" on the card..."). This
module maps that prose, plus ordinary requests, onto the same selection dicts.
"""
import json

from openai import AsyncOpenAI

from shared import config

MODEL = "asi1-mini"
ACTIONS = ["choose_mode", "submit_intake", "finding_detail", "approve_plan", "decline_plan",
           "check_payment", "show_modes", "other"]
MODES = ["elder", "baby", "transform", "claim"]

_client = AsyncOpenAI(base_url="https://api.asi1.ai/v1", api_key=config.ASI_ONE_API_KEY, timeout=20)

SYSTEM = """You read messages sent to Last Mile Home, a home-safety agent in ASI:One, and decide what the user wants.
The flow: the user shares a video of a home -> picks a mode (elder = elder safety/fall risks, baby = baby-proofing,
transform = repurpose a room such as a home office, claim = insurance claim inventory) -> fills in a short form ->
sees findings and a fix plan -> approves it -> pays a service fee -> confirms payment.
Messages may come from the user directly or from the ASI:One planner describing what the user clicked or typed.
Use the last card shown to the user to resolve what a click or answer refers to.
Actions:
- choose_mode: user picks a mode, or asks for a mode's check/report/assessment without giving the form answers (set mode)
- submit_intake: user answers the form questions (set mode and copy every answer into fields, as plain strings)
- finding_detail: user asks about one specific finding (set finding_id from the card)
- approve_plan: user approves the fix plan, wants products, or wants to pay
- decline_plan: user declines or cancels
- check_payment: user says they paid or asks if the payment went through
- show_modes: user wants the list of options or another mode without naming one
- other: anything else (greetings, questions)
Only fill fields with answers the message actually contains; use null otherwise."""


def _card_summary(card: dict | None) -> str:
    if not card:
        return "none"
    kind, p = card.get("kind"), card.get("payload", {})
    if kind == "carousel":
        body = [{"title": i.get("title"), "on_click": i.get("primary_cta", {}).get("selection")} for i in p.get("items", [])]
    elif kind == "form":
        body = {"fields": [{"name": f["name"], "label": f["label"], "options": [o["value"] for o in f.get("options", [])]}
                           for f in p.get("fields", [])],
                "on_submit": p.get("submit_cta", {}).get("selection")}
    elif kind == "review":
        body = {"approve": p.get("approve_cta", {}).get("selection"), "reject": p.get("reject_cta", {}).get("selection")}
    else:
        body = [c.get("selection") for c in p.get("ctas", [])]
    return json.dumps({"kind": kind, "title": p.get("title"), "content": body})[:3000]


def _schema(card: dict | None) -> dict:
    field_names = []
    if card and card.get("kind") == "form":
        field_names = [f["name"] for f in card["payload"].get("fields", [])]
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["action", "mode", "finding_id", "fields"],
        "properties": {
            "action": {"type": "string", "enum": ACTIONS},
            "mode": {"type": ["string", "null"], "enum": MODES + [None]},
            "finding_id": {"type": ["string", "null"]},
            "fields": {
                "type": "object",
                "additionalProperties": False,
                "required": field_names,
                "properties": {name: {"type": ["string", "null"]} for name in field_names},
            },
        },
    }


async def understand(text: str, last_card: dict | None) -> dict:
    """A selection dict like the cards produce, e.g. {"action": "choose_mode", "mode": "elder"}."""
    try:
        r = await _client.chat.completions.create(
            model=MODEL,
            temperature=0,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": f"Last card shown: {_card_summary(last_card)}\n\nMessage: {text}"},
            ],
            response_format={"type": "json_schema",
                             "json_schema": {"name": "selection", "strict": True, "schema": _schema(last_card)}},
        )
        result = json.loads(r.choices[0].message.content)
    except Exception:
        return {"action": "other"}
    selection = {"action": result["action"]}
    if result.get("mode"):
        selection["mode"] = result["mode"]
    if result.get("finding_id"):
        selection["finding_id"] = result["finding_id"]
    selection.update({k: v for k, v in (result.get("fields") or {}).items() if v not in (None, "")})
    return selection
