"""See your cart in your home, before you buy: every product in the cart is placed in the 3D model
where it would go (a grab bar on the wall behind the toilet, a gate at the bottom of the stairs,
monitors on the desk), at its real size.

Each cart item becomes `ghost_object` overlays (one per unit shown) that the viewer draws as a
small realistic model and lists in its cart panel. Placements are anchored to the flagged object
of the item's finding, like the pins; room makeover items go on the room's largest free wall.
"""
from __future__ import annotations

import asyncio
import json
import math
import re
from pathlib import Path

import httpx

from agents.specialists.geometry import bounds
from shared.models import CartResult, Finding, Overlay, ProductQuote, Space, SpaceObject

# (search words, viewer type, size [w, h, d] in m or None when it comes from the anchor, placement rule)
KINDS = [
    (("grab bar", "safety bar", "grab rail"), "grab_bar", [0.61, 0.05, 0.08], "wall_behind"),
    (("night light", "nightlight", "motion light", "motion sensor light", "plug-in light", "path light",
      "stair light", "led light"), "night_light", [0.07, 0.1, 0.04], "low_by_doors"),
    (("handrail", "hand rail", "stair rail", "banister"), "stair_rail", None, "stairs_side"),
    (("gate",), "baby_gate", None, "stairs_bottom"),
    (("anchor", "anti-tip", "tip-over", "anti tip", "furniture strap", "wall strap", "tip kit"),
     "anchor_strap", [0.03, 0.2, 0.012], "back_top"),
    (("corner guard", "corner protector", "corner cushion", "edge guard", "edge protector", "bumper"),
     "corner_guard", [0.05, 0.03, 0.05], "corners"),
    (("outlet cover", "outlet plug", "socket cover", "plug cover", "outlet cap", "outlet protector"),
     "outlet_cover", [0.07, 0.11, 0.012], "on_outlets"),
    (("rug gripper", "rug pad", "rug tape", "carpet tape", "rug grip", "anti-slip rug", "non-slip rug"),
     "rug_pad", None, "under_rug"),
    (("bath mat", "shower mat", "tub mat", "non-slip mat", "bathtub mat"), "rug", [0.7, 0.01, 0.4], "floor_front"),
    (("cable tray", "cable management", "cord management", "cable organizer", "cable raceway", "cord cover",
      "cable cover", "cable box"), "cable_tray", [0.6, 0.08, 0.14], "under_desk"),
    (("monitor arm", "monitor mount", "monitor stand"), "package", [0.3, 0.12, 0.25], "desk_side"),
    (("monitor", "computer display"), "monitor", [0.61, 0.46, 0.2], "desk_back"),
    (("keyboard",), "keyboard", [0.44, 0.03, 0.14], "desk_front"),
    (("mouse",), "mouse", [0.07, 0.04, 0.11], "desk_mouse"),
    (("desk lamp", "table lamp", "task lamp"), "lamp_table", [0.2, 0.45, 0.2], "desk_corner"),
    (("floor lamp",), "lamp_floor", [0.35, 1.6, 0.35], "beside_desk"),
    (("desk",), "desk", [1.2, 0.75, 0.6], "free_wall"),
    (("chair",), "office_chair", [0.62, 1.0, 0.62], "front_of_desk"),
    (("bookshelf", "bookcase", "shelf", "shelves", "shelving"), "bookshelf", [0.8, 1.8, 0.3], "second_wall"),
]
FALLBACK = ("package", [0.3, 0.2, 0.25], "beside")
MAX_UNITS = 6          # covers, lights or straps shown per cart item
WALL_GAP_M = 0.02
PHOTO_TIMEOUT_S = 2.5
PHOTO_CACHE = Path(__file__).resolve().parents[1] / "actions" / "product_finder" / "cache" / "photos.json"


def kind_of(*texts: str) -> tuple[str, list[float] | None, str]:
    """The kind of product, from the search words first and the product title second."""
    for text in texts:
        t = (text or "").lower()
        if "keyboard" in t and "mouse" in t:
            return "keyboard_mouse", [0.44, 0.04, 0.14], "desk_front"
        for words, vtype, size, rule in KINDS:
            if any(w in t for w in words):
                return vtype, size, rule
    return FALLBACK


