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
           "check_payment", "payment_opened", "link_opened", "show_results", "show_modes", "other"]
MODES = ["elder", "baby", "transform", "claim"]

_client = AsyncOpenAI(base_url="https://api.asi1.ai/v1", api_key=config.ASI_ONE_API_KEY, timeout=20)

SYSTEM = """You read messages sent to Last Mile Home, a home-safety agent in ASI:One, and decide what the user wants.
The flow: the user shares a video of a home -> picks a mode (elder = elder safety/fall risks, baby = baby-proofing,
transform = repurpose a room such as a home office, claim = insurance claim inventory) -> fills in a short form ->
sees findings and a fix plan -> approves it -> sees a cart of products that fit -> pays a service fee -> confirms
payment and gets the store links. In claim mode, after the inventory the user asks for the claim package instead.
Messages may come from the user directly or from the ASI:One planner describing what the user clicked or typed.
Use the last card shown to the user to resolve what a click or answer refers to.
Messages can be in any language; answer with the same actions and English field values.
The user can switch modes at any time: if they ask for a different mode than the last card's, that is choose_mode with
the new mode (e.g. "actually, turn the bedroom into an office" -> choose_mode, mode=transform, goal="home office",
room_id="bedroom"). Copy any answers the message contains into fields even for choose_mode.
Field meanings: age = the older adult's age in YEARS (elder mode only); child_age_months = the child's age converted
to MONTHS ("18 months" -> "18", "2 years old" -> "24", "1-year-old" -> "12", "newborn" -> "0"); goal = what a room
should become (transform mode only); person = who lives there (elder mode only).
Field formats: mobility_aid is one of none/cane/walker/wheelchair; night_trips is "true" or "false"; policy_type is
replacement_cost/actual_cash_value/unknown; numbers as plain digits ("$1,200" -> "1200"); room_id is the room name.
Actions:
- choose_mode: user picks a mode, or asks for a mode's check/report/assessment without giving the form answers (set mode)
- submit_intake: user answers the form questions (set mode and copy every answer into fields, as plain strings).
  Only when the last card shown is a form or the message gives new answers: after results are shown, a message that
  restates earlier answers and asks for products, recommendations, prices, a shopping list or to proceed is approve_plan
- finding_detail: user asks about one specific finding (copy its exact finding_id from the card's on_click; never invent one)
- approve_plan: user approves the fix plan, picks fixes, wants products or a cart, or wants to pay; in claim mode,
  asks to price the items or build/download the claim package
- decline_plan: user declines or cancels
- check_payment: user says they paid or asks if the payment went through
- payment_opened: user opened the checkout / tapped Pay but hasn't confirmed paying yet
- link_opened: user opened a store link or a download link from a card
- show_results: user wants to see the results again
- show_modes: user wants the list of options or another mode without naming one
- other: anything else (greetings, questions)
Only fill fields with answers the message actually contains; use null otherwise."""


def _custom_actions(node):
    """Buttons, list rows and pickers in a custom card tree."""
    if isinstance(node, dict):
        if node.get("type") == "button":
            yield {"button": node.get("label"), "on_click": (node.get("action") or {}).get("selection")}
        elif node.get("type") == "choice_grid":
            yield {"picker": node.get("name"), "options": [c.get("value") for c in node.get("choices", [])]}
        for child in node.get("children", []) or []:
            yield from _custom_actions(child)
        for item in node.get("items", []) or []:
            if not isinstance(item, dict):
                continue
            if item.get("action"):
                heading = next((c.get("value") for c in item.get("children", []) if c.get("type") == "heading"), None)
                yield {"row": heading, "on_click": item["action"].get("selection")}
            elif item.get("label"):
                yield {"section": item["label"]}
            yield from _custom_actions(item)


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
    elif kind == "custom":
        body = list(_custom_actions(p.get("root", {})))
    else:
        body = [c.get("selection") for c in p.get("ctas", [])]
    return json.dumps({"kind": kind, "title": p.get("title"), "content": body})[:3000]


ALL_FIELDS = ["person", "age", "mobility_aid", "night_trips", "child_age_months", "goal", "room_id",
              "requirements", "style", "budget_usd", "policy_type", "zip_code"]


def _schema(card: dict | None) -> dict:
    # Always allow every answer field: users volunteer answers for other modes too (mode switches).
    field_names = list(ALL_FIELDS)
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


# The model sometimes drops answers the message plainly states ("84-year-old ... uses a walker
# ... gets up at night" came back as choose_mode with no fields), which sends the user back to
# a form they already answered. These patterns fill only what's missing; the model wins otherwise.
_PATTERNS = [
    ("mobility_aid", r"\bwheel ?chairs?\b", "wheelchair"),
    ("mobility_aid", r"\b(?:walker|rollator)s?\b", "walker"),
    ("mobility_aid", r"\bcanes?\b", "cane"),
    ("night_trips", r"\bsleeps? through the night\b|\bno (?:night|nighttime) trips\b", "false"),
    ("night_trips", r"\b(?:up|gets? up|wakes? up|trips?|walks?|bathroom)\b[^.]{0,40}\b(?:at|during the) night\b|\bnight(?:time)? (?:trips?|bathroom)", "true"),
    ("policy_type", r"\breplacement[- ]cost\b", "replacement_cost"),
    ("policy_type", r"\bactual[- ]cash[- ]value\b|\bACV\b", "actual_cash_value"),
]


def fill_missing(text: str, selection: dict) -> dict:
    """Copy answers the text clearly states into fields the model left empty."""
    import re

    out = dict(selection)
    for field, pattern, value in _PATTERNS:
        if not out.get(field) and re.search(pattern, text, re.I):
            out[field] = value
    if not out.get("budget_usd"):
        m = re.search(r"budget[^\d$]{0,20}\$?\s?(\d[\d,]*)|\$\s?(\d[\d,]*)\s*budget", text, re.I)
        if m:
            out["budget_usd"] = (m.group(1) or m.group(2)).replace(",", "")
    if not out.get("zip_code"):
        m = re.search(r"\b(?:zip|postal)(?: code)?\D{0,10}(\d{5})\b", text, re.I)
        if m:
            out["zip_code"] = m.group(1)
    child = re.search(r"\b(toddler|baby|infant|child|kid|son|daughter|newborn)\b", text, re.I)
    if child and not out.get("child_age_months"):
        m = re.search(r"\b(\d{1,2})[- ]?(?:months?|mos?)\b", text, re.I)
        y = re.search(r"\b(\d)[- ]?(?:years?|yrs?)[- ]?old\b", text, re.I)
        if m:
            out["child_age_months"] = m.group(1)
        elif y:
            out["child_age_months"] = str(int(y.group(1)) * 12)
    if not child and not out.get("age"):
        m = re.search(r"\b(\d{2,3})[- ]?(?:years?|yrs?)[- ]?old\b|\b(?:is|aged?|she's|he's) (\d{2,3})\b", text, re.I)
        if m and 40 <= int(m.group(1) or m.group(2)) <= 120:
            out["age"] = m.group(1) or m.group(2)
    return out
