"""Insurance claim inventory: every contents item, with evidence, ready for pricing.

Values come from the Product Finder (current replacement price) or the user; until then
each item is listed with value_usd=None rather than an invented number.
"""
from agents.specialists.geometry import M_TO_IN, evidence_for, pin
from shared.models import Finding, Overlay, ProductQuery, Profile, Space

# Fixtures and building parts belong to the dwelling claim, not contents.
NOT_CONTENTS = {"outlet", "window", "light", "ceiling_light", "cord", "door", "toilet", "bathtub", "shower", "sink",
                "counter", "cabinet", "stairs", "handrail", "grab_bar", "fireplace",
                # fixtures in the extractor's 96-type catalog
                "vanity", "kitchen_island", "range_hood", "light_switch", "smoke_detector", "thermostat",
                "towel_rack", "dishwasher", "built_in", "radiator", "ceiling_fan"}
CONFIRM_BELOW = 0.6


def analyze(space: Space, profile: Profile) -> tuple[str, list[Finding], list[Overlay]]:
    rooms = {r.id: r.name for r in space.rooms}
    findings: list[Finding] = []
    overlays: list[Overlay] = []
    listed = []
    for o in space.objects:
        if o.type in NOT_CONTENTS:
            continue
        brand = o.attributes.get("brand_guess") or ""
        model = o.attributes.get("model_guess") or ""
        label_words = {w for w in o.label.lower().replace("-", " ").split() if len(w) >= 2}
        if model and not label_words & set(model.lower().replace("-", " ").split()):
            model = f"{model} {o.label}"  # "Whirlpool" alone prices the washer and the dryer the same
        guess = model or (f"{brand} {o.label}".strip() if brand.lower() not in o.label.lower() else o.label)
        if o.type == "tv" and not o.attributes.get("model_guess"):
            # "wall mounted TV" finds TV mounts; price the set itself by its measured size (16:9 width -> diagonal).
            guess = f"{brand} {round(o.size[0] * M_TO_IN / 0.87)} inch TV".strip()
        f = Finding(
            id=f"claim_{o.id}", kind="item", title=o.label,
            object_ids=[o.id],
            fix_summary=f"{rooms.get(o.room_id, o.room_id)} · priced as: {guess}",
            # room/brand/model ride along for the Insurance Claim Filer's spreadsheet (search ignores them).
            product_query=ProductQuery(query=f"{guess} replacement price", constraints={
                k: v for k, v in (("room", rooms.get(o.room_id, o.room_id)), ("brand", brand),
                                  ("model", o.attributes.get("model_guess"))) if v}),
            value_basis="estimate",
            evidence=evidence_for(o, f"Seen in the {rooms.get(o.room_id, o.room_id).lower()}"),
        )
        findings.append(f)
        listed.append(o)
        if o.confidence < CONFIRM_BELOW:  # only items the user should check get their own pin
            pin(overlays, f.copy(update={"title": f"Confirm: {o.label}"}), o.position, badge="Confirm", severity=3)
        overlays.append(Overlay(type="tag", data={"object_id": o.id, "label": o.label,
                                                  "needs_confirm": o.confidence < CONFIRM_BELOW}))
    # One pin per room with its item count, on the room's biggest item that needs no checking.
    by_room: dict[str, list] = {}
    for o in listed:
        by_room.setdefault(o.room_id, []).append(o)
    for room_id, items in by_room.items():
        anchor = max(items, key=lambda o: (o.confidence >= CONFIRM_BELOW, o.size[0] * o.size[1] * o.size[2]))
        overlays.append(Overlay(type="pin", data={
            "finding_id": f"claim_room_{room_id}", "object_id": anchor.id, "position": anchor.position,
            "severity": 1, "badge": "Room", "title": f"{rooms.get(room_id, room_id).capitalize()} · {len(items)} item{'s' if len(items) > 1 else ''}",
        }))
    overlays.append(Overlay(type="camera", data={"mode": "flythrough"}))
    basis = f" for a {profile.policy_type.replace('_', ' ')} claim" if profile.policy_type else ""
    summary = f"Listed {len(findings)} items across {len(rooms)} rooms{basis}. Prices come next."
    return summary, findings, overlays
