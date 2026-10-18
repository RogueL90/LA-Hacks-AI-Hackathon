"""Space transformer: measure a room and plan what stays, what goes and what to buy for its new use.

Checkpoint A: deterministic measurements plus a fixed item list per goal. Checkpoint B
replaces the item list with a Claude-generated plan sized to the measured gaps.
"""
from agents.specialists.geometry import bounds, footprint, inches, is_movable, pin
from shared.models import Finding, Measurement, Overlay, ProductQuery, Profile, Space

WALKWAY_M = 0.9
CEILING_PER_WEIGHT = 150  # USD per unit of item weight: chair (3) up to $450, cable tray (0.4) up to $60
WALL_TOUCH_M = 0.35   # an object this close to a wall uses that wall

# Object types that already satisfy an item, so an existing desk isn't bought twice.
SATISFIED_BY = {"Desk": {"desk"}, "Standing desk": {"desk"}, "Ergonomic office chair": {"office_chair"},
                "Desk lamp": {"lamp_table"}, "Monitor": {"monitor"}, "Crib": {"crib"}, "Changing table": {"dresser"},
                "Sleeper sofa": {"sofa", "bed"}, "Side table": {"side_table", "nightstand"}, "Bookshelf": {"bookshelf"}}


# A plain "chair" only counts as the office chair when its label says so (an armchair doesn't).
SATISFIED_BY_LABEL = {"Ergonomic office chair": ("chair", r"desk|office|task|ergonomic|gaming|swivel")}


def satisfies(title: str, obj) -> bool:
    """Does this existing object already cover the item (so it isn't bought twice)?"""
    import re

    if obj.type in SATISFIED_BY.get(title, set()):
        return True
    rule = SATISFIED_BY_LABEL.get(title)
    return bool(rule and obj.type == rule[0] and re.search(rule[1], obj.label, re.I))


def item(title, query, max_w=None, weight=1.0, styled=False, qty=1):
    """One thing to buy. weight = its typical share of the cost (a desk ~3, a mouse ~0.3), used to
    split the budget; styled = the user's style applies (furniture and decor, not chairs or tech)."""
    return {"title": title, "query": query, "max_w": max_w, "weight": weight, "styled": styled, "qty": qty}


GOAL_ITEMS = {
    "office": [
        item("Desk", "writing desk", 1.4, 3, styled=True),
        item("Ergonomic office chair", "ergonomic office chair with lumbar support", weight=3),
        item("Desk lamp", "LED desk lamp dimmable", weight=0.6, styled=True),
        item("Cable management tray", "under desk cable management tray", weight=0.4),
    ],
    "nursery": [
        item("Crib", "convertible crib", 1.4, 3, styled=True),
        item("Changing table", "changing table dresser", 1.0, 2, styled=True),
        item("Blackout curtains", "blackout curtains nursery", weight=0.6, styled=True),
    ],
    "gym": [
        item("Exercise mat", "large exercise mat 6x4 ft", 1.9, 0.6),
        item("Adjustable dumbbells", "adjustable dumbbells pair", weight=2),
        item("Wall mirror", "full length wall mirror", 0.8, 1, styled=True),
    ],
    "guest": [
        item("Sleeper sofa", "sleeper sofa queen", 2.1, 5, styled=True),
        item("Side table", "small side table", 0.5, 0.8, styled=True),
        item("Luggage rack", "folding luggage rack", 0.7, 0.5),
    ],
}

