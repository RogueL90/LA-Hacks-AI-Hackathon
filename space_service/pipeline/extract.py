"""Claude extraction in two passes: frames -> rooms, doors, objects (meters).

Uses ANTHROPIC_MODEL (Fable 5.1 by default) with structured outputs.

  1. plan.py   one call over every frame: rooms, levels, how they connect, frame -> room.
               Rooms are then placed by code, not by the model.
  2. per room  one call per room, in parallel, with only that room's frames at higher
               resolution: every object, positioned relative to the room's own walls.
               Small focused requests find far more objects than one call over the house.

Optional extra inputs (floor plan images, free-text notes) go to both passes and outrank
the model's own estimates. Each object records the frame + timestamp it was seen in.
The response schema is deliberately flat (no free-form dicts, no optionals) so it stays
inside the JSON-schema subset structured outputs supports.
"""
import math
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Literal, Optional

from pydantic import BaseModel

from config import ANTHROPIC_EFFORT, ANTHROPIC_PLAN_EFFORT
from pipeline import llm, plan
from pipeline.catalog import EXTRACTABLE_TYPES, GROUPS, MOVABLE

# Yes/no facts Claude lists only when true; _object_raw expands them into the attribute
# names the specialists read. A list keeps output short: most objects have none.
FLAGS = ("loose", "covered", "anchored", "grab_bar", "sharp_corners", "night_light")
ObjectType = Literal[EXTRACTABLE_TYPES]  # type: ignore[valid-type]
Flag = Literal[FLAGS]  # type: ignore[valid-type]
Shape = Literal["rectangular", "round", "oval", "l_shaped", "irregular"]

ROOM_IMAGE_PX = 1024  # per-room calls see fewer frames, so each can be sharper
MAX_FRAMES_PER_ROOM = 12
ROOM_WORKERS = 4  # concurrent per-room calls; more mostly buys 429s
ROOM_RETRIES = 2  # parallel calls on one key do hit rate limits
DEDUPE_M = 0.6  # same-type objects this close, seen from two open-plan rooms, are one object


# --- Per-room response schema (flat on purpose) ---

class ExObject(BaseModel):
    type: ObjectType
    label: str
    x: float  # footprint center, meters from the room's x_min wall
    z: float  # footprint center, meters from the room's z_min wall
    y_bottom: float  # height of the object's underside above the floor
    width_m: float  # along x before rotation
    height_m: float
    depth_m: float  # along z before rotation
    rotation_deg: float  # about the vertical axis; 0, 90, 180 or 270
    shape: Shape  # footprint shape from above
    color_hex: str
    material: str
    model_guess: str
    flags: list[Flag]
    seat_height_m: float  # toilets, chairs, sofas, beds; 0 for everything else
    confidence: float
    frame_index: int


class ExRoomObjects(BaseModel):
    objects: list[ExObject]


_CATALOG_TEXT = "\n".join(f"  {group}: {', '.join(types)}" for group, types in GROUPS.items())
_SIDE_WORDS = {"x_min": "x_min (left)", "x_max": "x_max (right)", "z_min": "z_min (back)", "z_max": "z_max (front)"}

