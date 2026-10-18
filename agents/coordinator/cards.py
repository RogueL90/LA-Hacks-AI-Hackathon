"""Interactive Card payloads for the Coordinator (ASI:One card protocol v1)."""
from shared.models import CartResult, ClaimPackage, Finding, ModeResult, ProductQuote

MODES = {
    "elder": {
        "title": "Elder safety",
        "subtitle": "Fall hazards, walker clearance and the 2 am walk to the bathroom",
        "badge": "CDC STEADI checks",
        "frame": 10,
    },
    "baby": {
        "title": "Baby-proofing",
        "subtitle": "Hazards at a toddler's eye level: outlets, corners, cords and stairs",
        "badge": "Toddler's-eye view",
        "frame": 35,
    },
    "transform": {
        "title": "Space transformer",
        "subtitle": "Turn a room into something new, like a home office, with real products that fit",
        "badge": "Sized to your walls",
        "frame": 60,
    },
    "claim": {
        "title": "Insurance claim",
        "subtitle": "List and value everything you own, with evidence, for a claim package",
        "badge": "Item-by-item evidence",
        "frame": 85,
    },
}


def space_ready(frames: dict[str, str], stats: str) -> dict:
    """Slide carousel, one big card per mode. `frames` maps mode -> image URL."""
    items = []
    for mode, info in MODES.items():
        items.append({
            "id": mode,
            "image": frames[mode],
            "title": info["title"],
            "subtitle": info["subtitle"],
            "badges": [{"label": info["badge"], "variant": "info"}],
            "secondary_text": "About a minute",
            "primary_cta": {"label": f"Start {info['title'].lower()}", "selection": {"action": "choose_mode", "mode": mode}},
        })
    return {"title": "Your home is mapped", "subtitle": stats, "style": "slide", "items": items}


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
            ({"name": "room_id", "kind": "select", "label": "Which room", "required": True, "options": rooms} if rooms
             else {"name": "room_id", "kind": "text", "label": "Which room? (e.g. bedroom)", "required": True}),
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


SEVERITY = {5: ("Critical", "warning"), 4: ("Serious", "warning"), 3: ("Moderate", "info"),
            2: ("Minor", "info"), 1: ("Minor", "info")}
MEASURE_NAMES = {
    "walkway_clearance": "Clear path", "door_width": "Door width", "seat_height": "Seat height",
    "cord_length_on_floor": "Cord on floor", "height_from_floor": "Off the floor", "height": "Height",
    "corner_height": "Corner height", "free_wall_length": "Free wall",
}


def _measure(f: Finding) -> str:
    """'Clear path 14 in · needs 32 in'."""
    parts = []
    for m in f.measurements:
        text = f"{MEASURE_NAMES.get(m.name, m.name.replace('_', ' ').capitalize())} {m.value:g} {m.unit}"
        if m.required is not None:
            text += f" · needs {m.required:g} {m.unit}"
        parts.append(text)
    return " · ".join(parts)


def _severity_badge(f: Finding) -> dict:
    label, variant = SEVERITY.get(f.severity, ("Moderate", "info"))
    return {"label": label, "variant": variant}


def _buttons(fee_label: str | None, approve: str = "Find products") -> dict:
    buttons = []
    if fee_label:
        buttons.append({"type": "button", "label": approve, "primary": True,
                        "action": {"selection": {"action": "approve_plan"}}})
    buttons.append({"type": "button", "label": "Other checks", "action": {"selection": {"action": "show_modes"}}})
    return {"type": "group", "direction": "row", "gap": 8, "children": buttons}


def _finding_row(f: Finding) -> dict:
    children = [{"type": "heading", "value": f.title, "level": 3}]
    measure = _measure(f)
    if measure:
        children.append({"type": "text", "value": measure, "style": "emphasis"})
    if f.fix_summary:
        children.append({"type": "text", "value": f"Fix: {f.fix_summary}", "style": "muted"})
    if f.kind == "hazard":
        children.append({"type": "badge", **_severity_badge(f)})
    return {"children": children, "action": {"selection": {"action": "finding_detail", "finding_id": f.id}}}


def _picker(name: str, title: str, findings: list[Finding], label) -> list[dict]:
    if not findings:
        return []
    return [
        {"type": "heading", "value": title, "level": 3},
        {"type": "choice_grid", "name": name, "multi": True,
         "choices": [{"value": f.id, "label": label(f)} for f in findings]},
    ]


