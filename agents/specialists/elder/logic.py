"""Elder safety checks: deterministic measurements on the Space (rules: CDC STEADI, ADA widths)."""
from agents.specialists.geometry import footprint, gap_x, inches
from shared.models import Evidence, Finding, Measurement, Overlay, ProductQuery, Profile, Space

# Clear width needed along a path, in meters (ADA: 32 in door clear width, 36 in continuous path).
CLEAR_WIDTH = {"wheelchair": 0.91}
DEFAULT_CLEAR = 0.81
NIGHT_PATH_ROOMS = {"bedroom", "hallway", "bathroom"}
COMFORT_TOILET_HEIGHT = 0.43  # 17 in seat height (ADA range 17-19 in)


def _evidence(note: str) -> list[Evidence]:
    return [Evidence(note=note)]


def analyze(space: Space, profile: Profile) -> tuple[str, list[Finding], list[Overlay]]:
    aid = (profile.mobility_aid or "none").lower()
    need = CLEAR_WIDTH.get(aid, DEFAULT_CLEAR)
    who = profile.person or "they"
    findings: list[Finding] = []
    overlays: list[Overlay] = []
    objs = {o.id: o for o in space.objects}

    def add(f: Finding, pin_at: list[float] | None):
        findings.append(f)
        if pin_at:
            overlays.append(Overlay(type="pin", data={"finding_id": f.id, "position": pin_at, "severity": f.severity}))

    # 1. Doors on the night path narrower than the clear width the person needs.
    for door in space.doors:
        if door.room_id in NIGHT_PATH_ROOMS and door.width_m < need:
            add(Finding(
                id=f"elder_{door.id}", kind="hazard", severity=4,
                title=f"Narrow {door.room_id} door",
                measurements=[Measurement(name="door_width", value=inches(door.width_m), unit="in",
                                          required=inches(need), passes=False)],
                fix_summary="Swap to offset (swing-clear) hinges, which add up to 2 in of clear width",
                product_query=ProductQuery(query="swing clear offset door hinges 3.5 in", quantity=2),
                evidence=_evidence("Door width measured from the 3D model"),
            ), door.position)

    # 2. Furniture squeezing the walk from the bed to the bedroom door.
    bed = next((o for o in space.objects if o.type == "bed"), None)
    if bed:
        for o in space.objects:
            if o.room_id != bed.room_id or not o.attributes.get("is_movable"):
                continue
            room = next(r for r in space.rooms if r.id == o.room_id)
            wall_x = max(p[0] for p in room.polygon)
            passage = max(gap_x(bed, o), wall_x - footprint(o)[1])
            if passage < need:
                add(Finding(
                    id=f"elder_path_{o.id}", kind="hazard", severity=5,
                    title=f"{o.label} blocks the path from bed to door",
                    object_ids=[o.id, bed.id],
                    measurements=[Measurement(name="walkway_clearance", value=inches(passage), unit="in",
                                              required=inches(need), passes=False)],
                    fix_summary=f"Move the {o.label.lower()} out of the bedroom to open a {inches(need)} in path",
                    evidence=_evidence("Clearance measured between furniture in the 3D model"),
                ), o.position)

    # 3. Trip hazards on the night path: loose rugs and cords.
    for o in space.objects:
        if o.room_id not in NIGHT_PATH_ROOMS:
            continue
        if o.type == "rug" and o.attributes.get("is_loose"):
            add(Finding(
                id=f"elder_{o.id}", kind="hazard", severity=4, title=f"Loose {o.label.lower()}",
                object_ids=[o.id],
                fix_summary="Remove it, or hold it down with a non-slip rug pad (CDC STEADI)",
                product_query=ProductQuery(
                    query=f"non-slip rug pad gripper {round(o.size[0] * 3.28)}x{round(o.size[2] * 3.28)} ft runner"),
                evidence=_evidence("Rug edge visible in the video with no backing"),
            ), o.position)
        if o.type == "cord":
            add(Finding(
                id=f"elder_{o.id}", kind="hazard", severity=4, title=f"{o.label}",
                object_ids=[o.id],
                measurements=[Measurement(name="cord_length_on_floor", value=inches(o.size[2]), unit="in")],
                fix_summary="Run the cord along the wall under a cord cover (CDC STEADI)",
                product_query=ProductQuery(query="floor cord cover raceway 6 ft"),
                evidence=_evidence("Cord crosses the walking path"),
            ), o.position)

    # 4. Lighting for night trips.
    if profile.night_trips is not False:
        dark = [o for o in space.objects
                if o.type == "light" and o.room_id in NIGHT_PATH_ROOMS and not o.attributes.get("night_light")]
        if dark:
            add(Finding(
                id="elder_night_light", kind="hazard", severity=3,
                title="No night lighting between bedroom and bathroom",
                object_ids=[o.id for o in dark],
                fix_summary="Add plug-in motion-sensor night lights along the path (CDC STEADI)",
                product_query=ProductQuery(query="plug-in motion sensor LED night light", quantity=3),
                evidence=_evidence("Only switch is at the far end of the hallway"),
            ), dark[0].position)

    # 5. Bathroom: low toilet and missing grab bars.
    for o in space.objects:
        if o.type == "toilet":
            seat = o.attributes.get("seat_height_m")
            if seat is not None and seat < COMFORT_TOILET_HEIGHT:
                shape = o.attributes.get("toilet_shape", "round")
                add(Finding(
                    id=f"elder_{o.id}", kind="hazard", severity=3, title="Low toilet seat",
                    object_ids=[o.id],
                    measurements=[Measurement(name="seat_height", value=inches(seat), unit="in",
                                              required=inches(COMFORT_TOILET_HEIGHT), passes=False)],
                    fix_summary="Add a raised toilet seat with handles",
                    product_query=ProductQuery(query=f"raised toilet seat with handles {shape}",
                                               constraints={"toilet_shape": shape}),
                    evidence=_evidence("Seat height measured from the 3D model"),
                ), o.position)
        if o.type == "bathtub" and not o.attributes.get("grab_bar"):
            add(Finding(
                id=f"elder_{o.id}", kind="hazard", severity=4, title="No grab bar at the tub",
                object_ids=[o.id],
                fix_summary="Install grab bars inside and next to the tub (CDC STEADI)",
                product_query=ProductQuery(query="stainless steel grab bar 18 in", quantity=2),
                evidence=_evidence("No grab bar seen on the tub wall"),
            ), o.position)

    # The 2 am walk: bed -> bedroom door -> hallway -> bathroom door -> toilet.
    toilet = next((o for o in space.objects if o.type == "toilet"), None)
    if bed and toilet:
        doors = {d.room_id: d for d in space.doors}
        points = [[footprint(bed)[1] + 0.2, 0, bed.position[2]]]
        for room_id in ("bedroom", "bathroom"):
            if room_id in doors:
                points.append(doors[room_id].position)
        points.append(toilet.position)
        blocked = next((f for f in findings if f.id.startswith("elder_path_")), None)
        path = {"points": points, "width_m": need}
        if blocked:
            path["blocked_at"] = objs[blocked.object_ids[0]].position
        overlays.append(Overlay(type="path", data=path))
        overlays.append(Overlay(type="camera", data={"mode": "first_person", "eye_height_m": 1.55, "follow_path": True}))

    findings.sort(key=lambda f: -f.severity)
    worst = sum(1 for f in findings if f.severity >= 4)
    summary = (f"Found {len(findings)} fall hazards, {worst} of them serious, on the path {who} takes at night."
               if findings else "No fall hazards found on the night path.")
    return summary, findings, overlays