def _rot(lx: float, lz: float, yaw: float) -> tuple[float, float]:
    """Object-local (x, z) offset -> world offset (three.js rotation about y)."""
    return lx * math.cos(yaw) + lz * math.sin(yaw), -lx * math.sin(yaw) + lz * math.cos(yaw)


def _at(o: SpaceObject, lx: float, y: float, lz: float) -> list[float]:
    dx, dz = _rot(lx, lz, o.rotation_y)
    return [round(o.position[0] + dx, 3), round(y, 3), round(o.position[2] + dz, 3)]


def _walls(space: Space, room_id: str) -> list[dict]:
    """Each wall of a (bounding-box) room with its largest free stretch, longest first."""
    room = next((r for r in space.rooms if r.id == room_id), None)
    if room is None:
        return []
    x0, x1, z0, z1 = bounds(room)
    walls = [
        {"name": "back", "axis": "x", "at": z0, "lo": x0, "hi": x1, "yaw": 0.0, "inward": 1},
        {"name": "front", "axis": "x", "at": z1, "lo": x0, "hi": x1, "yaw": math.pi, "inward": -1},
        {"name": "left", "axis": "z", "at": x0, "lo": z0, "hi": z1, "yaw": math.pi / 2, "inward": 1},
        {"name": "right", "axis": "z", "at": x1, "lo": z0, "hi": z1, "yaw": -math.pi / 2, "inward": -1},
    ]
    for w in walls:
        taken = []
        for o in space.objects:
            if o.room_id != room_id or o.type in {"outlet", "light", "window", "painting", "light_switch",
                                                   "curtain", "smoke_detector", "thermostat", "mirror"}:
                continue
            x, _, z = o.position
            half = max(o.size[0], o.size[2]) / 2
            near = abs((z if w["axis"] == "x" else x) - w["at"]) < half + 0.25
            if near:
                c = x if w["axis"] == "x" else z
                taken.append((c - half, c + half))
        edges, start = [], w["lo"]
        for a, b in sorted(taken):
            if a > start:
                edges.append((start, a))
            start = max(start, b)
        if w["hi"] > start:
            edges.append((start, w["hi"]))
        gap = max(edges, key=lambda e: e[1] - e[0], default=(w["lo"], w["lo"]))
        w["free"], w["center"] = gap[1] - gap[0], (gap[0] + gap[1]) / 2
    return sorted(walls, key=lambda w: -w["free"])


def _against(wall: dict, size: list[float], along: float | None = None, y: float | None = None) -> tuple[list[float], float]:
    """Center and yaw for an item standing against `wall`, facing into the room."""
    c = wall["center"] if along is None else along
    depth = wall["at"] + wall["inward"] * (size[2] / 2 + WALL_GAP_M)
    yy = size[1] / 2 if y is None else y
    pos = [c, yy, depth] if wall["axis"] == "x" else [depth, yy, c]
    return [round(v, 3) for v in pos], wall["yaw"]


def _nearest_wall(space: Space, room_id: str, x: float, z: float) -> dict | None:
    walls = _walls(space, room_id)
    if not walls:
        return None
    return min(walls, key=lambda w: abs((z if w["axis"] == "x" else x) - w["at"]))


