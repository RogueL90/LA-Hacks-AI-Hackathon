"""Stable ids: obj_{type}_{nn}, room_{name}, door_{nn}; returns a validated Space."""
import re
import uuid
from collections import Counter

from schemas import Space


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "room"


def assign_ids(raw: dict) -> Space:
    room_ids: dict[str, str] = {}
    used: Counter = Counter()
    rooms = []
    for r in raw["rooms"]:
        base = f"room_{_slug(r['name'])}"
        used[base] += 1
        room_id = base if used[base] == 1 else f"{base}_{used[base]}"
        room_ids[r["name"]] = room_id
        rooms.append({"id": room_id, "name": r["name"], "polygon": r["polygon"], "height_m": r["height_m"]})

    doors = [
        {"id": f"door_{n:02d}", "room_id": room_ids[d["room_name"]], "position": d["position"], "width_m": round(d["width_m"], 3)}
        for n, d in enumerate(raw["doors"], start=1)
    ]

    per_type: Counter = Counter()
    objects = []
    for o in raw["objects"]:
        per_type[o["type"]] += 1
        objects.append({
            **{k: v for k, v in o.items() if k != "room_name"},
            "id": f"obj_{o['type']}_{per_type[o['type']]:02d}",
            "room_id": room_ids[o["room_name"]],
        })

    return Space.model_validate({
        "space_id": f"sp_{uuid.uuid4().hex[:10]}",
        "source_type": raw.get("source_type", "video"),
        "rooms": rooms,
        "doors": doors,
        "objects": objects,
        "scale_method": raw.get("scale_method", "estimate"),
        "scale_confidence": raw.get("scale_confidence", 0.4),
        "viewer_url": "",  # filled in by build_space
        "snapshot_url": "",
    })
