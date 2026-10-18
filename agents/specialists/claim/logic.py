"""Insurance claim inventory: every contents item, with evidence, ready for pricing.

Values come from the Product Finder (current replacement price) or the user; until then
each item is listed with value_usd=None rather than an invented number.
"""
from agents.specialists.geometry import evidence_for
from shared.models import Finding, Overlay, ProductQuery, Profile, Space

# Fixtures and building parts belong to the dwelling claim, not contents.
NOT_CONTENTS = {"outlet", "window", "light", "ceiling_light", "cord", "door", "toilet", "bathtub", "shower", "sink",
                "counter", "cabinet", "stairs", "handrail", "grab_bar", "fireplace"}
CONFIRM_BELOW = 0.6


def analyze(space: Space, profile: Profile) -> tuple[str, list[Finding], list[Overlay]]:
    rooms = {r.id: r.name for r in space.rooms}
    findings: list[Finding] = []
    overlays: list[Overlay] = []
    for o in space.objects:
        if o.type in NOT_CONTENTS:
            continue
        brand = o.attributes.get("brand_guess") or ""
        guess = o.attributes.get("model_guess") or (f"{brand} {o.label}".strip() if brand.lower() not in o.label.lower() else o.label)
        findings.append(Finding(
            id=f"claim_{o.id}", kind="item", title=o.label,
            object_ids=[o.id],
            fix_summary=f"{rooms.get(o.room_id, o.room_id)} · priced as: {guess}",
            product_query=ProductQuery(query=f"{guess} replacement price"),
            value_basis="estimate",
            evidence=evidence_for(o, f"Seen in the {rooms.get(o.room_id, o.room_id).lower()}"),
        ))
        overlays.append(Overlay(type="tag", data={"object_id": o.id, "label": o.label,
                                                  "needs_confirm": o.confidence < CONFIRM_BELOW}))
    overlays.append(Overlay(type="camera", data={"mode": "flythrough"}))
    basis = (profile.policy_type or "unknown").replace("_", " ")
    summary = f"Listed {len(findings)} items across {len(rooms)} rooms for a {basis} claim. Prices come next."
    return summary, findings, overlays
