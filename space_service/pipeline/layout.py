"""Deterministic layout solver (no LLM). This is what makes the dollhouse look right.

  0. rooms: shift the plan to the origin, snap corners to a 5 cm grid, and merge
     near-equal wall coordinates across rooms so shared walls line up exactly
  1. floor objects -> y = size.h / 2
  2. snap objects to the nearest wall when close
  3. push overlapping boxes apart
  4. clamp everything inside its room polygon
"""
import math

GRID_M = 0.05
WALL_MERGE_M = 0.3  # wall coordinates closer than this are the same wall
WALL_SNAP_M = 0.3  # objects this close to a wall get pushed flush against it
MIN_ROOM_M = 1.0
DOOR_CENTER_Y = 1.015  # half a standard 2.03 m door

FLOOR_TYPES = {
    "bed", "nightstand", "sofa", "armchair", "coffee_table", "dining_table", "chair", "desk",
    "tv_stand", "bookshelf", "dresser", "wardrobe", "rug", "lamp_floor", "plant", "toilet",
    "bathtub", "shower", "stairs", "refrigerator", "stove", "counter", "cabinet", "clutter", "cord",
}
WALL_MOUNTED = {"painting", "mirror", "window", "outlet"}
NO_WALL_SNAP = {"rug", "cord", "clutter", "chair", "coffee_table", "dining_table", "ceiling_light", "laptop", "lamp_table"}
NO_COLLIDE = {"rug", "cord", "ceiling_light", "outlet", "painting", "mirror", "window"}


def _snap(v: float) -> float:
    return round(round(v / GRID_M) * GRID_M, 3)


def _merge_coords(values: list[float]) -> dict[float, float]:
    """Cluster sorted coordinates within WALL_MERGE_M; map each value to its cluster's grid-snapped mean."""
    mapping: dict[float, float] = {}
    cluster: list[float] = []
    for v in sorted(set(values)) + [math.inf]:
        if cluster and v - cluster[0] > WALL_MERGE_M:
            target = _snap(sum(cluster) / len(cluster))
            mapping.update({c: target for c in cluster})
            cluster = []
        cluster.append(v)
    return mapping


def _solve_rooms(rooms: list[dict]) -> tuple[float, float]:
    """Normalizes room rects in place; returns the (x, z) shift subtracted from everything."""
    min_x = min(r["rect"][0] for r in rooms)
    min_z = min(r["rect"][1] for r in rooms)
    for r in rooms:
        x0, z0, x1, z1 = r["rect"]
        r["rect"] = [x0 - min_x, z0 - min_z, x1 - min_x, z1 - min_z]
    xs = _merge_coords([c for r in rooms for c in (r["rect"][0], r["rect"][2])])
    zs = _merge_coords([c for r in rooms for c in (r["rect"][1], r["rect"][3])])
    for r in rooms:
        x0, z0, x1, z1 = r["rect"]
        nx0, nx1, nz0, nz1 = xs[x0], xs[x1], zs[z0], zs[z1]
        # Merging must never collapse a room; fall back to a plain grid snap.
        if nx1 - nx0 < MIN_ROOM_M:
            nx0, nx1 = _snap(x0), max(_snap(x1), _snap(x0) + MIN_ROOM_M)
        if nz1 - nz0 < MIN_ROOM_M:
            nz0, nz1 = _snap(z0), max(_snap(z1), _snap(z0) + MIN_ROOM_M)
        r["rect"] = [nx0, nz0, nx1, nz1]
        r["height_m"] = round(r["height_m"], 2)
    # Merging can move the outermost walls off zero; re-anchor the plan at the origin.
    dx = min(r["rect"][0] for r in rooms)
    dz = min(r["rect"][1] for r in rooms)
    for r in rooms:
        x0, z0, x1, z1 = r["rect"]
        r["rect"] = [round(x0 - dx, 3), round(z0 - dz, 3), round(x1 - dx, 3), round(z1 - dz, 3)]
    return min_x + dx, min_z + dz


def _room_for(o: dict, rooms: list[dict]) -> dict:
    by_name = {r["name"].lower(): r for r in rooms}
    if o.get("room_name", "").lower() in by_name:
        return by_name[o["room_name"].lower()]
    x, _, z = o["position"]

    def dist(r):
        x0, z0, x1, z1 = r["rect"]
        return math.hypot(max(x0 - x, 0, x - x1), max(z0 - z, 0, z - z1))

    return min(rooms, key=dist)


def _footprint(o: dict) -> tuple[float, float]:
    w, _, d = o["size"]
    quarter_turns = round(o["rotation_y"] / (math.pi / 2)) % 4
    return (d, w) if quarter_turns % 2 else (w, d)