def _hazard_results(result: ModeResult, image: str, fee_label: str | None) -> dict:
    hazards = [f for f in result.findings if f.kind == "hazard"]
    counts: dict[str, int] = {}
    for f in hazards:
        name = SEVERITY.get(f.severity, ("Moderate", ""))[0]
        counts[name] = counts.get(name, 0) + 1
    tally = [{"type": "badge", "label": f"{n} {label.lower()}", "variant": "warning" if label in ("Critical", "Serious") else "info"}
             for label, n in counts.items()]
    fixes = [f for f in result.findings if f.fix_summary]
    picker = _picker("fix_ids", "Pick the fixes you want", fixes,
                     lambda f: f"{f.fix_summary.split(' (')[0].split(', which')[0]} ({SEVERITY.get(f.severity, ('Moderate',))[0].lower()})"
                     ) if fee_label else []
    footer = [{"type": "text", "value": f"I'll search real stores for products that fit your measurements and show you a cart. "
                                        f"Service fee {fee_label}, only if I find something.", "style": "muted"}] if fee_label else []
    return {"root": {
        "type": "section",
        "title": f"{MODES[result.mode]['title']} · {len(hazards)} hazard{'s' if len(hazards) != 1 else ''}",
        "subtitle": result.summary,
        "children": [
            {"type": "image", "src": image, "alt": "Frame from your video", "aspect_ratio": "16:9"},
            {"type": "group", "direction": "row", "gap": 6, "children": tally},
            {"type": "list", "items": [_finding_row(f) for f in result.findings[:10]]},
            {"type": "divider"},
            *picker,
            *footer,
            _buttons(fee_label),
        ],
    }}


def _transform_results(result: ModeResult, image: str, fee_label: str | None) -> dict:
    layout = [f for f in result.findings if f.id == "transform_wall"]
    keeps = [f for f in result.findings if f.id.startswith("transform_keep")]
    moves = [f for f in result.findings if f.id.startswith("transform_move")]
    adds = [f for f in result.findings if f.id.startswith("transform_item")]
    rows = []
    for f in layout:
        rows.append({"children": [{"type": "heading", "value": f.title, "level": 3},
                                  {"type": "text", "value": f.fix_summary or "", "style": "muted"},
                                  {"type": "badge", "label": "Layout", "variant": "info"}]})
    for f in keeps:
        rows.append({"children": [{"type": "heading", "value": f.title, "level": 3},
                                  {"type": "badge", "label": "Keep", "variant": "info"}]})
    for f in moves:
        rows.append({"children": [{"type": "heading", "value": f.title, "level": 3},
                                  {"type": "text", "value": f.fix_summary or "", "style": "muted"},
                                  {"type": "badge", "label": "Move out", "variant": "warning"}]})
    for f in adds:
        rows.append({"children": [{"type": "heading", "value": f.title.replace("Add: ", ""), "level": 3},
                                  {"type": "text", "value": f.fix_summary or "", "style": "emphasis"},
                                  {"type": "badge", "label": "Add", "variant": "success"}]})
    picker = _picker("fix_ids", "What should I shop for?", adds, lambda f: f.title.replace("Add: ", "")) if fee_label else []
    footer = [{"type": "text", "value": f"I'll search real stores for products that fit these sizes and show you a cart. "
                                        f"Service fee {fee_label}, only if I find something.", "style": "muted"}] if fee_label else []
    return {"root": {
        "type": "section",
        "title": "Space transformer",
        "subtitle": result.summary,
        "children": [
            {"type": "image", "src": image, "alt": "Frame from your video", "aspect_ratio": "16:9"},
            {"type": "list", "items": rows},
            {"type": "divider"},
            *picker,
            *footer,
            _buttons(fee_label, "Find products"),
        ],
    }}


