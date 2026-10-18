"""Geometry and vocabulary helpers shared by the specialists (meters, floor plane = x/z).

Spaces come from two sources: the hand-made demo home and Aditya's extractor, which uses
its own room ids ("room_bedroom_2"), object types ("ceiling_light") and attribute names
("has_cover"). These helpers let the rules read both.
"""
from shared.models import Evidence, Finding, Overlay, Room, Space, SpaceObject

M_TO_IN = 39.37

LIGHT_TYPES = {"light", "ceiling_light", "lamp_floor", "lamp_table", "night_light"}
MOVABLE_TYPES = {"chair", "armchair", "stool", "ottoman", "pouf", "clutter", "side_table", "laundry_basket", "box"}
TIP_OVER_TYPES = {"bookshelf", "dresser", "tv", "tv_stand", "wardrobe"}  # cabinets are usually built in (vanities, kitchen)
ROOM_KINDS = [
    ("storage", ("closet", "pantry", "storage", "garage", "attic")),  # first: "bedroom closet" is storage
    ("bathroom", ("bath", "restroom", "toilet", "powder", "wc", "ensuite", "en_suite")),
    ("bedroom", ("bed", "nursery", "primary", "master", "guest")),
    ("hallway", ("hall", "corridor", "landing", "entry", "foyer")),
    ("kitchen", ("kitchen",)),
    ("living", ("living", "family", "lounge", "den")),
    ("dining", ("dining",)),
    ("laundry", ("laundry", "utility")),
    ("office", ("office", "study")),
    ("stairs", ("stair",)),
]


def inches(m: float) -> float:
    return round(m * M_TO_IN)


def footprint(obj: SpaceObject) -> tuple[float, float, float, float]:
    """Axis-aligned floor footprint (min_x, max_x, min_z, max_z), ignoring rotation."""
    x, _, z = obj.position
    w, _, d = obj.size
    return x - w / 2, x + w / 2, z - d / 2, z + d / 2


def bounds(room: Room) -> tuple[float, float, float, float]:
    xs = [p[0] for p in room.polygon]
    zs = [p[1] for p in room.polygon]
    return min(xs), max(xs), min(zs), max(zs)


def gap_x(a: SpaceObject, b: SpaceObject) -> float:
    """Clear floor distance between two objects along x (0 if they overlap)."""
    a0, a1, _, _ = footprint(a)
    b0, b1, _, _ = footprint(b)
    return max(0.0, max(b0 - a1, a0 - b1))


def room_kind(room: Room | None) -> str:
    """'bedroom', 'bathroom', 'hallway', ... from the room's name or id."""
    if room is None:
        return "other"
    text = f"{room.name} {room.id}".lower()
    for kind, words in ROOM_KINDS:
        if any(w in text for w in words):
            return kind
    return "other"


def kinds_by_room(space: Space) -> dict[str, str]:
    return {r.id: room_kind(r) for r in space.rooms}


def is_movable(obj: SpaceObject) -> bool:
    return bool(obj.attributes.get("is_movable")) or obj.type in MOVABLE_TYPES


def is_covered(obj: SpaceObject) -> bool:
    return bool(obj.attributes.get("covered", obj.attributes.get("has_cover", False)))


def floor_height(obj: SpaceObject) -> float:
    return float(obj.attributes.get("height_from_floor", 0.0) or 0.0)


def evidence_for(obj: SpaceObject, note: str) -> list[Evidence]:
    """The frames the object was seen in (from the extractor), plus our note."""
    seen = [Evidence(frame_url=e.frame_url, timestamp_s=e.timestamp_s, note=note) for e in obj.evidence[:1]]
    return seen or [Evidence(note=note)]


SEVERITY_LABELS = {5: "Critical", 4: "Serious", 3: "Moderate", 2: "Minor", 1: "Minor"}


def pin(overlays: list[Overlay], f: Finding, position: list[float] | None = None,
        badge: str | None = None, severity: int | None = None):
    """A viewer pin for a finding: the viewer draws it above `object_id` (Aditya's Pin overlay).

    `badge` ("Keep", "Move out", "Confirm") is for pins that aren't hazards; until the viewer
    shows it, the pin shows `severity` instead.
    """
    data = {"finding_id": f.id, "severity": severity or f.severity, "title": f.title}
    if badge:
        data["badge"] = badge
    # What the viewer shows when the pin is clicked: why it was flagged and what to do.
    why = [f"{m.name.replace('_', ' ').capitalize()}: {m.value:g} {m.unit}"
           + (f" (needs {m.required:g} {m.unit})" if m.required is not None else "") for m in f.measurements]
    why += [e.note for e in f.evidence if e.note]
    if why:
        data["why"] = why
    if f.fix_summary:
        data["fix"] = f.fix_summary
    if f.kind == "hazard":
        data["severity_label"] = SEVERITY_LABELS.get(data["severity"], "Moderate")
    if f.object_ids:
        data["object_id"] = f.object_ids[0]
    if position:
        data["position"] = position
    frame = next((e.frame_url for e in f.evidence if e.frame_url), None)
    if frame:
        data["frame_url"] = frame
    overlays.append(Overlay(type="pin", data=data))


# Typical cost weight of a fix's product (a handrail kit ~2, an outlet cover pack ~0.3), matched on its
# search words. Used to give each product search a share of the user's budget.
COST_WEIGHTS = [
    ("handrail", 2.0), ("gate", 2.0), ("raised toilet seat", 1.2), ("grab bar", 1.0), ("rug pad", 1.0),
    ("hinge", 0.6), ("night light", 0.6), ("anti-tip", 0.5), ("stove knob", 0.4), ("corner guard", 0.4),
    ("cord cover", 0.4), ("toilet seat lock", 0.3), ("outlet cover", 0.3),
]


def cost_weight(query: str) -> float:
    q = query.lower()
    return next((w for word, w in COST_WEIGHTS if word in q), 1.0)


def split_budget(findings: list[Finding], budget: float | None, ceiling_per_weight: float = 150) -> None:
    """Give each product search a price cap: its share of the budget by typical cost, no more than a
    sensible ceiling for its kind. Without a budget, searches stay uncapped."""
    shopping = [f for f in findings if f.product_query]
    if not budget or not shopping:
        return
    total = sum(cost_weight(f.product_query.query) * f.product_query.quantity for f in shopping) or 1
    for f in shopping:
        w = cost_weight(f.product_query.query)
        # 30% headroom over the share: the cart still keeps the total within the budget.
        f.product_query.max_price_usd = round(min(budget * w / total * 1.3, w * ceiling_per_weight), 2)
