"""Scale correction from reference objects (doors, counters).

Sets scale_method ("door_reference" | "estimate" | ...) and scale_confidence.
"""
from statistics import median

DOOR_HEIGHT_M = 2.03
COUNTER_HEIGHT_M = 0.91
MIN_FACTOR, MAX_FACTOR = 0.6, 1.6  # beyond this the reference itself is suspect


def _ratios(raw: dict) -> tuple[list[float], str]:
    doors = [DOOR_HEIGHT_M / d["height_m"] for d in raw["doors"] if 1.0 <= d.get("height_m", 0) <= 3.5]
    if doors:
        return doors, "door_reference"
    counters = [
        COUNTER_HEIGHT_M / o["size"][1]
        for o in raw["objects"]
        if o["type"] == "counter" and 0.5 <= o["size"][1] <= 1.5
    ]
    return counters, "counter_reference"


def _scale(raw: dict, k: float) -> None:
    for room in raw["rooms"]:
        room["rect"] = [c * k for c in room["rect"]]
        room["height_m"] *= k
    for door in raw["doors"]:
        door["offset_m"] *= k
        door["width_m"] *= k
    for o in raw["objects"]:
        o["position"] = [c * k for c in o["position"]]
        o["size"] = [c * k for c in o["size"]]
        o["attributes"]["height_from_floor"] = round(o["attributes"].get("height_from_floor", 0.0) * k, 3)


def apply_scale(raw: dict) -> dict:
    ratios, method = _ratios(raw)
    if not ratios:
        raw["scale_method"], raw["scale_confidence"] = "estimate", 0.4
        return raw
    k = median(ratios)
    if not MIN_FACTOR <= k <= MAX_FACTOR:
        raw["scale_method"], raw["scale_confidence"] = "estimate", 0.3
        return raw
    if abs(k - 1.0) > 0.02:
        _scale(raw, k)
    raw["scale_method"] = method
    raw["scale_confidence"] = (0.8 if method == "door_reference" else 0.65) if len(ratios) > 1 else 0.6
    return raw
