"""Pass 1: the floor plan. Frames -> rooms (size, level, floor), how they connect, and
which room each frame shows. Positions are NOT asked of the model: it is good at
"the dining area is open to the kitchen, on its right" and bad at metric coordinates,
so assemble() places the rooms from the connections in plain code.
"""
from typing import Literal, Optional

from pydantic import BaseModel

from pipeline import llm

PLAN_IMAGE_PX = 768  # all frames go in one request; Claude bills ~w*h/750 tokens per image
FLOOR_PLAN_IMAGE_PX = 1568  # a plan's labels and dimensions need the full resolution Claude reads
DEFAULT_DOOR_M = 0.81
MIN_SHARED_WALL_M = 0.3  # rooms touching along less than this aren't really connected
OVERLAP_EPS_M2 = 0.05
SLIDE_STEP_M = 0.1

Side = Literal["x_min", "x_max", "z_min", "z_max"]
OPPOSITE = {"x_min": "x_max", "x_max": "x_min", "z_min": "z_max", "z_max": "z_min"}
FloorMaterial = Literal["wood", "laminate", "vinyl", "tile", "stone", "carpet", "concrete"]


# --- Response schema ---

class PlanFrame(BaseModel):
    index: int
    room_name: str


class PlanRoom(BaseModel):
    name: str
    level: int  # 0 = entry floor, 1 = upstairs, -1 = basement
    width_m: float  # extent along x
    depth_m: float  # extent along z
    height_m: float
    floor_material: FloorMaterial


class PlanLink(BaseModel):
    room_a: str
    side: Side  # room_b lies directly beyond this wall of room_a
    room_b: str
    kind: Literal["open", "doorway", "door", "stairs"]
    align: Literal["start", "center", "end"]  # where room_b sits along that wall


class ExPlan(BaseModel):
    frames: list[PlanFrame]
    rooms: list[PlanRoom]
    links: list[PlanLink]


PROMPT = """These frames are a walkthrough video of one home, in order. Map its floor plan.

ORIENTATION: use one fixed compass for the whole home. +z is the direction the camera faces in
frame 0, +x is to its right. Keep that orientation for every room even after the camera turns:
work out each room's directions from how you walked into it. A room's width_m runs along x,
its depth_m along z.

ROOMS: every distinct space the camera visits. Split an open-plan space into its areas
(e.g. "kitchen", "dining area", "living room") and join them with "open" links. Count hallways,
landings and stair halls as rooms. Names are short and unique ("bedroom", "bedroom 2").
level is 0 for the entry floor, 1 for the floor up the stairs, -1 for a basement. Walkthrough
videos often climb stairs: rooms seen after going up a staircase are on level 1.
Sizes in meters, judged from furniture: interior door 2.03 x 0.81 m, kitchen counter 0.91 m high,
queen bed 1.5 x 2.0 m, dining chair seat ~0.45 m high. Never make a room smaller than its furniture.
floor_material is what the floor is covered with.

LINKS: one per pair of rooms that touch. "room_b lies directly beyond room_a's <side> wall".
kind: "open" = no wall between them; "doorway" = an opening in a wall without a door;
"door" = a doorway with a door; "stairs" = room_b is on another level, reached by stairs from room_a.
align: where room_b sits along that wall of room_a - "start" if their low-coordinate ends line up,
"end" if their high-coordinate ends line up, "center" if room_b is centred on it.
Every room must link to at least one other room on its level, unless it is alone on that level.

FRAMES: for every frame, the room the camera is standing in (use the room names above)."""


FLOOR_PLAN_PROMPT = """The first image(s), before the frames, are a floor plan / map of this same home supplied
by its owner. Treat it as authoritative for which rooms exist, their sizes, their levels and how they
connect; use the frames to name rooms, read floor materials and match frames to rooms. If the plan
shows dimensions, use them. Keep the compass defined above (frame 0's view is +z), not the plan's."""


