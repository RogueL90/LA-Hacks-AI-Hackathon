"""Interactive Card payloads for the Coordinator (ASI:One card protocol v1)."""
from shared.models import Finding, ModeResult

MODES = {
    "elder": {
        "title": "Elder safety",
        "subtitle": "Fall hazards, walker clearance and the 2 am walk to the bathroom",
        "frame": 10,
    },
    "baby": {
        "title": "Baby-proofing",
        "subtitle": "Hazards at a toddler's eye level: outlets, corners, cords and stairs",
        "frame": 35,
    },
    "transform": {
        "title": "Space transformer",
        "subtitle": "Turn a room into something new, like a home office, with real products that fit",
        "frame": 60,
    },
    "claim": {
        "title": "Insurance claim",
        "subtitle": "List and value everything you own, with evidence, for a claim package",
        "frame": 85,
    },
}


def space_ready(frames: dict[str, str], viewer_url: str | None) -> dict:
    """Carousel: one item per mode. `frames` maps mode -> image URL."""
    items = []
    for mode, info in MODES.items():
        items.append({
            "id": mode,
            "image": frames[mode],
            "title": info["title"],
            "subtitle": info["subtitle"],
            "badges": [{"label": "From your video", "variant": "info"}],
            "secondary_text": "Takes about a minute",
            "primary_cta": {"label": "Start", "selection": {"action": "choose_mode", "mode": mode}},
        })
    subtitle = "Your home is mapped. Pick what you'd like to do."
    if viewer_url:
        subtitle += f" 3D view: {viewer_url}"
    return {"title": "What should we look at?", "subtitle": subtitle, "items": items}


def intake_form(mode: str, rooms: list[dict]) -> dict:
    """Form card with the questions each mode needs. `rooms` is [{"value", "label"}]."""
    budget = {"name": "budget_usd", "kind": "number", "label": "Budget for fixes (USD)", "required": False}
    if mode == "elder":
        fields = [
            {"name": "person", "kind": "text", "label": "Who lives here? (e.g. Mom)", "required": False},
            {"name": "age", "kind": "number", "label": "Their age", "required": False},
            {
                "name": "mobility_aid", "kind": "select", "label": "Mobility aid", "required": True,
                "options": [
                    {"value": "none", "label": "None"},
                    {"value": "cane", "label": "Cane"},
                    {"value": "walker", "label": "Walker"},
                    {"value": "wheelchair", "label": "Wheelchair"},
                ],
            },
            {"name": "night_trips", "kind": "checkbox", "label": "Gets up at night to use the bathroom", "required": False},
            budget,
        ]
        title = "A few questions about who lives here"
    elif mode == "baby":
        fields = [
            {"name": "child_age_months", "kind": "number", "label": "Child's age in months", "required": True},
            budget,
        ]
        title = "A few questions about your child"
    elif mode == "transform":
        fields = [
            {"name": "goal", "kind": "text", "label": "What should this space become? (e.g. home office)", "required": True},
            {"name": "room_id", "kind": "select", "label": "Which room", "required": True, "options": rooms},
            {"name": "requirements", "kind": "text", "label": "Anything it must have? (e.g. two monitors, video calls)", "required": False},
            {"name": "style", "kind": "text", "label": "Style (e.g. warm modern, japandi)", "required": False},
            {"name": "budget_usd", "kind": "number", "label": "Budget (USD)", "required": True},
        ]
        title = "What should this space become?"
    else:
        fields = [
            {
                "name": "policy_type", "kind": "select", "label": "Your policy pays", "required": True,
                "options": [
                    {"value": "replacement_cost", "label": "Replacement cost (new for old)"},
                    {"value": "actual_cash_value", "label": "Actual cash value (after depreciation)"},
                    {"value": "unknown", "label": "Not sure"},
                ],
            },
            {"name": "zip_code", "kind": "text", "label": "ZIP code", "required": True},
        ]
        title = "A few questions about your policy"
    return {
        "title": title,
        "fields": fields,
        "submit_cta": {"label": "Run the check", "selection": {"action": "submit_intake", "mode": mode}},
    }