ROOM_PROMPT = """These frames show the {name} of a home ({w:.1f} m wide along x, {d:.1f} m deep along z,
{h:.1f} m ceiling). The room's walls, using the same compass as the rest of the house:
{sides}
Use the neighbouring rooms to orient yourself in each frame.

List EVERY physical object inside this room's {w:.1f} x {d:.1f} m area, each ONCE even if it appears in
many frames (give the frame_index of the clearest one). Count multiples individually: six dining chairs
are six objects. Include small things too: outlets, switches, cords, lights, smoke detectors, grab bars,
toys, clutter. Leave out objects that belong to a neighbouring room even if they are visible.
Pick the most specific type from this catalog:
{catalog}
Use "light" for fixed light fixtures (ceiling, wall, plug-in night lights) and the lamp types for lamps.
Use "clutter" for loose items lying on the floor, and "other" only when nothing above fits (then make
the label specific).

Position: x and z are the footprint centre in meters from this room's x_min and z_min walls
(0 <= x <= {w:.1f}, 0 <= z <= {d:.1f}). y_bottom is 0 for things standing on the floor (e.g. 0.5 for a
TV on a stand, 1.4 for a painting, 0.9 for a microwave on a counter). Real-world width/height/depth.
rotation_deg is 0 when the object's front faces +z (front), 90 when it faces +x (right), 180 when it
faces back, 270 when it faces left; furniture against a wall faces away from it. shape is the
footprint seen from above. model_guess is the brand/model if you can tell (e.g. "IKEA Kallax"),
else "". seat_height_m is the seat height of toilets, chairs, sofas and beds, else 0. confidence is 0..1.
flags: list only the ones that are clearly true, usually none:
  loose          rug or mat that can slip (no visible backing or pad)
  covered        outlet has a safety cover
  anchored       tall furniture or TV visibly strapped or bolted to the wall
  grab_bar       a grab bar is mounted at this tub, shower or toilet
  sharp_corners  hard, square corners (tables, counters, dressers)
  night_light    a light that stays on low at night or is motion-activated
Sizes: interior door 2.03 x 0.81 m, kitchen counter 0.91 m high, outlet cover 0.11 m tall."""


def _sides_text(room: dict, links: list[dict]) -> str:
    sides: dict[str, list[str]] = {s: [] for s in _SIDE_WORDS}
    for link in links:
        if link["kind"] == "stairs":
            continue
        if link["room_a"] == room["name"]:
            sides[link["side"]].append(f"{link['room_b']} ({link['kind']})")
        elif link["room_b"] == room["name"]:
            sides[plan.OPPOSITE[link["side"]]].append(f"{link['room_a']} ({link['kind']})")
    return "\n".join(f"  {_SIDE_WORDS[s]}: {', '.join(n) if n else 'outer wall'}" for s, n in sides.items())


def _room_frames(room: dict, raw: dict) -> list[int]:
    """Frames taken in this room, plus frames from rooms open to it (open-plan objects show up there)."""
    open_to = {room["name"]}
    for link in raw["links"]:
        if link["kind"] == "open" and room["name"] in (link["room_a"], link["room_b"]):
            open_to.update((link["room_a"], link["room_b"]))
    own = [i for i, name in sorted(raw["frame_rooms"].items()) if name == room["name"]]
    near = [i for i, name in sorted(raw["frame_rooms"].items()) if name in open_to and name != room["name"]]
    own = own[:MAX_FRAMES_PER_ROOM]
    room_left = MAX_FRAMES_PER_ROOM - len(own)
    if len(near) > room_left:  # keep the room's own frames, then fill evenly from its open neighbours
        step = len(near) / room_left if room_left else 0
        near = [near[int(k * step)] for k in range(room_left)]
    return sorted(own + near)


def _object_raw(o: ExObject, room: dict, frames: list[dict]) -> dict:
    """One per-room object -> the raw object dict, in the shared floor-plan coordinates."""
    size = [max(o.width_m, 0.01), max(o.height_m, 0.01), max(o.depth_m, 0.01)]
    x0, z0, x1, z1 = room["rect"]
    frame = frames[o.frame_index] if 0 <= o.frame_index < len(frames) else None
    flags = set(o.flags)
    # Attribute names are the ones Shresth's specialists read (elder / baby / claim / transformer).
    attributes = {
        "is_loose": "loose" in flags,
        "covered": "covered" in flags,
        "anchored": "anchored" in flags,
        "grab_bar": "grab_bar" in flags,
        "sharp_corners": "sharp_corners" in flags,
        "night_light": "night_light" in flags,
        "is_movable": o.type in MOVABLE,
        "shape": o.shape,
        "height_from_floor": round(max(o.y_bottom, 0.0), 3),
    }
    if o.seat_height_m > 0:
        attributes["seat_height_m"] = round(o.seat_height_m, 3)
    if o.type == "toilet":
        attributes["toilet_shape"] = "elongated" if o.shape == "oval" else "round"
    if o.model_guess:
        attributes["model_guess"] = o.model_guess
    return {
        "type": o.type,
        "label": o.label.strip() or o.type.replace("_", " "),
        "room_name": room["name"],  # set here, never taken from the model
        "position": [
            x0 + min(max(o.x, 0.0), x1 - x0),
            max(o.y_bottom, 0.0) + size[1] / 2,
            z0 + min(max(o.z, 0.0), z1 - z0),
        ],
        "size": size,
        "rotation_y": math.radians(o.rotation_deg),
        "color": o.color_hex if o.color_hex.startswith("#") else None,
        "material": o.material or None,
        "attributes": attributes,
        "confidence": min(max(o.confidence, 0.0), 1.0),
        "evidence": [{"frame_url": frame["url"], "timestamp_s": frame.get("timestamp_s")}] if frame else [],
    }