# Things people ask for in "Anything it must have?" -> extra items (pattern, item). A count in
# front ("two monitors", "2 monitors", "dual monitors") sets the quantity.
REQUESTED = [
    (r"standing desk|sit[- ]stand", item("Standing desk", "electric standing desk", 1.4, 4, styled=True)),
    (r"monitor arm", item("Dual monitor arm", "dual monitor arm desk mount", weight=0.8)),
    (r"monitors?|screens?|displays?", item("Monitor", "27 inch IPS monitor", weight=2)),
    (r"keyboard.{0,20}mouse|mouse.{0,20}keyboard", item("Keyboard and mouse", "wireless keyboard and mouse combo", weight=0.8)),
    (r"keyboard", item("Keyboard", "wireless keyboard", weight=0.5)),
    (r"\bmouse\b|\bmice\b", item("Mouse", "wireless ergonomic mouse", weight=0.3)),
    (r"webcam|camera|video calls?", item("Webcam", "1080p webcam with microphone", weight=0.6)),
    (r"headphones?|headset", item("Headset", "noise cancelling headset with microphone", weight=1)),
    (r"printer", item("Printer", "compact wireless printer", weight=1.5)),
    (r"dock(ing station)?", item("Docking station", "USB-C docking station dual monitor", weight=1)),
    (r"book ?shel(f|ves)|shelving", item("Bookshelf", "bookshelf", 0.9, 1.5, styled=True)),
    (r"whiteboard", item("Whiteboard", "wall whiteboard 36 x 24 in", weight=0.6)),
    (r"ring light|lighting for calls", item("Ring light", "desk ring light for video calls", weight=0.4)),
    (r"footrest", item("Footrest", "under desk footrest", weight=0.3)),
    (r"\brug\b", item("Rug", "area rug 5x7", weight=1, styled=True)),
]
COUNTS = {"one": 1, "single": 1, "two": 2, "dual": 2, "pair of": 2, "double": 2, "three": 3, "triple": 3, "four": 4}


def requested_items(text: str | None) -> list[dict]:
    """Extra items named in the requirements, with quantities."""
    import re

    found, taken = [], text.lower() if text else ""
    for pattern, it in REQUESTED:
        m = re.search(rf"(?:(\d+|{'|'.join(COUNTS)})\s+)?(?:{pattern})", taken)
        if not m:
            continue
        qty = int(m.group(1)) if m.group(1) and m.group(1).isdigit() else COUNTS.get(m.group(1) or "", 1)
        found.append({**it, "qty": max(1, min(qty, 6))})
        taken = taken[:m.start()] + " " * (m.end() - m.start()) + taken[m.end():]  # don't match it twice
    return found


def _plural(label: str) -> str:
    """"black bar stool" -> "black bar stools"."""
    return label + ("es" if label.endswith(("s", "sh", "ch", "x")) else "s")


def _goal_key(goal: str) -> str:
    g = goal.lower()
    for key in GOAL_ITEMS:
        if key in g:
            return key
    return "office"


def _free_walls(space: Space, room_id: str) -> list[dict]:
    """Free length along each wall of a rectangular room, after objects pushed against it."""
    room = next(r for r in space.rooms if r.id == room_id)
    x0, x1, z0, z1 = bounds(room)
    walls = {
        "back": {"length": x1 - x0, "axis": "x", "at": z0},
        "front": {"length": x1 - x0, "axis": "x", "at": z1},
        "left": {"length": z1 - z0, "axis": "z", "at": x0},
        "right": {"length": z1 - z0, "axis": "z", "at": x1},
    }
    for name, wall in walls.items():
        used = 0.0
        for o in space.objects:
            if o.room_id != room_id or o.type in {"outlet", "light"}:
                continue
            ox0, ox1, oz0, oz1 = footprint(o)
            near = (abs(oz0 - wall["at"]) < WALL_TOUCH_M or abs(oz1 - wall["at"]) < WALL_TOUCH_M) if wall["axis"] == "x" \
                else (abs(ox0 - wall["at"]) < WALL_TOUCH_M or abs(ox1 - wall["at"]) < WALL_TOUCH_M)
            if near:
                used += (ox1 - ox0) if wall["axis"] == "x" else (oz1 - oz0)
        wall["free"] = max(0.0, wall["length"] - used)
        wall["name"] = name
        wall["window"] = any(o.type == "window" and o.room_id == room_id and
                             abs((o.position[2] if wall["axis"] == "x" else o.position[0]) - wall["at"]) < WALL_TOUCH_M
                             for o in space.objects)
    return sorted(walls.values(), key=lambda w: -w["free"])