def extract_plan(
    frames: list[dict],
    effort: str,
    stats: Optional[dict] = None,
    floor_plans: Optional[list[str]] = None,
    notes: Optional[str] = None,
) -> ExPlan:
    """`floor_plans`: optional local image paths of a floor plan; `notes`: optional owner text."""
    content: list[dict] = []
    for i, path in enumerate(floor_plans or []):
        content.append({"type": "text", "text": f"Floor plan image {i + 1}"})
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": llm.image_b64(path, FLOOR_PLAN_IMAGE_PX)},
        })
    content += llm.frame_blocks(list(enumerate(frames)), PLAN_IMAGE_PX)
    prompt = PROMPT
    if floor_plans:
        prompt += "\n\n" + FLOOR_PLAN_PROMPT
    if notes:
        prompt += f"\n\nNotes from the person who submitted this home (trust them over your estimates):\n{notes}"
    content.append({"type": "text", "text": prompt})  # images first, instructions last
    plan = llm.parse(content, ExPlan, effort, stats)
    if not plan.rooms:
        raise ValueError("Claude found no rooms in the media")
    return plan


# --- Assembly: connections -> rectangles ---

Rect = list[float]  # [x0, z0, x1, z1]


def _overlap_area(a: Rect, b: Rect) -> float:
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def _beside(a: Rect, w: float, d: float, side: str, align: str) -> Rect:
    """Rect of size w x d placed directly beyond `side` of rect a, aligned along that wall."""
    ax0, az0, ax1, az1 = a
    if side in ("x_min", "x_max"):
        x0 = ax1 if side == "x_max" else ax0 - w
        z0 = {"start": az0, "end": az1 - d, "center": (az0 + az1 - d) / 2}[align]
    else:
        z0 = az1 if side == "z_max" else az0 - d
        x0 = {"start": ax0, "end": ax1 - w, "center": (ax0 + ax1 - w) / 2}[align]
    return [x0, z0, x0 + w, z0 + d]


def _slide_free(r: Rect, side: str, placed: list[Rect]) -> Rect:
    """Two rooms often sit on the same side of a third; push the newcomer outward until it fits."""
    dx, dz = {"x_max": (1, 0), "x_min": (-1, 0), "z_max": (0, 1), "z_min": (0, -1)}[side]
    for _ in range(200):
        if all(_overlap_area(r, p) <= OVERLAP_EPS_M2 for p in placed):
            break
        r = [r[0] + dx * SLIDE_STEP_M, r[1] + dz * SLIDE_STEP_M, r[2] + dx * SLIDE_STEP_M, r[3] + dz * SLIDE_STEP_M]
    return r


def _shared_wall(a: Rect, b: Rect, side: str) -> Optional[tuple[float, float]]:
    """Overlap of a's `side` wall with b, as (low, high) along that wall; None if they don't touch."""
    if side in ("x_min", "x_max"):
        wall_x = a[2] if side == "x_max" else a[0]
        near = b[0] if side == "x_max" else b[2]
        lo, hi = max(a[1], b[1]), min(a[3], b[3])
    else:
        wall_x = a[3] if side == "z_max" else a[1]
        near = b[1] if side == "z_max" else b[3]
        lo, hi = max(a[0], b[0]), min(a[2], b[2])
    if abs(wall_x - near) > 0.3 or hi - lo < MIN_SHARED_WALL_M:
        return None
    return lo, hi


def _clean(plan: ExPlan) -> tuple[list[dict], list[PlanLink]]:
    rooms: list[dict] = []
    seen: set[str] = set()
    for i, r in enumerate(plan.rooms):
        name = r.name.strip() or f"room {i + 1}"
        base, n = name, 2
        while name.lower() in seen:  # objects and doors refer to rooms by name
            name, n = f"{base} {n}", n + 1
        seen.add(name.lower())
        rooms.append({
            "name": name,
            "key": r.name.strip().lower(),
            "level": r.level,
            "w": min(max(r.width_m, 1.0), 20.0),
            "d": min(max(r.depth_m, 1.0), 20.0),
            "height_m": r.height_m if 2.0 <= r.height_m <= 5.0 else 2.5,
            "floor_material": r.floor_material,
        })
    names = {r["key"] for r in rooms}
    links, pairs = [], set()
    for link in plan.links:
        a, b = link.room_a.strip().lower(), link.room_b.strip().lower()
        pair = frozenset((a, b))
        if a == b or a not in names or b not in names or pair in pairs:
            continue  # the model often lists A->B and B->A
        pairs.add(pair)
        links.append(link)
    return rooms, links