class Placer:
    """Places one cart's items; keeps the desk it put down so monitors and keyboards land on it."""

    def __init__(self, space: Space, room_id: str | None):
        self.space = space
        self.objects = {o.id: o for o in space.objects}
        self.room_id = room_id
        self.desk: SpaceObject | None = next(
            (o for o in space.objects if o.room_id == room_id and o.type == "desk"), None) if room_id else None
        self.used_walls: set[str] = set()

    def _room_walls(self) -> list[dict]:
        return _walls(self.space, self.room_id) if self.room_id else []

    def _desk(self) -> SpaceObject | None:
        if self.desk is None and self.room_id:
            walls = self._room_walls()
            if walls:
                size = [1.2, 0.75, 0.6]
                pos, yaw = _against(walls[0], size)
                self.used_walls.add(walls[0]["name"])
                self.desk = SpaceObject(id="virtual_desk", type="desk", label="desk", room_id=self.room_id,
                                        position=pos, size=size, rotation_y=yaw)
        return self.desk

    def place(self, vtype: str, size: list[float] | None, rule: str, anchor: SpaceObject | None,
              units: int, finding: Finding | None) -> list[dict]:
        """[{position, size, rotation_y, pitch?, room_id, object_id?}] for each unit shown."""
        o = anchor
        out: list[dict] = []

        def put(pos, sz, yaw, room, pitch=None, obj=None):
            item = {"position": pos, "size": [round(v, 3) for v in sz], "rotation_y": round(yaw, 4), "room_id": room}
            if pitch is not None:
                item["pitch"] = round(pitch, 4)
            if obj:
                item["object_id"] = obj
            out.append(item)

        if rule == "wall_behind" and o:
            # On the wall behind the fixture (a rear bar above the toilet tank, a bar along the tub), 33-36 in up.
            put(_at(o, 0, 0.86, -o.size[2] / 2 + 0.05), size, o.rotation_y, o.room_id, obj=o.id)
        elif rule == "low_by_doors" and o:
            doors = sorted(self.space.doors, key=lambda d: math.dist((d.position[0], d.position[2]),
                                                                     (o.position[0], o.position[2])))
            rooms = {r.id: r.level for r in self.space.rooms}
            spots = [o] + [d for d in doors if rooms.get(d.room_id) == rooms.get(o.room_id)][:units - 1]
            for s in spots[:units]:
                # Low on the nearest wall: beside the flagged object, then beside each doorway on the way.
                x, z = s.position[0], s.position[2]
                wall = _nearest_wall(self.space, s.room_id, x, z)
                if wall:
                    along = (x if wall["axis"] == "x" else z) + 0.4
                    along = min(max(along, wall["lo"] + 0.1), wall["hi"] - 0.1)
                    pos, yaw = _against(wall, size, along=along, y=0.3)
                    put(pos, size, yaw, s.room_id, obj=s.id if isinstance(s, SpaceObject) else None)
        elif rule == "stairs_side" and o:
            w, h, d = o.size
            length = math.hypot(h, d)
            for side in ([1, -1][:max(1, min(units, 2))]):
                put(_at(o, side * (w / 2 - 0.05), o.position[1] + 0.86, 0), [0.05, 0.05, length],
                    o.rotation_y, o.room_id, pitch=math.atan2(h, d), obj=o.id)
        elif rule == "stairs_bottom" and o:
            w = min(o.size[0], o.size[2])
            put(_at(o, 0, 0.38, o.size[2] / 2 + 0.04), [w, 0.76, 0.04], o.rotation_y, o.room_id, obj=o.id)
        elif rule == "back_top" and o:
            w, h, d = o.size
            top = o.position[1] + h / 2
            for lx in ([-w / 3, w / 3][:max(1, min(units, 2))]):
                put(_at(o, lx, top - 0.06, -d / 2 + 0.008), size, o.rotation_y, o.room_id, obj=o.id)
        elif rule == "corners" and o:
            w, h, d = o.size
            top = o.position[1] + h / 2
            for lx, lz in [(-1, -1), (1, -1), (1, 1), (-1, 1)]:
                put(_at(o, lx * (w / 2 - 0.02), top + 0.005, lz * (d / 2 - 0.02)), size, o.rotation_y, o.room_id,
                    obj=o.id)
        elif rule == "on_outlets":
            ids = [i for i in (finding.object_ids if finding else []) if self.objects.get(i, None)
                   and self.objects[i].type == "outlet"] or ([o.id] if o else [])
            for oid in ids[:MAX_UNITS]:
                out_o = self.objects[oid]
                put(_at(out_o, 0, out_o.position[1], out_o.size[2] / 2 + 0.006), size, out_o.rotation_y,
                    out_o.room_id, obj=oid)
        elif rule == "under_rug" and o:
            w, _, d = o.size
            put([o.position[0], 0.004, o.position[2]], [w + 0.05, 0.008, d + 0.05], o.rotation_y, o.room_id, obj=o.id)
        elif rule == "floor_front" and o:
            put(_at(o, 0, size[1] / 2, o.size[2] / 2 + size[2] / 2 + 0.05), size, o.rotation_y, o.room_id, obj=o.id)
        elif rule in ("desk_back", "desk_front", "desk_mouse", "desk_corner", "desk_side", "under_desk"):
            desk = self._desk()
            if desk:
                w, h, d = desk.size
                top = desk.position[1] + h / 2
                if rule == "desk_back":
                    n = max(1, min(units, 3))
                    for i in range(n):
                        lx = (i - (n - 1) / 2) * (size[0] + 0.04)
                        put(_at(desk, lx, top + size[1] / 2, -d / 2 + size[2] / 2 + 0.05), size, desk.rotation_y,
                            desk.room_id)
                elif rule == "desk_front":
                    put(_at(desk, 0, top + size[1] / 2, d / 2 - size[2] / 2 - 0.08), size, desk.rotation_y, desk.room_id)
                elif rule == "desk_mouse":
                    put(_at(desk, 0.32, top + size[1] / 2, d / 2 - 0.15), size, desk.rotation_y, desk.room_id)
                elif rule == "under_desk":
                    put(_at(desk, 0, top - 0.1, -d / 2 + size[2] / 2 + 0.03), size, desk.rotation_y, desk.room_id)
                elif rule == "desk_corner":
                    put(_at(desk, -w / 2 + 0.15, top + size[1] / 2, -d / 2 + 0.15), size, desk.rotation_y, desk.room_id)
                else:
                    put(_at(desk, w / 2 - 0.2, top + size[1] / 2, -d / 2 + 0.15), size, desk.rotation_y, desk.room_id)
        elif rule == "free_wall" and self.room_id:
            walls = [w for w in self._room_walls() if w["name"] not in self.used_walls] or self._room_walls()
            if walls:
                pos, yaw = _against(walls[0], size)
                self.used_walls.add(walls[0]["name"])
                self.desk = SpaceObject(id="virtual_desk", type="desk", label="desk", room_id=self.room_id,
                                        position=pos, size=size, rotation_y=yaw)
                put(pos, size, yaw, self.room_id)
        elif rule == "front_of_desk":
            desk = self._desk()
            if desk:
                put(_at(desk, 0, size[1] / 2, desk.size[2] / 2 + 0.3), size, desk.rotation_y + math.pi, desk.room_id)
        elif rule == "beside_desk":
            desk = self._desk()
            if desk:
                put(_at(desk, desk.size[0] / 2 + 0.3, size[1] / 2, -desk.size[2] / 2 + 0.2), size, desk.rotation_y,
                    desk.room_id)
        elif rule == "second_wall" and self.room_id:
            walls = [w for w in self._room_walls() if w["name"] not in self.used_walls]
            if walls:
                pos, yaw = _against(walls[0], size)
                self.used_walls.add(walls[0]["name"])
                put(pos, size, yaw, self.room_id)
        if not out:
            # Anything else: the box it comes in, on the floor next to the flagged object (or mid-room).
            sz = FALLBACK[1]
            if o:
                put(_at(o, o.size[0] / 2 + 0.25, sz[1] / 2, 0), sz, o.rotation_y, o.room_id, obj=o.id)
            elif self.room_id and (room := next((r for r in self.space.rooms if r.id == self.room_id), None)):
                x0, x1, z0, z1 = bounds(room)
                put([round((x0 + x1) / 2, 3), sz[1] / 2, round((z0 + z1) / 2, 3)], sz, 0.0, self.room_id)
            return [dict(item, fallback=True) for item in out]
        return out


