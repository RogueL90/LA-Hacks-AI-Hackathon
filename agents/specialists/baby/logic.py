"""Baby-proofing checks: everything a toddler can reach (below 0.9 m) and what can tip over."""
from agents.specialists.geometry import TIP_OVER_TYPES, evidence_for, floor_height, inches, is_covered
from shared.models import Finding, Measurement, Overlay, ProductQuery, Profile, Space

REACH_M = 0.9               # toddler reach height
HEAD_HEIGHT = (0.4, 0.9)    # corners in this band hit a toddler's head when they fall
TIP_OVER_MIN_HEIGHT = 0.75  # furniture this tall can fall on a child if it isn't anchored


def analyze(space: Space, profile: Profile) -> tuple[str, list[Finding], list[Overlay]]:
    findings: list[Finding] = []
    overlays: list[Overlay] = [Overlay(type="highlight", data={"zone": "reachable", "max_height_m": REACH_M})]
    rooms = {r.id: r.name for r in space.rooms}

    def add(f: Finding, pin_at: list[float]):
        findings.append(f)
        overlays.append(Overlay(type="pin", data={"finding_id": f.id, "position": pin_at, "severity": f.severity}))

    for o in space.objects:
        floor_h = floor_height(o)
        top = floor_h + o.size[1]
        where = rooms.get(o.room_id, o.room_id).lower()
        if o.type == "outlet" and not is_covered(o) and floor_h < REACH_M:
            add(Finding(
                id=f"baby_{o.id}", kind="hazard", severity=4, title=f"Uncovered outlet in the {where}",
                object_ids=[o.id],
                measurements=[Measurement(name="height_from_floor", value=inches(floor_h), unit="in")],
                fix_summary="Fit sliding outlet covers or plug covers",
                product_query=ProductQuery(query="sliding outlet covers child safety", quantity=2),
                evidence=evidence_for(o, "Outlet within a toddler's reach"),
            ), o.position)
        elif (o.type in TIP_OVER_TYPES and o.attributes.get("anchored") is not True
              and floor_h < 0.2 and top >= TIP_OVER_MIN_HEIGHT):  # floor-standing only; wall cabinets can't tip
            add(Finding(
                id=f"baby_{o.id}", kind="hazard", severity=5, title=f"{o.label.capitalize()} could tip over",
                object_ids=[o.id],
                measurements=[Measurement(name="height", value=inches(top), unit="in")],
                fix_summary="Anchor it to the wall with an anti-tip kit (CPSC Anchor It!)",
                product_query=ProductQuery(
                    query="TV anti-tip safety strap" if o.type == "tv" else "furniture anti-tip wall anchor kit"),
                evidence=evidence_for(o, "No wall anchor seen"),
            ), o.position)
        elif o.type == "stairs":
            add(Finding(
                id=f"baby_{o.id}", kind="hazard", severity=5, title="Stairs without a safety gate",
                object_ids=[o.id],
                fix_summary="Fit hardware-mounted gates at the top and bottom of the stairs",
                product_query=ProductQuery(query="hardware mounted baby gate for top of stairs", quantity=2),
                evidence=evidence_for(o, "No gate seen at the stairs"),
            ), o.position)
        elif o.type == "stove":
            add(Finding(
                id=f"baby_{o.id}", kind="hazard", severity=4, title="Stove knobs within reach",
                object_ids=[o.id],
                fix_summary="Fit stove knob covers and an oven door lock",
                product_query=ProductQuery(query="stove knob covers and oven lock child safety"),
                evidence=evidence_for(o, "Front stove knobs are at toddler height"),
            ), o.position)
        elif o.type == "toilet":
            add(Finding(
                id=f"baby_{o.id}", kind="hazard", severity=3, title=f"Toilet in the {where}",
                object_ids=[o.id],
                fix_summary="Fit a toilet seat lock (drowning risk for toddlers)",
                product_query=ProductQuery(query="toilet seat lock child safety"),
                evidence=evidence_for(o, "Toilet lid within reach"),
            ), o.position)
        elif o.attributes.get("sharp_corners") and HEAD_HEIGHT[0] <= top <= HEAD_HEIGHT[1]:
            add(Finding(
                id=f"baby_{o.id}", kind="hazard", severity=3, title=f"Sharp corners on the {o.label.lower()}",
                object_ids=[o.id],
                measurements=[Measurement(name="corner_height", value=inches(top), unit="in")],
                fix_summary="Add soft corner guards",
                product_query=ProductQuery(query=f"clear corner guards for {o.label.lower()}", quantity=1),
                evidence=evidence_for(o, "Corner at toddler head height"),
            ), o.position)
        elif o.type == "cord" and floor_h < REACH_M:
            add(Finding(
                id=f"baby_{o.id}", kind="hazard", severity=3, title=f"{o.label.capitalize()} within reach",
                object_ids=[o.id],
                fix_summary="Hide it under a cord cover or behind furniture",
                product_query=ProductQuery(query="floor cord cover raceway 6 ft"),
                evidence=evidence_for(o, "Cord on the floor"),
            ), o.position)
        elif o.type == "plant" and floor_h < REACH_M:
            add(Finding(
                id=f"baby_{o.id}", kind="hazard", severity=2, title="Floor plant within reach",
                object_ids=[o.id],
                fix_summary="Move it up out of reach; some houseplants are toxic if chewed",
                evidence=evidence_for(o, "Plant pot on the floor"),
            ), o.position)

    overlays.append(Overlay(type="camera", data={"mode": "first_person", "eye_height_m": 0.75}))
    findings.sort(key=lambda f: -f.severity)
    age = f" for a {profile.child_age_months}-month-old" if profile.child_age_months else ""
    summary = f"Found {len(findings)} hazards within a toddler's reach{age}." if findings else "Nothing hazardous within reach."
    return summary, findings, overlays
