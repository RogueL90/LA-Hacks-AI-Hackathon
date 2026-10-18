"""Elder safety checks: deterministic measurements on the Space (rules: CDC STEADI, ADA widths).

Works on the demo home and on extracted homes: rooms are matched by kind (bedroom,
bathroom, hallway...), and a check whose evidence can't be seen says "seen", not "is".
"""
from agents.specialists.geometry import (
    pin,
    LIGHT_TYPES,
    evidence_for,
    floor_height,
    footprint,
    gap_x,
    inches,
    kinds_by_room,
    is_movable,
)
from shared.models import Evidence, Finding, Measurement, Overlay, ProductQuery, Profile, Space

# Clear width each mobility aid needs, in meters. Wheelchair: ADA 32 in door clear width and
# 36 in continuous path. Walker: a 26 in frame plus hands. A cane or no aid fits any normal door.
DOOR_CLEAR = {"wheelchair": 0.81, "walker": 0.76, "rollator": 0.76}
PATH_CLEAR = {"wheelchair": 0.91, "walker": 0.81, "rollator": 0.81}
DEFAULT_DOOR, DEFAULT_PATH = 0.61, 0.71
NIGHT_PATH = {"bedroom", "hallway", "bathroom"}
WALK_AREAS = NIGHT_PATH | {"living", "kitchen", "dining", "office", "laundry", "other"}
COMFORT_TOILET_HEIGHT = 0.43  # 17 in seat height (ADA range 17-19 in)
# Clutter is a trip hazard only on the floor of a room people walk through (not on a table,
# a wall, or in a closet or laundry room), and it is one finding per room, not one per pile.
CLUTTER_ROOMS = NIGHT_PATH | {"living", "kitchen", "dining", "office"}
ON_FLOOR_M = 0.15