def ghosts(space: Space, cart: CartResult, findings: list[Finding], room_id: str | None = None,
           photos: dict[str, str] | None = None) -> list[Overlay]:
    """`ghost_object` overlays for every cart item that can be placed in this home."""
    by_id = {f.id: f for f in findings}
    objects = {o.id: o for o in space.objects}
    placer = Placer(space, room_id)
    # Desks first, so monitors and keyboards land on the new desk, not on thin air.
    order = sorted(range(len(cart.items)), key=lambda i: 0 if kind_of(*_texts(cart.items[i], by_id))[2] == "free_wall" else 1)
    overlays = []
    for i in order:
        q = cart.items[i]
        f = by_id.get(q.finding_id or "")
        vtype, size, rule = kind_of(*_texts(q, by_id))
        anchor = next((objects[o] for o in (f.object_ids if f else []) if o in objects), None)
        qty = int((q.specs or {}).get("quantity", 1) or 1)
        units = qty if rule in ("low_by_doors", "stairs_side", "back_top", "desk_back") else 1
        placed = placer.place(vtype, size, rule, anchor, max(1, min(units, MAX_UNITS)), f)
        frame = next((e.frame_url for e in (f.evidence if f else []) if e.frame_url), None)
        for u, spot in enumerate(placed):
            data = {
                "id": f"cart_{i}_{u}", "item": i, "unit": u, "units": len(placed), "action": "add",
                "type": FALLBACK[0] if spot.pop("fallback", False) else vtype,
                "label": _short(q.title), "title": q.title, "price_usd": q.price_usd, "merchant": q.merchant,
                "url": q.url, "quantity": qty, "finding_id": q.finding_id,
                "finding_title": f.title if f else None, "fix": f.fix_summary if f else None,
                "image_url": q.image_url or (photos or {}).get(q.url), "frame_url": frame, **spot,
            }
            overlays.append(Overlay(type="ghost_object", data=data))
    return overlays


