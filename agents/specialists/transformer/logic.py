"""Space transformer: measure a room and plan what stays, what goes and what to buy for its new use.

Checkpoint A: deterministic measurements plus a fixed item list per goal. Checkpoint B
replaces the item list with a Claude-generated plan sized to the measured gaps.
"""
from agents.specialists.geometry import bounds, floor_height, footprint, inches, is_movable, pin
from shared.models import Finding, Measurement, Overlay, ProductQuery, Profile, Space

WALKWAY_M = 0.9
MIN_FIT_M = 0.5  # less free wall than this and nothing wall-sized fits until something moves out
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


def item(title, query, max_w=None, weight=1.0, styled=False, qty=1, floor=None, rank=2):
    """One thing to buy. weight = its typical share of the cost (a desk ~3, a mouse ~0.3), used to
    split the budget; floor = the least a decent one costs (a 27 in monitor won't be $36);
    styled = the user's style applies (furniture and decor, not chairs or tech);
    rank = how much it matters (3 the essentials, 2 what the user asked for, 1 nice-to-haves)."""
    return {"title": title, "query": query, "max_w": max_w, "weight": weight, "styled": styled, "qty": qty,
            "floor": floor if floor is not None else round(weight * 25), "rank": rank}


GOAL_ITEMS = {
    "office": [
        item("Desk", "writing desk", 1.4, 3, styled=True, floor=60, rank=3),
        item("Ergonomic office chair", "ergonomic office chair with lumbar support", weight=3, floor=60, rank=3),
        item("Desk lamp", "LED desk lamp dimmable", weight=0.6, styled=True, floor=15, rank=1),
        item("Cable management tray", "under desk cable management tray", weight=0.4, floor=12, rank=1),
    ],
    "nursery": [
        item("Crib", "convertible crib", 1.4, 3, styled=True, floor=120, rank=3),
        item("Changing table", "changing table dresser", 1.0, 2, styled=True, floor=80, rank=3),
        item("Blackout curtains", "blackout curtains nursery", weight=0.6, styled=True, floor=20, rank=1),
    ],
    "gym": [
        item("Exercise mat", "large exercise mat 6x4 ft", 1.9, 0.6, floor=25, rank=3),
        item("Adjustable dumbbells", "adjustable dumbbells pair", weight=2, floor=60, rank=3),
        item("Wall mirror", "full length wall mirror", 0.8, 1, styled=True, floor=40, rank=1),
    ],
    "guest": [
        item("Sleeper sofa", "sleeper sofa queen", 2.1, 5, styled=True, floor=300, rank=3),
        item("Side table", "small side table", 0.5, 0.8, styled=True, floor=30, rank=1),
        item("Luggage rack", "folding luggage rack", 0.7, 0.5, floor=25, rank=1),
    ],
}

# Things people ask for in "Anything it must have?" -> extra items (pattern, item). A count in
# front ("two monitors", "2 monitors", "dual monitors") sets the quantity.
REQUESTED = [
    (r"standing desk|sit[- ]stand", item("Standing desk", "electric standing desk", 1.4, 4, styled=True, floor=150, rank=2)),
    (r"monitor arm", item("Dual monitor arm", "dual monitor arm desk mount", weight=0.8, floor=30, rank=2)),
    (r"monitors?|screens?|displays?", item("Monitor", "27 inch IPS monitor", weight=2, floor=90, rank=2)),
    (r"keyboard.{0,20}mouse|mouse.{0,20}keyboard", item("Keyboard and mouse", "wireless keyboard and mouse combo", weight=0.8, floor=20, rank=2)),
    (r"keyboard", item("Keyboard", "wireless keyboard", weight=0.5, floor=15, rank=2)),
    (r"\bmouse\b|\bmice\b", item("Mouse", "wireless ergonomic mouse", weight=0.3, floor=10, rank=2)),
    (r"webcam|camera|video calls?", item("Webcam", "1080p webcam with microphone", weight=0.6, floor=25, rank=2)),
    (r"headphones?|headset", item("Headset", "noise cancelling headset with microphone", weight=1, floor=30, rank=2)),
    (r"printer", item("Printer", "compact wireless printer", weight=1.5, floor=70, rank=2)),
    (r"dock(ing station)?", item("Docking station", "USB-C docking station dual monitor", weight=1, floor=40, rank=2)),
    (r"book ?shel(f|ves)|shelving", item("Bookshelf", "bookshelf", 0.9, 1.5, styled=True, floor=50, rank=2)),
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


# Furniture that takes up floor space. Plants, curtains, decor and things on a desk stay put.
FLOOR_FURNITURE = {"chair", "armchair", "ottoman", "pouf", "stool", "bench", "side_table", "coffee_table",
                   "console_table", "sofa", "loveseat", "bookshelf", "dresser", "tv_stand", "dining_table", "bed",
                   "laundry_basket", "box", "clutter", "rocking_chair", "bean_bag", "treadmill", "exercise_bike"}


def takes_floor_space(o) -> bool:
    return o.type in FLOOR_FURNITURE and is_movable(o) and floor_height(o) < 0.2


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
        if o.id not in keep and o not in needed and takes_floor_space(o):
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
        no_wall = False
        if w["max_w"] is not None:
            fit_w = min(w["max_w"], best["free"] - WALKWAY_M / 3)
            if fit_w >= MIN_FIT_M:
                constraints["width_in"] = inches(fit_w)  # Product Finder reads numbers as maximums
                query = f"{query} under {inches(fit_w)} in wide"
            else:
                no_wall = True  # every wall is taken: clear one first, then any size that suits the room
        if profile.style and w["styled"]:
            query = f"{query}, {profile.style} style"
        # ...no more than a sensible ceiling for its kind (a big budget doesn't buy a $106 cable tray) and
        # no less than a decent one costs: with too small a budget the cart keeps what matters most and
        # says what didn't fit, instead of searching for a $36 monitor that doesn't exist.
        cap = round(min(max(profile.budget_usd * w["weight"] / total_weight * 1.3, w["floor"]),
                        w["weight"] * CEILING_PER_WEIGHT), 2) if profile.budget_usd else None
        size = (f"at most {constraints['width_in']} in wide to fit" if constraints else
                "no free wall is long enough yet: move something out first" if no_wall else "fits anywhere in the plan")
        price = (f", up to ${cap:,.0f} each" if w["qty"] > 1 else f", up to ${cap:,.0f}") if cap else ""
        findings.append(Finding(
            id=f"transform_item_{i}", kind="suggestion", severity=w["rank"] + 1,  # cart order: essentials first
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
