"""Insurance claim inventory: every contents item, with evidence, ready for pricing.

Values come from the Product Finder (current replacement price) or the user; until then
each item is listed with value_usd=None rather than an invented number.
"""
from shared.models import Evidence, Finding, Overlay, ProductQuery, Profile, Space

NOT_CONTENTS = {"outlet", "window", "light", "cord", "door", "toilet", "bathtub"}  # fixtures and building parts
CONFIRM_BELOW = 0.6


def analyze(space: Space, profile: Profile) -> tuple[str, list[Finding], list[Overlay]]:
    rooms = {r.id: r.name for r in space.rooms}
    findings: list[Finding] = []
    overlays: list[Overlay] = []
    for o in space.objects:
        if o.type in NOT_CONTENTS:
            continue
        guess = o.attributes.get("model_guess") or o.label
        findings.append(Finding(
            id=f"claim_{o.id}", kind="item", title=o.label,
            object_ids=[o.id],
            fix_summary=f"{rooms.get(o.room_id, o.room_id)} · priced as: {guess}",
            product_query=ProductQuery(query=f"{guess} replacement price"),
            value_basis="estimate",
            evidence=o.evidence or [Evidence(note=f"Seen in the {rooms.get(o.room_id, o.room_id).lower()}")],
        ))
        overlays.append(Overlay(type="tag", data={"object_id": o.id, "label": o.label,
                                                  "needs_confirm": o.confidence < CONFIRM_BELOW}))
    overlays.append(Overlay(type="camera", data={"mode": "flythrough"}))
    basis = (profile.policy_type or "unknown").replace("_", " ")
    summary = f"Listed {len(findings)} items across {len(rooms)} rooms for a {basis} claim. Prices come next."
    return summary, findings, overlays
