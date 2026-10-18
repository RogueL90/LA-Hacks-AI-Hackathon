"""Space transformer: measure a room and plan what stays, what goes and what to buy for its new use.

Checkpoint A: deterministic measurements plus a fixed item list per goal. Checkpoint B
replaces the item list with a Claude-generated plan sized to the measured gaps.
"""
from agents.specialists.geometry import bounds, footprint, inches, is_movable
from shared.models import Finding, Measurement, Overlay, ProductQuery, Profile, Space

WALKWAY_M = 0.9
WALL_TOUCH_M = 0.35   # an object this close to a wall uses that wall

# Items each goal needs: (title, query, max width in m or None)
# Object types that already satisfy an item, so an existing desk isn't bought twice.
SATISFIED_BY = {"Desk": {"desk"}, "Ergonomic office chair": {"chair"}, "Desk lamp": {"lamp_table"},
                "Crib": {"crib"}, "Changing table": {"dresser"}, "Sleeper sofa": {"sofa", "bed"},
                "Side table": {"side_table", "nightstand"}}

GOAL_ITEMS = {
    "office": [
        ("Desk", "writing desk", 1.4),
        ("Ergonomic office chair", "ergonomic office chair lumbar support", None),
        ("Desk lamp", "LED desk lamp dimmable", None),
        ("Cable management tray", "under desk cable management tray", None),
    ],
    "nursery": [
        ("Crib", "convertible crib", 1.4),
        ("Changing table", "changing table dresser", 1.0),
        ("Blackout curtains", "blackout curtains nursery", None),
    ],
    "gym": [
        ("Exercise mat", "large exercise mat 6x4 ft", 1.9),
        ("Adjustable dumbbells", "adjustable dumbbells pair", None),
        ("Wall mirror", "full length wall mirror", 0.8),
    ],
    "guest": [
        ("Sleeper sofa", "sleeper sofa queen", 2.1),
        ("Side table", "small side table", 0.5),
        ("Luggage rack", "folding luggage rack", 0.7),
    ],
}


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
    present = {o.type for o in in_room}
    wanted = GOAL_ITEMS[key]
    needed_types = set().union(*(SATISFIED_BY.get(title, set()) for title, _, _ in wanted))
    for o in in_room:
        if o.type in needed_types:
            findings.append(Finding(
                id=f"transform_keep_{o.id}", kind="suggestion", title=f"Keep the {o.label.lower()}",
                object_ids=[o.id], fix_summary="Already right for the new use",
            ))
    for o in in_room:
        if o.id not in keep and o.type not in needed_types and is_movable(o):
            findings.append(Finding(
                id=f"transform_move_{o.id}", kind="suggestion", title=f"Move the {o.label.lower()} out",
                object_ids=[o.id],
                fix_summary=f"Frees {inches(o.size[0])} in of floor for the new layout",
            ))
            overlays.append(Overlay(type="ghost_object", data={"object_id": o.id, "action": "remove"}))

    for i, (title, query, max_w) in enumerate(wanted):
        if SATISFIED_BY.get(title, set()) & present:
            continue  # the room already has one
        constraints = {}
        if max_w is not None:
            fit_w = min(max_w, best["free"] - WALKWAY_M / 3)
            constraints["max_width_in"] = inches(fit_w)
            query = f"{query} under {inches(fit_w)} in wide"
        if profile.style:
            query = f"{profile.style} {query}"
        findings.append(Finding(
            id=f"transform_item_{i}", kind="suggestion", title=f"Add: {title}",
            fix_summary=(f"Must be at most {constraints['max_width_in']} in wide to fit"
                         if constraints else "Fits anywhere in the plan"),
            product_query=ProductQuery(query=query, max_price_usd=profile.budget_usd, constraints=constraints),
        ))
        overlays.append(Overlay(type="ghost_object", data={"label": title, "wall": best["name"], "action": "add"}))

    overlays.append(Overlay(type="camera", data={"mode": "orbit", "room_id": room_id}))
    summary = (f"Plan to turn the {room.name.lower()} into a {goal}: "
               f"{sum(1 for f in findings if f.id.startswith('transform_item'))} items to add, "
               f"{sum(1 for f in findings if f.id.startswith('transform_move'))} to move out.")
    return summary, findings, overlays