def analyze(space: Space, profile: Profile) -> tuple[str, list[Finding], list[Overlay]]:
    aid = (profile.mobility_aid or "none").lower()
    need = PATH_CLEAR.get(aid, DEFAULT_PATH)
    door_need = DOOR_CLEAR.get(aid, DEFAULT_DOOR)
    kinds = kinds_by_room(space)
    names = {r.id: r.name for r in space.rooms}
    findings: list[Finding] = []
    overlays: list[Overlay] = []
    objs = {o.id: o for o in space.objects}

    def add(f: Finding, pin_at: list[float] | None, each: list | None = None, label: str = ""):
        findings.append(f)
        if not each:
            pin(overlays, f, pin_at)
        for o in each or []:  # a grouped finding still marks every object in the 3D view
            pin(overlays, f.copy(update={"title": label, "object_ids": [o.id]}), o.position)

    # 1. Doors on the night path narrower than the person's mobility aid needs (one finding per room).
    narrow: dict[str, list] = {}
    for door in space.doors:
        if kinds.get(door.room_id) in NIGHT_PATH and door.width_m < door_need:
            narrow.setdefault(door.room_id, []).append(door)
    for room_id, doors in narrow.items():
        room = names.get(room_id, "room").lower()
        tightest = min(doors, key=lambda d: d.width_m)
        add(Finding(
            id=f"elder_{tightest.id}", kind="hazard", severity=4,
            title=f"{len(doors)} narrow {room} doors" if len(doors) > 1 else f"Narrow {room} door",
            measurements=[Measurement(name="door_width", value=inches(tightest.width_m), unit="in",
                                      required=inches(door_need), passes=False)],
            fix_summary="Swap to offset (swing-clear) hinges, which add up to 2 in of clear width",
            product_query=ProductQuery(query="swing clear offset door hinges 3.5 in", quantity=2 * len(doors)),
            evidence=[Evidence(note=f"Door width measured from the 3D model; {inches(door_need)} in needed with a {aid}"
                               if aid != "none" else "Door width measured from the 3D model")],
        ), tightest.position)

    # 2. Furniture squeezing the walk from the bed to the bedroom door.
    beds = [o for o in space.objects if o.type == "bed" and "crib" not in o.label.lower()]
    for bed in beds:
        room = next((r for r in space.rooms if r.id == bed.room_id), None)
        if room is None:
            continue
        wall_x = max(p[0] for p in room.polygon)
        _, _, bed_z0, bed_z1 = footprint(bed)
        for o in space.objects:
            if o.room_id != bed.room_id or not is_movable(o) or o.type == "clutter":
                continue
            _, _, oz0, oz1 = footprint(o)
            if oz1 < bed_z0 or oz0 > bed_z1:  # not beside the bed, so not on the bedside path
                continue
            passage = max(gap_x(bed, o), wall_x - footprint(o)[1])
            if passage < need:
                add(Finding(
                    id=f"elder_path_{o.id}", kind="hazard", severity=5,
                    title=f"{o.label.capitalize()} blocks the path from bed to door",
                    object_ids=[o.id, bed.id],
                    measurements=[Measurement(name="walkway_clearance", value=inches(passage), unit="in",
                                              required=inches(need), passes=False)],
                    fix_summary=f"Move the {o.label.lower()} out of the way to open a {inches(need)} in path",
                    evidence=evidence_for(o, "Clearance measured between furniture in the 3D model"),
                ), o.position)

    # 3. Trip hazards where people walk: loose rugs, cords, stairs.
    for o in space.objects:
        kind = kinds.get(o.room_id, "other")
        where = names.get(o.room_id, "home").lower()
        if o.type == "rug" and o.attributes.get("is_loose") and kind in WALK_AREAS:
            add(Finding(
                id=f"elder_{o.id}", kind="hazard", severity=4 if kind in NIGHT_PATH else 3,
                title=f"Loose {o.label.lower()} in the {where}",
                object_ids=[o.id],
                fix_summary="Remove it, or hold it down with a non-slip rug pad (CDC STEADI)",
                product_query=ProductQuery(
                    query=f"non-slip rug pad gripper {round(o.size[0] * 3.28)}x{round(o.size[2] * 3.28)} ft"),
                evidence=evidence_for(o, f"Rug edge in the {where} with no non-slip backing seen"),
            ), o.position)
        elif o.type == "cord" and kind in WALK_AREAS:
            add(Finding(
                id=f"elder_{o.id}", kind="hazard", severity=4, title=f"{o.label.capitalize()} on the floor",
                object_ids=[o.id],
                measurements=[Measurement(name="cord_length_on_floor", value=inches(o.size[2]), unit="in")],
                fix_summary="Run the cord along the wall under a cord cover (CDC STEADI)",
                product_query=ProductQuery(query="floor cord cover raceway 6 ft"),
                evidence=evidence_for(o, "Cord crosses a walking path"),
            ), o.position)
        elif o.type == "stairs" and not o.attributes.get("handrail_both_sides"):
            add(Finding(
                id=f"elder_{o.id}", kind="hazard", severity=5, title="Stairs without confirmed handrails",
                object_ids=[o.id],
                fix_summary="Fit sturdy handrails on both sides and light the top and bottom (CDC STEADI)",
                product_query=ProductQuery(query="stair handrail kit wall mounted"),
                evidence=evidence_for(o, "Handrails on both sides not seen in the video"),
            ), o.position)

    # 3b. Clutter on the floor: one finding per room, worst rooms (night path) first.
    piles: dict[str, list] = {}
    for o in space.objects:
        if o.type == "clutter" and floor_height(o) < ON_FLOOR_M and kinds.get(o.room_id) in CLUTTER_ROOMS:
            piles.setdefault(o.room_id, []).append(o)
    for room_id, items in piles.items():
        where = names.get(room_id, "home").lower()
        what = ", ".join(o.label.lower() for o in items[:3]) + (f" and {len(items) - 3} more" if len(items) > 3 else "")
        add(Finding(
            id=f"elder_clutter_{room_id}", kind="hazard", severity=4 if kinds.get(room_id) in NIGHT_PATH else 3,
            title=f"Clutter on the {where} floor",
            object_ids=[o.id for o in items],
            fix_summary=f"Clear the floor ({what}) or move it onto a shelf (CDC STEADI)",
            evidence=evidence_for(items[0], f"{items[0].label.capitalize()} on the floor"),
        ), items[0].position, each=items, label="Clutter")

    # 4. Lighting for night trips: no night light seen on the bedroom-to-bathroom path.
    if profile.night_trips is not False and any(k in ("bedroom", "bathroom") for k in kinds.values()):
        path_lights = [o for o in space.objects if o.type in LIGHT_TYPES and kinds.get(o.room_id) in NIGHT_PATH]
        if not any(o.attributes.get("night_light") for o in path_lights):
            add(Finding(
                id="elder_night_light", kind="hazard", severity=3,
                title="No night lighting between bedroom and bathroom",
                object_ids=[o.id for o in path_lights],
                fix_summary="Add plug-in motion-sensor night lights along the path (CDC STEADI)",
                product_query=ProductQuery(query="plug-in motion sensor LED night light 3 pack"),
                evidence=evidence_for(path_lights[0], "No night light seen on the path") if path_lights
                else [Evidence(note="No night light seen on the path")],
            ), path_lights[0].position if path_lights else None)

    # 5. Bathroom: toilet height and grab bars (none can be seen in the model unless marked).
    for o in space.objects:
        if o.type == "toilet":
            seat = o.attributes.get("seat_height_m")
            if seat is not None and seat < COMFORT_TOILET_HEIGHT:
                shape = o.attributes.get("toilet_shape", "round")
                add(Finding(
                    id=f"elder_{o.id}", kind="hazard", severity=3,
                    title=f"Low toilet seat in the {names.get(o.room_id, 'bathroom').lower()}",
                    object_ids=[o.id],
                    measurements=[Measurement(name="seat_height", value=inches(seat), unit="in",
                                              required=inches(COMFORT_TOILET_HEIGHT), passes=False)],
                    fix_summary="Add a raised toilet seat with handles",
                    product_query=ProductQuery(query=f"raised toilet seat with handles {shape}",
                                               constraints={"toilet_shape": shape}),
                    evidence=evidence_for(o, "Seat height measured from the 3D model"),
                ), o.position)
            if not o.attributes.get("grab_bar") and not any(x.type == "grab_bar" and x.room_id == o.room_id
                                                            for x in space.objects):
                add(Finding(
                    id=f"elder_grab_{o.id}", kind="hazard", severity=4,
                    title=f"No grab bar beside the {names.get(o.room_id, 'bathroom').lower()} toilet",
                    object_ids=[o.id],
                    fix_summary="Install a grab bar next to the toilet (CDC STEADI)",
                    product_query=ProductQuery(query="stainless steel grab bar 18 in"),
                    evidence=evidence_for(o, "No grab bar seen beside the toilet"),
                ), o.position)
        if o.type in ("bathtub", "shower") and not o.attributes.get("grab_bar"):
            add(Finding(
                id=f"elder_{o.id}", kind="hazard", severity=4, title=f"No grab bar at the {o.type}",
                object_ids=[o.id],
                fix_summary=f"Install grab bars inside and next to the {o.type} (CDC STEADI)",
                product_query=ProductQuery(query="stainless steel grab bar 18 in", quantity=2),
                evidence=evidence_for(o, f"No grab bar seen at the {o.type}"),
            ), o.position)

    # The 2 am walk: bed -> bedroom door -> bathroom door -> toilet.
    toilet = next((o for o in space.objects if o.type == "toilet"), None)
    if beds and toilet:
        bed = beds[0]
        points = [[footprint(bed)[1] + 0.2, 0, bed.position[2]]]
        for door in space.doors:
            if kinds.get(door.room_id) in ("bedroom", "bathroom"):
                points.append(door.position)
        points.append(toilet.position)
        blocked = next((f for f in findings if f.id.startswith("elder_path_")), None)
        path = {"points": points, "width_m": need}
        if blocked:
            path["blocked_at"] = objs[blocked.object_ids[0]].position
        overlays.append(Overlay(type="path", data=path))
        overlays.append(Overlay(type="camera", data={"mode": "first_person", "eye_height_m": 1.55, "follow_path": True}))

    findings.sort(key=lambda f: -f.severity)
    worst = sum(1 for f in findings if f.severity >= 4)
    summary = (f"Found {len(findings)} fall hazards, {worst} of them serious, on the night path from bed to bathroom."
               if findings else "No fall hazards found on the night path.")
    return summary, findings, overlays