def analyze(space: Space, profile: Profile) -> tuple[str, list[Finding], list[Overlay]]:
    rooms = {r.id: r for r in space.rooms}
    largest = max(space.rooms, key=lambda r: (bounds(r)[1] - bounds(r)[0]) * (bounds(r)[3] - bounds(r)[2]))
    room = rooms.get(profile.room_id or "", largest)
    room_id = room.id
    goal = profile.goal or "home office"
    key = _goal_key(goal)
    walls = _free_walls(space, room_id)
    best = walls[0]
    findings: list[Finding] = []
    overlays: list[Overlay] = []

    findings.append(Finding(
        id="transform_wall", kind="suggestion",
        title=f"Use the {best['name']} wall{' by the window' if best['window'] else ''}",
        measurements=[Measurement(name="free_wall_length", value=inches(best["free"]), unit="in")],
        fix_summary=f"The longest free wall in the {room.name.lower()} has {inches(best['free'])} in clear",
    ))

    keep = set(profile.keep_object_ids)
    in_room = [o for o in space.objects if o.room_id == room_id]
    wanted = list(GOAL_ITEMS[key])
    for extra in requested_items(profile.requirements):
        if extra["title"] == "Standing desk":
            wanted = [w for w in wanted if w["title"] != "Desk"]  # a standing desk replaces the desk
        if extra["title"] not in {w["title"] for w in wanted}:
            wanted.append(extra)
    needed = [o for o in in_room if any(satisfies(w["title"], o) for w in wanted)]
    for o in needed:
        f = Finding(
            id=f"transform_keep_{o.id}", kind="suggestion", title=f"Keep the {o.label.lower()}",
            object_ids=[o.id], fix_summary="Already right for the new use",
        )
        findings.append(f)
        pin(overlays, f, o.position, badge="Keep", severity=1)
    # Same-label objects (two bar stools) are one "move out" line with every object pinned.
    moving: dict[str, list] = {}
    for o in in_room:
        if o.id not in keep and o not in needed and is_movable(o):
            moving.setdefault(o.label.lower(), []).append(o)
    for label, objs in moving.items():
        width = sum(inches(o.size[0]) for o in objs)
        f = Finding(
            id=f"transform_move_{objs[0].id}", kind="suggestion",
            title=f"Move the {label} out" if len(objs) == 1 else f"Move the {len(objs)} {_plural(label)} out",
            object_ids=[o.id for o in objs],
            fix_summary=f"Frees {width} in of floor for the new layout",
        )
        findings.append(f)
        for o in objs:
            pin(overlays, f.copy(update={"object_ids": [o.id]}), o.position, badge="Move out", severity=3)
            overlays.append(Overlay(type="ghost_object", data={"object_id": o.id, "action": "remove"}))

    to_buy = [w for w in wanted if not any(satisfies(w["title"], o) for o in in_room)]  # skip what the room has
    # Split the budget by typical cost, so one item can't use it all (a $469 chair, nothing else).
    total_weight = sum(w["weight"] * w["qty"] for w in to_buy) or 1
    for i, w in enumerate(to_buy):
        title, query, constraints = w["title"], w["query"], {}
        if w["max_w"] is not None:
            fit_w = min(w["max_w"], best["free"] - WALKWAY_M / 3)
            constraints["width_in"] = inches(fit_w)  # Product Finder reads numbers as maximums
            query = f"{query} under {inches(fit_w)} in wide"
        if profile.style and w["styled"]:
            query = f"{query}, {profile.style} style"
        # ...and no more than a sensible ceiling for its kind, so a big budget doesn't buy a $106 cable tray.
        cap = round(min(profile.budget_usd * w["weight"] / total_weight, w["weight"] * CEILING_PER_WEIGHT), 2) \
            if profile.budget_usd else None
        size = f"at most {constraints['width_in']} in wide to fit" if constraints else "fits anywhere in the plan"
        price = (f", up to ${cap:,.0f} each" if w["qty"] > 1 else f", up to ${cap:,.0f}") if cap else ""
        findings.append(Finding(
            id=f"transform_item_{i}", kind="suggestion",
            title=f"Add: {title}" + (f" ×{w['qty']}" if w["qty"] > 1 else ""),
            fix_summary=f"{size[0].upper()}{size[1:]}{price}",
            product_query=ProductQuery(query=query, max_price_usd=cap, constraints=constraints, quantity=w["qty"]),
        ))
        overlays.append(Overlay(type="ghost_object", data={"label": title, "wall": best["name"], "action": "add"}))

    overlays.append(Overlay(type="camera", data={"mode": "orbit", "room_id": room_id}))
    summary = (f"Plan to turn the {room.name.lower()} into a {goal}: "
               f"{sum(1 for f in findings if f.id.startswith('transform_item'))} items to add, "
               f"{sum(1 for f in findings if f.id.startswith('transform_move'))} to move out."
               + (f" Your ${profile.budget_usd:,.0f} budget is split across them by typical cost." if profile.budget_usd and to_buy else ""))
    return summary, findings, overlays