def _extract_room(room: dict, raw: dict, frames: list[dict], effort: str, notes: Optional[str]) -> tuple[list[dict], dict]:
    indices = _room_frames(room, raw)
    if not indices:
        return [], {}
    x0, z0, x1, z1 = room["rect"]
    prompt = ROOM_PROMPT.format(
        name=room["name"], w=x1 - x0, d=z1 - z0, h=room["height_m"],
        sides=_sides_text(room, raw["links"]), catalog=_CATALOG_TEXT,
    )
    if notes:
        prompt += f"\n\nNotes from the person who submitted this home (trust them over your estimates):\n{notes}"
    content = llm.frame_blocks([(i, frames[i]) for i in indices], ROOM_IMAGE_PX)
    content.append({"type": "text", "text": prompt})  # images first, instructions last
    stats: dict = {}
    answer = llm.parse(content, ExRoomObjects, effort, stats, retries=ROOM_RETRIES)
    return [_object_raw(o, room, frames) for o in answer.objects if o.type != "door"], stats


def _dedupe(objects: list[dict]) -> list[dict]:
    """Rooms open to each other both see the shared objects; keep the more confident copy."""
    kept: list[dict] = []
    for o in sorted(objects, key=lambda o: -o["confidence"]):
        if any(
            k["type"] == o["type"] and k["room_name"] != o["room_name"]
            and math.dist((k["position"][0], k["position"][2]), (o["position"][0], o["position"][2])) < DEDUPE_M
            for k in kept
        ):
            continue
        kept.append(o)
    return kept


def extract_scene(
    frames: list[dict],
    effort: Optional[str] = None,
    stats: Optional[dict] = None,
    floor_plans: Optional[list[str]] = None,
    notes: Optional[str] = None,
) -> dict:
    """Returns a raw scene dict: {"rooms": [...], "doors": [...], "objects": [...], ...}.

    `effort` is for the per-room calls (the plan pass uses ANTHROPIC_PLAN_EFFORT).
    `floor_plans` are local image paths of a floor plan / map; `notes` is free text.
    `stats` (if given) is filled with latency, model and token usage for both passes.
    """
    stats = stats if stats is not None else {}
    room_effort = effort or ANTHROPIC_EFFORT

    plan_stats: dict = {}
    house = plan.extract_plan(frames, ANTHROPIC_PLAN_EFFORT, plan_stats, floor_plans=floor_plans, notes=notes)
    raw = plan.assemble(house, frames)

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=ROOM_WORKERS) as pool:
        results = list(pool.map(lambda r: _extract_room(r, raw, frames, room_effort, notes), raw["rooms"]))
    rooms_s = round(time.perf_counter() - t0, 2)

    raw["objects"] = _dedupe([o for objs, _ in results for o in objs])
    room_stats = [s for _, s in results if s]
    stats.update({
        "model": plan_stats.get("model"),
        "effort": f"plan {ANTHROPIC_PLAN_EFFORT} / rooms {room_effort}",
        "plan_s": plan_stats.get("llm_s"),
        "rooms_s": rooms_s,
        "room_calls": len(room_stats),
        "llm_s": round((plan_stats.get("llm_s") or 0) + rooms_s, 2),
        "input_tokens": plan_stats.get("input_tokens", 0) + sum(s["input_tokens"] for s in room_stats),
        "output_tokens": plan_stats.get("output_tokens", 0) + sum(s["output_tokens"] for s in room_stats),
        "rooms": len(raw["rooms"]),
        "levels": len({r["level"] for r in raw["rooms"]}),
    })
    return raw