def _place_level(rooms: list[dict], links: list[PlanLink]) -> None:
    by_key = {r["key"]: r for r in rooms}
    placed: list[Rect] = []
    for start in rooms:
        if "rect" in start:
            continue
        if not placed:
            start["rect"] = [0.0, 0.0, start["w"], start["d"]]
        else:  # a room no link reaches: line it up past the east end of what's placed
            x1 = max(p[2] for p in placed)
            z0 = min(p[1] for p in placed)
            start["rect"] = [x1, z0, x1 + start["w"], z0 + start["d"]]
        placed.append(start["rect"])
        queue = [start]
        while queue:
            a = queue.pop(0)
            for link in links:
                ka, kb = link.room_a.strip().lower(), link.room_b.strip().lower()
                if ka == a["key"]:
                    other, side = by_key.get(kb), link.side
                elif kb == a["key"]:
                    other, side = by_key.get(ka), OPPOSITE[link.side]
                else:
                    continue
                if other is None or "rect" in other:
                    continue
                rect = _beside(a["rect"], other["w"], other["d"], side, link.align)
                other["rect"] = _slide_free(rect, side, placed)
                placed.append(other["rect"])
                queue.append(other)


def assemble(plan: ExPlan, frames: list[dict]) -> dict:
    """Plan -> the raw scene dict layout.py works on (rooms with rects, doors, frame -> room)."""
    rooms, links = _clean(plan)
    by_key = {r["key"]: r for r in rooms}

    levels = sorted({r["level"] for r in rooms})
    for level in levels:
        level_rooms = [r for r in rooms if r["level"] == level]
        same_level = [
            l for l in links
            if l.kind != "stairs"
            and by_key[l.room_a.strip().lower()]["level"] == level
            and by_key[l.room_b.strip().lower()]["level"] == level
        ]
        _place_level(level_rooms, same_level)

    # Stack the levels: line up the two ends of a staircase; otherwise share the origin.
    aligned = {levels[0]}
    for level in levels[1:]:
        dx = dz = 0.0
        for l in links:
            a, b = by_key[l.room_a.strip().lower()], by_key[l.room_b.strip().lower()]
            if l.kind != "stairs":
                continue
            if b["level"] == level and a["level"] in aligned:
                dx, dz = a["rect"][0] - b["rect"][0], a["rect"][1] - b["rect"][1]
                break
            if a["level"] == level and b["level"] in aligned:
                dx, dz = b["rect"][0] - a["rect"][0], b["rect"][1] - a["rect"][1]
                break
        for r in rooms:
            if r["level"] == level:
                x0, z0, x1, z1 = r["rect"]
                r["rect"] = [x0 + dx, z0 + dz, x1 + dx, z1 + dz]
        aligned.add(level)

    # Openings between rooms on the same level, in the raw door format layout.py positions.
    doors = []
    for l in links:
        if l.kind == "stairs":
            continue
        a, b = by_key[l.room_a.strip().lower()], by_key[l.room_b.strip().lower()]
        if a["level"] != b["level"]:
            continue
        seg = _shared_wall(a["rect"], b["rect"], l.side)
        if seg is None:
            continue
        lo, hi = seg
        low_end = a["rect"][1] if l.side in ("x_min", "x_max") else a["rect"][0]
        doors.append({
            "room_name": a["name"],
            "wall": l.side,
            "offset_m": (lo + hi) / 2 - low_end,
            "width_m": hi - lo if l.kind == "open" else min(DEFAULT_DOOR_M, hi - lo),
            "height_m": 0.0,  # unmeasured; scale.py ignores it
            "kind": l.kind,
        })

    frame_rooms: dict[int, str] = {}
    for f in plan.frames:
        room = by_key.get(f.room_name.strip().lower())
        if room is not None and 0 <= f.index < len(frames):
            frame_rooms[f.index] = room["name"]

    return {
        "source_type": "video" if any(f.get("is_video") for f in frames) else "photos",
        "rooms": [
            {k: r[k] for k in ("name", "rect", "height_m", "level", "floor_material")}
            for r in rooms
        ],
        "doors": doors,
        "objects": [],
        "frame_rooms": frame_rooms,
        "links": [
            {"room_a": by_key[l.room_a.strip().lower()]["name"], "side": l.side,
             "room_b": by_key[l.room_b.strip().lower()]["name"], "kind": l.kind}
            for l in links
        ],
    }