def _claim_results(result: ModeResult, image: str) -> dict:
    rooms: dict[str, list] = {}
    for f in result.findings:
        rooms.setdefault((f.fix_summary or "Home").split(" · ")[0], []).append(f)
    rows = [{"children": [
        {"type": "heading", "value": f"{room} · {len(items)} item{'s' if len(items) != 1 else ''}", "level": 3},
        {"type": "text", "value": ", ".join(f.title for f in items)},
        {"type": "badge", "label": "Ready to price", "variant": "info"},
    ]} for room, items in rooms.items()]
    return {"root": {
        "type": "section",
        "title": f"Insurance claim · {len(result.findings)} items",
        "subtitle": result.summary,
        "children": [
            {"type": "image", "src": image, "alt": "Frame from your video", "aspect_ratio": "16:9"},
            {"type": "list", "items": rows},
            {"type": "divider"},
            {"type": "text", "value": "Next: today's replacement price for each item, then your claim package (spreadsheet and cover letter).",
             "style": "muted"},
            {"type": "group", "direction": "row", "gap": 8, "children": [
                {"type": "button", "label": "Build my claim package", "primary": True,
                 "action": {"selection": {"action": "approve_plan"}}},
                {"type": "button", "label": "Other checks", "action": {"selection": {"action": "show_modes"}}},
            ]},
        ],
    }}


def results_card(result: ModeResult, image: str, fee_label: str | None) -> dict:
    if result.mode == "transform":
        return _transform_results(result, image, fee_label)
    if result.mode == "claim":
        return _claim_results(result, image)
    return _hazard_results(result, image, fee_label)


def finding_detail(f: Finding, image: str) -> dict:
    rows = [{"label": MEASURE_NAMES.get(m.name, m.name.replace("_", " ").capitalize()),
             "value": f"{m.value:g} {m.unit}" + (f" (needs {m.required:g} {m.unit})" if m.required is not None else "")}
            for m in f.measurements]
    if f.kind == "hazard":
        rows.append({"label": "Severity", "value": f"{SEVERITY.get(f.severity, ('Moderate',))[0]} ({f.severity} of 5)"})
    if f.fix_summary:
        rows.append({"label": "Fix", "value": f.fix_summary})
    note = next((e.note for e in f.evidence if e.note), None)
    if note:
        rows.append({"label": "Evidence", "value": note})
    return {
        "title": f.title,
        "hero_image": image,
        "summary_rows": rows,
        "ctas": [
            {"label": "Back to results", "primary": True, "selection": {"action": "show_results"}},
            {"label": "Other checks", "selection": {"action": "show_modes"}},
        ],
    }


def _money(value: float) -> str:
    return f"${value:,.2f}"


def _quote_row(q: ProductQuote, link: bool) -> dict:
    qty = int((q.specs or {}).get("quantity", 1) or 1)
    price = f"{_money(q.price_usd)}" + (f" × {qty}" if qty > 1 else "")
    children = [
        {"type": "heading", "value": q.title, "level": 3},
        {"type": "text", "value": f"{price} · {q.merchant}", "style": "emphasis"},
    ]
    if q.fit_note:
        children.append({"type": "text", "value": q.fit_note.split(". ", 1)[-1], "style": "muted"})
    if (q.specs or {}).get("role") == "backup":
        children.append({"type": "badge", "label": "Backup pick", "variant": "info"})
    if link:
        children.append({"type": "button", "label": f"Open at {q.merchant}",
                         "action": {"selection": {"action": "link_opened"}, "redirect": q.url}})
    return {"children": children}


def cart_card(cart: CartResult, budget: float | None, fee_label: str, checkout_url: str) -> dict:
    """The products found for the chosen fixes, then the service fee (store links come after paying)."""
    if budget is None:
        budget_badge = {"type": "badge", "label": "No budget set", "variant": "info"}
    elif cart.within_budget:
        budget_badge = {"type": "badge", "label": f"Within your {_money(budget)} budget", "variant": "success"}
    else:
        budget_badge = {"type": "badge", "label": f"Over your {_money(budget)} budget", "variant": "warning"}
    return {"root": {
        "type": "section",
        "title": f"Your cart · {len(cart.items)} product{'s' if len(cart.items) != 1 else ''}",
        "subtitle": f"Subtotal {_money(cart.subtotal_usd)}, most important fixes first",
        "children": [
            {"type": "group", "direction": "row", "gap": 6, "children": [
                budget_badge, {"type": "badge", "label": "Store pages checked", "variant": "success"}]},
            {"type": "list", "items": [_quote_row(q, link=False) for q in cart.items[:10]]},
            {"type": "divider"},
            {"type": "text", "value": f"Pay the {fee_label} service fee to get the store link for every item. "
                                      "You buy on each store's site: this is a handoff, not an order."},
            {"type": "text", "value": "Stripe test mode · test card 4242 4242 4242 4242 · any future date · any CVC",
             "style": "muted"},
            {"type": "group", "direction": "row", "gap": 8, "children": [
                {"type": "button", "label": f"Pay {fee_label} securely", "primary": True,
                 "action": {"selection": {"action": "payment_opened"}, "redirect": checkout_url}},
                {"type": "button", "label": "I've paid", "action": {"selection": {"action": "check_payment"}}},
            ]},
        ],
    }}