def _clamp_into(o: dict, rect: list[float]) -> None:
    x0, z0, x1, z1 = rect
    fw, fd = _footprint(o)
    x, y, z = o["position"]
    x = (x0 + x1) / 2 if fw >= x1 - x0 else min(max(x, x0 + fw / 2), x1 - fw / 2)
    z = (z0 + z1) / 2 if fd >= z1 - z0 else min(max(z, z0 + fd / 2), z1 - fd / 2)
    o["position"] = [x, y, z]


def _wall_snap(o: dict, rect: list[float]) -> None:
    x0, z0, x1, z1 = rect
    fw, fd = _footprint(o)
    x, y, z = o["position"]
    gaps = {"x0": x - fw / 2 - x0, "x1": x1 - (x + fw / 2), "z0": z - fd / 2 - z0, "z1": z1 - (z + fd / 2)}
    side, gap = min(gaps.items(), key=lambda kv: kv[1])
    if gap < 0:  # wider than the room; _clamp_into already centered it
        return
    if gap > WALL_SNAP_M and o["type"] not in WALL_MOUNTED:
        return
    if side == "x0":
        x = x0 + fw / 2
    elif side == "x1":
        x = x1 - fw / 2
    elif side == "z0":
        z = z0 + fd / 2
    else:
        z = z1 - fd / 2
    o["position"] = [x, y, z]


def _push_apart(objs: list[dict], rect: list[float], iterations: int = 20) -> None:
    solid = [o for o in objs if o["type"] not in NO_COLLIDE]
    for _ in range(iterations):
        moved = False
        for i, a in enumerate(solid):
            for b in solid[i + 1:]:
                (ax, ay, az), (bx, by, bz) = a["position"], b["position"]
                ah, bh = a["size"][1], b["size"][1]
                if abs(ay - by) >= (ah + bh) / 2:  # stacked (TV on a stand), not colliding
                    continue
                (aw, ad), (bw, bd) = _footprint(a), _footprint(b)
                ox = (aw + bw) / 2 - abs(ax - bx)
                oz = (ad + bd) / 2 - abs(az - bz)
                if ox <= 0.01 or oz <= 0.01:
                    continue
                moved = True
                if ox < oz:
                    s = (ox / 2 + 0.005) * (1 if ax >= bx else -1)
                    a["position"][0] += s
                    b["position"][0] -= s
                else:
                    s = (oz / 2 + 0.005) * (1 if az >= bz else -1)
                    a["position"][2] += s
                    b["position"][2] -= s
                _clamp_into(a, rect)
                _clamp_into(b, rect)
        if not moved:
            break


def _door_position(door: dict, rect: list[float]) -> list[float]:
    x0, z0, x1, z1 = rect
    half = door["width_m"] / 2
    along_x = door["wall"] in ("z_min", "z_max")
    lo, hi = (x0, x1) if along_x else (z0, z1)
    t = min(max(lo + door["offset_m"], lo + half), hi - half) if hi - lo > door["width_m"] else (lo + hi) / 2
    if along_x:
        return [round(t, 3), DOOR_CENTER_Y, z0 if door["wall"] == "z_min" else z1]
    return [x0 if door["wall"] == "x_min" else x1, DOOR_CENTER_Y, round(t, 3)]


def solve(raw: dict) -> dict:
    rooms = raw["rooms"]
    if not rooms:
        raise ValueError("layout needs at least one room")
    shift_x, shift_z = _solve_rooms(rooms)

    for o in raw["objects"]:
        o["position"][0] -= shift_x
        o["position"][2] -= shift_z
        o["rotation_y"] = round(o["rotation_y"] / (math.pi / 2)) * (math.pi / 2) % (2 * math.pi)
        room = _room_for(o, rooms)
        o["room_name"] = room["name"]
        h = o["size"][1]
        if o["type"] in FLOOR_TYPES:
            o["position"][1] = h / 2
        elif o["type"] == "ceiling_light":
            o["position"][1] = room["height_m"] - h / 2
        else:
            o["position"][1] = min(max(o["position"][1], h / 2), room["height_m"] - h / 2)
        _clamp_into(o, room["rect"])
        if o["type"] not in NO_WALL_SNAP:
            _wall_snap(o, room["rect"])

    for room in rooms:
        _push_apart([o for o in raw["objects"] if o["room_name"] == room["name"]], room["rect"])

    for o in raw["objects"]:
        o["position"] = [round(c, 3) for c in o["position"]]
        o["size"] = [round(c, 3) for c in o["size"]]
        o["rotation_y"] = round(o["rotation_y"], 4)

    by_name = {r["name"].lower(): r for r in rooms}
    for door in raw["doors"]:
        room = by_name.get(door["room_name"].lower(), rooms[0])
        door["room_name"] = room["name"]
        door["position"] = _door_position(door, room["rect"])

    for r in rooms:
        x0, z0, x1, z1 = r["rect"]
        r["polygon"] = [[x0, z0], [x1, z0], [x1, z1], [x0, z1]]
    return raw