def _finding_subtitle(f: Finding) -> str:
    parts = []
    for m in f.measurements:
        text = f"{m.name.replace('_', ' ')}: {m.value:g} {m.unit}"
        if m.required is not None:
            text += f" (needs {m.required:g} {m.unit})"
        parts.append(text)
    if f.value_usd is not None:
        parts.append(f"${f.value_usd:,.0f} ({f.value_basis or 'estimate'})")
    return " · ".join(parts) or (f.fix_summary or "")


def findings_carousel(result: ModeResult, fallback_image: str) -> dict:
    items = []
    for f in result.findings:
        badges = []
        if f.kind == "hazard":
            variant = "warning" if f.severity >= 3 else "info"
            badges.append({"label": f"Severity {f.severity}/5", "variant": variant})
        image = next((e.frame_url for e in f.evidence if e.frame_url), None) or fallback_image
        items.append({
            "id": f.id,
            "image": image,
            "title": f.title,
            "subtitle": _finding_subtitle(f),
            "badges": badges,
            "secondary_text": f.fix_summary or "",
            "primary_cta": {"label": "Details", "selection": {"action": "finding_detail", "finding_id": f.id}},
        })
    return {"title": MODES[result.mode]["title"], "subtitle": result.summary, "items": items}


def fix_plan_review(result: ModeResult, fee_label: str) -> dict:
    fixes = [f for f in result.findings if f.fix_summary]
    rows = [{"label": f.title, "value": f.fix_summary} for f in fixes[:8]]
    rows.append({"label": "Service fee", "value": fee_label})
    return {
        "title": "Your fix plan",
        "summary_rows": rows,
        "approve_cta": {"label": "Approve and find products", "selection": {"action": "approve_plan"}, "primary": True},
        "reject_cta": {"label": "Not now", "selection": {"action": "decline_plan"}},
    }


def payment_check(fee_label: str) -> dict:
    return {
        "title": "Pay the service fee",
        "summary_rows": [
            {"label": "Fee", "value": fee_label},
            {"label": "You get", "value": "Products that fit your measured space, with checkout links"},
            {"label": "Test card", "value": "4242 4242 4242 4242, any future date, any CVC"},
        ],
        "approve_cta": {"label": "I've paid", "selection": {"action": "check_payment"}, "primary": True},
        "reject_cta": {"label": "Cancel", "selection": {"action": "decline_plan"}},
    }


def results_card(result: ModeResult, image: str, fee_label: str | None) -> dict:
    """Custom card: findings list (tap for details) plus Approve and Other modes buttons."""
    rows = []
    for f in result.findings[:10]:
        children = [{"type": "heading", "value": f.title, "level": 3}]
        detail = _finding_subtitle(f)
        if detail:
            children.append({"type": "text", "value": detail})
        if f.fix_summary and f.fix_summary != detail:
            children.append({"type": "text", "value": f"Fix: {f.fix_summary}", "style": "muted"})
        if f.kind == "hazard":
            children.append({"type": "badge", "label": f"Severity {f.severity}/5",
                             "variant": "warning" if f.severity >= 3 else "info"})
        rows.append({"children": children, "action": {"selection": {"action": "finding_detail", "finding_id": f.id}}})
    buttons = []
    if fee_label:
        buttons.append({"type": "button", "label": "Approve plan", "primary": True,
                        "action": {"selection": {"action": "approve_plan"}}})
    buttons.append({"type": "button", "label": "Other modes", "action": {"selection": {"action": "show_modes"}}})
    footer = [{"type": "text", "value": f"Service fee if you approve: {fee_label}", "style": "muted"}] if fee_label else []
    return {"root": {
        "type": "section",
        "title": MODES[result.mode]["title"],
        "subtitle": result.summary,
        "children": [
            {"type": "image", "src": image, "alt": "Frame from your video", "aspect_ratio": "16:9"},
            {"type": "list", "items": rows},
            {"type": "divider"},
            *footer,
            {"type": "group", "direction": "row", "gap": 8, "children": buttons},
        ],
    }}