def payment_card(fee_label: str, checkout_url: str) -> dict:
    return {"root": {
        "type": "section",
        "title": "One step left",
        "subtitle": f"Service fee {fee_label}",
        "children": [
            {"type": "text", "value": "Pay the service fee to get the store link for every product in your cart."},
            {"type": "group", "direction": "row", "gap": 6, "children": [
                {"type": "badge", "label": "Secure Stripe checkout", "variant": "success"},
                {"type": "badge", "label": "Test mode", "variant": "info"},
            ]},
            {"type": "text", "value": "Test card 4242 4242 4242 4242 · any future date · any CVC", "style": "muted"},
            {"type": "group", "direction": "row", "gap": 8, "children": [
                {"type": "button", "label": f"Pay {fee_label.split(' ')[0]} securely", "primary": True,
                 "action": {"selection": {"action": "payment_opened"}, "redirect": checkout_url}},
                {"type": "button", "label": "I've paid", "action": {"selection": {"action": "check_payment"}}},
            ]},
        ],
    }}


def receipt_card(amount: str, reference: str, cart: CartResult | None = None) -> dict:
    items = cart.items if cart else []
    children = [
        {"type": "group", "direction": "row", "gap": 6, "children": [
            {"type": "badge", "label": "Paid", "variant": "success"},
            {"type": "badge", "label": "Stripe test mode, not a real charge", "variant": "info"}]},
        {"type": "text", "value": f"Reference {reference}", "style": "muted"},
    ]
    if items:
        children += [
            {"type": "heading", "value": "Your store links", "level": 3},
            {"type": "list", "items": [_quote_row(q, link=True) for q in items[:10]]},
            {"type": "text", "value": "These links open each store's product page. Nothing has been ordered for you.",
             "style": "muted"},
        ]
    children.append({"type": "button", "label": "Other checks", "action": {"selection": {"action": "show_modes"}}})
    return {"root": {
        "type": "section",
        "title": "Payment received",
        "subtitle": f"{amount} service fee" + (f" · subtotal {_money(cart.subtotal_usd)} at the stores" if items else ""),
        "children": children,
    }}


def claim_package_card(pkg: ClaimPackage, priced: list[Finding], unpriced: int, image: str) -> dict:
    top = sorted(priced, key=lambda f: -(f.value_usd or 0))[:6]
    rows = [{"children": [
        {"type": "heading", "value": f.title, "level": 3},
        {"type": "text", "value": f"{_money(f.value_usd or 0)} · {(f.fix_summary or '').split(' · ')[0]}", "style": "emphasis"},
    ]} for f in top]
    downloads = [(label, url) for label, url in (("Inventory (Excel)", pkg.inventory_xlsx_url),
                                                 ("Inventory (CSV)", pkg.inventory_csv_url),
                                                 ("Cover letter (PDF)", pkg.letter_pdf_url)) if url]
    children = [
        {"type": "image", "src": image, "alt": "Frame from your video", "aspect_ratio": "16:9"},
        {"type": "group", "direction": "row", "gap": 6, "children": [
            {"type": "badge", "label": f"{pkg.item_count} items", "variant": "info"},
            {"type": "badge", "label": f"{len(priced)} priced", "variant": "success"},
            *([{"type": "badge", "label": f"{unpriced} to price by hand", "variant": "warning"}] if unpriced else []),
        ]},
        {"type": "heading", "value": "Highest-value items", "level": 3},
        {"type": "list", "items": rows},
        {"type": "divider"},
        {"type": "text", "value": "Ready to send to your insurer. Nothing has been filed for you.", "style": "muted"},
    ]
    if downloads:
        children.append({"type": "group", "direction": "row", "gap": 8, "children": [
            {"type": "button", "label": label, "primary": i == 0,
             "action": {"selection": {"action": "link_opened"}, "redirect": url}}
            for i, (label, url) in enumerate(downloads)]})
    children.append({"type": "button", "label": "Other checks", "action": {"selection": {"action": "show_modes"}}})
    return {"root": {
        "type": "section",
        "title": f"Claim package · {_money(pkg.total_usd)}",
        "subtitle": "Today's replacement cost for each item, with the frame it was seen in",
        "children": children,
    }}
