"""Baby-proofing checks: everything a toddler can reach (below 0.9 m) and what can tip over."""
from agents.specialists.geometry import pin, split_budget, TIP_OVER_TYPES, evidence_for, floor_height, inches, is_covered
from shared.models import Finding, Measurement, Overlay, ProductQuery, Profile, Space

REACH_M = 0.9               # toddler reach height
HEAD_HEIGHT = (0.4, 0.9)    # corners in this band hit a toddler's head when they fall
TIP_OVER_MIN_HEIGHT = 0.75  # furniture this tall can fall on a child if it isn't anchored


def _count(items: list, noun: str) -> str:
    return f"{len(items)} {noun}{'s' if len(items) > 1 else ''}"


def _names(items: list, rooms: dict[str, str]) -> str:
    """'dining table (dining room), desk (office) and 2 more'."""
    labels = [f"{o.label.lower()} ({rooms.get(o.room_id, o.room_id).lower()})" for o in items[:3]]
    return ", ".join(labels) + (f" and {len(items) - 3} more" if len(items) > 3 else "")


def analyze(space: Space, profile: Profile) -> tuple[str, list[Finding], list[Overlay]]:
    findings: list[Finding] = []
    overlays: list[Overlay] = [Overlay(type="highlight", data={"zone": "reachable", "max_height_m": REACH_M})]
    rooms = {r.id: r.name for r in space.rooms}

    def add(f: Finding, pin_at: list[float], each: list | None = None, label: str = ""):
        findings.append(f)
        if not each:
            pin(overlays, f, pin_at)
        for o in each or []:  # a grouped finding still marks every object in the 3D view
            pin(overlays, f.copy(update={"title": label, "object_ids": [o.id]}), o.position)

    # Sharp corners and floor plants share one fix each, so each is one finding for the whole
    # home rather than one per object.
    corners: list = []
    plants: list = []
    outlets: list = []
    stairs: list = []

    for o in space.objects:
        floor_h = floor_height(o)
        top = floor_h + o.size[1]
        where = rooms.get(o.room_id, o.room_id).lower()
        if o.type == "outlet" and not is_covered(o) and floor_h < REACH_M:
            outlets.append(o)
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
            stairs.append(o)
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
            corners.append(o)
        elif o.type == "cord" and floor_h < REACH_M:
            add(Finding(
                id=f"baby_{o.id}", kind="hazard", severity=3, title=f"{o.label.capitalize()} within reach",
                object_ids=[o.id],
                fix_summary="Hide it under a cord cover or behind furniture",
                product_query=ProductQuery(query="floor cord cover raceway 6 ft"),
                evidence=evidence_for(o, "Cord on the floor"),
            ), o.position)
        elif o.type == "plant" and floor_h < REACH_M:
            plants.append(o)

    if stairs:
        # One finding even when the stairs come as a flight per floor: a gate at the top and the bottom,
        # sized to the measured stair width.
        width = inches(max(min(o.size[0], o.size[2]) for o in stairs))
        add(Finding(
            id=f"baby_{stairs[0].id}", kind="hazard", severity=5, title="Stairs without a safety gate",
            object_ids=[o.id for o in stairs],
            measurements=[Measurement(name="stair_width", value=width, unit="in")],
            fix_summary="Fit hardware-mounted gates at the top and bottom of the stairs",
            product_query=ProductQuery(query=f"hardware mounted baby gate for stairs fits {width} in opening", quantity=2),
            evidence=evidence_for(stairs[0], "No gate seen at the stairs"),
        ), stairs[0].position, each=stairs if len(stairs) > 1 else None, label="Stairs without a safety gate")
    if outlets:
        pack = next(n for n in (6, 12, 24, 36) if n >= len(outlets) or n == 36)
        add(Finding(
            id="baby_outlets", kind="hazard", severity=4,
            title=f"{_count(outlets, 'uncovered outlet')} within reach",
            object_ids=[o.id for o in outlets],
            measurements=[Measurement(name="lowest_outlet", value=inches(min(floor_height(o) for o in outlets)), unit="in")],
            fix_summary=f"Fit sliding outlet covers ({', '.join(sorted({rooms.get(o.room_id, o.room_id).lower() for o in outlets}))})",
            product_query=ProductQuery(query=f"sliding outlet covers child safety {pack} pack"),
            evidence=evidence_for(outlets[0], "Outlets within a toddler's reach"),
        ), outlets[0].position, each=outlets if len(outlets) > 1 else None, label="Uncovered outlet")
    if corners:
        low = min(corners, key=lambda o: floor_height(o) + o.size[1])
        add(Finding(
            id="baby_corners", kind="hazard", severity=3,
            title=f"Sharp corners on {_count(corners, 'piece')} of furniture",
            object_ids=[o.id for o in corners],
            measurements=[Measurement(name="lowest_corner", value=inches(floor_height(low) + low.size[1]), unit="in")],
            fix_summary=f"Add soft corner guards to the {_names(corners, rooms)}",
            product_query=ProductQuery(query="clear silicone corner guards 8 pack", quantity=-(-len(corners) * 4 // 8)),
            evidence=evidence_for(corners[0], "Corners at toddler head height"),
        ), corners[0].position, each=corners, label="Sharp corners")
    if plants:
        add(Finding(
            id="baby_plants", kind="hazard", severity=2,
            title=f"{_count(plants, 'floor plant')} within reach",
            object_ids=[o.id for o in plants],
            fix_summary=f"Move them up out of reach ({', '.join(sorted({rooms.get(o.room_id, o.room_id).lower() for o in plants}))}); "
                        "some houseplants are toxic if chewed",
            evidence=evidence_for(plants[0], "Plant pot on the floor"),
        ), plants[0].position, each=plants, label="Floor plant")

    split_budget(findings, profile.budget_usd)
    overlays.append(Overlay(type="camera", data={"mode": "first_person", "eye_height_m": 0.75}))
    findings.sort(key=lambda f: -f.severity)
    age = f" for a {profile.child_age_months}-month-old" if profile.child_age_months else ""
    summary = f"Found {len(findings)} hazards within a toddler's reach{age}." if findings else "Nothing hazardous within reach."
    return summary, findings, overlays
