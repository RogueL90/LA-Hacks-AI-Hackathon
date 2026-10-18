"""Baby-proofing checks: everything a toddler can reach (below 0.9 m) and what can tip over."""
from agents.specialists.geometry import inches
from shared.models import Evidence, Finding, Measurement, Overlay, ProductQuery, Profile, Space

REACH_M = 0.9               # toddler reach height
HEAD_HEIGHT = (0.4, 0.9)    # corners in this band hit a toddler's head when they fall
TIP_OVER_TYPES = {"bookshelf", "dresser", "tv", "tv_stand", "wardrobe"}


def analyze(space: Space, profile: Profile) -> tuple[str, list[Finding], list[Overlay]]:
    findings: list[Finding] = []
    overlays: list[Overlay] = [Overlay(type="highlight", data={"zone": "reachable", "max_height_m": REACH_M})]
    rooms = {r.id: r.name for r in space.rooms}

    def add(f: Finding, pin_at: list[float]):
        findings.append(f)
        overlays.append(Overlay(type="pin", data={"finding_id": f.id, "position": pin_at, "severity": f.severity}))

    for o in space.objects:
        floor_h = o.attributes.get("height_from_floor", 0.0)
        top = floor_h + o.size[1]
        where = rooms.get(o.room_id, o.room_id)
        if o.type == "outlet" and not o.attributes.get("covered", False) and floor_h < REACH_M:
            add(Finding(
                id=f"baby_{o.id}", kind="hazard", severity=4, title=f"Uncovered outlet in the {where.lower()}",
                object_ids=[o.id],
                measurements=[Measurement(name="height_from_floor", value=inches(floor_h), unit="in")],
                fix_summary="Fit sliding outlet covers or plug covers",
                product_query=ProductQuery(query="sliding outlet covers child safety", quantity=2),
                evidence=[Evidence(note="Outlet within a toddler's reach")],
            ), o.position)
        elif o.type in TIP_OVER_TYPES and not o.attributes.get("anchored", True):
            add(Finding(
                id=f"baby_{o.id}", kind="hazard", severity=5, title=f"{o.label} can tip over",
                object_ids=[o.id],
                measurements=[Measurement(name="height", value=inches(top), unit="in")],
                fix_summary="Anchor it to the wall with an anti-tip kit (CPSC Anchor It!)",
                product_query=ProductQuery(
                    query="TV anti-tip safety strap" if o.type == "tv" else "furniture anti-tip wall anchor kit"),
                evidence=[Evidence(note="No wall anchor seen")],
            ), o.position)
        elif o.attributes.get("sharp_corners") and HEAD_HEIGHT[0] <= top <= HEAD_HEIGHT[1]:
            add(Finding(
                id=f"baby_{o.id}", kind="hazard", severity=3, title=f"Sharp corners on the {o.label.lower()}",
                object_ids=[o.id],
                measurements=[Measurement(name="corner_height", value=inches(top), unit="in")],
                fix_summary="Add soft corner guards",
                product_query=ProductQuery(query="clear corner guards for glass table", quantity=1),
                evidence=[Evidence(note="Corner at toddler head height")],
            ), o.position)
        elif o.type == "cord" and floor_h < REACH_M:
            add(Finding(
                id=f"baby_{o.id}", kind="hazard", severity=3, title=f"{o.label} within reach",
                object_ids=[o.id],
                fix_summary="Hide it under a cord cover or behind furniture",
                product_query=ProductQuery(query="floor cord cover raceway 6 ft"),
                evidence=[Evidence(note="Cord on the floor")],
            ), o.position)
        elif o.type == "plant" and floor_h < REACH_M:
            add(Finding(
                id=f"baby_{o.id}", kind="hazard", severity=2, title="Floor plant within reach",
                object_ids=[o.id],
                fix_summary="Move it up out of reach; some houseplants are toxic if chewed",
                evidence=[Evidence(note="Plant pot on the floor")],
            ), o.position)

    overlays.append(Overlay(type="camera", data={"mode": "first_person", "eye_height_m": 0.75}))
    findings.sort(key=lambda f: -f.severity)
    age = f" for a {profile.child_age_months}-month-old" if profile.child_age_months else ""
    summary = f"Found {len(findings)} hazards within a toddler's reach{age}." if findings else "Nothing hazardous within reach."
    return summary, findings, overlays