def _texts(q: ProductQuote, by_id: dict[str, Finding]) -> tuple[str, str]:
    f = by_id.get(q.finding_id or "")
    query = (f.product_query.query if f and f.product_query else "") or (q.specs or {}).get("query", "")
    return query, q.title


def room_for(space: Space, findings: list[Finding], room_id: str | None) -> str | None:
    """The room a makeover plan is about: the asked room if it's real, else the room of its objects."""
    rooms = {r.id for r in space.rooms}
    if room_id in rooms:
        return room_id
    objects = {o.id: o for o in space.objects}
    return next((objects[i].room_id for f in findings for i in f.object_ids if i in objects), None)


def _short(title: str, n: int = 48) -> str:
    title = re.sub(r"\s+", " ", title).strip()
    return title if len(title) <= n else title[: n - 1].rsplit(" ", 1)[0] + "…"


# --- product photos -------------------------------------------------------------------------

_OG = [re.compile(r'<meta[^>]+(?:property|name)=["\']og:image(?::secure_url)?["\'][^>]+content=["\']([^"\']+)', re.I),
       re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']og:image["\']', re.I),
       re.compile(r'"image"\s*:\s*\[?\s*"(https?://[^"]+)"', re.I)]
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/124.0 Safari/537.36", "Accept-Language": "en-US,en;q=0.9"}


def _load_photos() -> dict:
    try:
        return json.loads(PHOTO_CACHE.read_text())
    except (OSError, ValueError):
        return {}


async def _photo(client: httpx.AsyncClient, url: str) -> str | None:
    try:
        r = await client.get(url, timeout=PHOTO_TIMEOUT_S)
        html = r.text[:400_000]
    except Exception:
        return None
    for pattern in _OG:
        m = pattern.search(html)
        if m and m.group(1).startswith("http"):
            return m.group(1).replace("&amp;", "&")
    return None


async def photos(urls: list[str]) -> dict[str, str]:
    """The store's product photo for each page (og:image), cached; pages that hide it are skipped."""
    cache = _load_photos()
    missing = [u for u in dict.fromkeys(urls) if u not in cache]
    if missing:
        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
            found = await asyncio.gather(*(_photo(client, u) for u in missing))
        cache.update({u: p or "" for u, p in zip(missing, found)})
        try:
            PHOTO_CACHE.parent.mkdir(parents=True, exist_ok=True)
            PHOTO_CACHE.write_text(json.dumps(cache, indent=1))
        except OSError:
            pass
    return {u: cache[u] for u in urls if cache.get(u)}
