"""Claude structured extraction: frames -> rough rooms, doors, objects (meters).

Uses ANTHROPIC_MODEL (Sonnet) with structured outputs. The prompt asks Claude to
use reference objects for scale: interior door ~2.03 x 0.81 m, counter ~0.91 m,
outlet cover ~0.11 m. Each object records the frame + timestamp it was seen in.

Rooms come back as axis-aligned rectangles on one shared floor plan and doors as
(wall, offset) on a room; layout.py snaps these into clean polygons. The response
schema below is deliberately flat (no free-form dicts, no optionals) so it stays
inside the JSON-schema subset structured outputs supports.
"""
import base64
import io
import math
import os
import time
from typing import Optional

from PIL import Image
from pydantic import BaseModel

from config import ANTHROPIC_API_KEY, ANTHROPIC_EFFORT, ANTHROPIC_MODEL, EXTRACT_MODE

OBJECT_CATALOG = [
    "bed", "nightstand", "sofa", "armchair", "coffee_table", "dining_table", "chair",
    "desk", "tv", "tv_stand", "bookshelf", "dresser", "wardrobe", "rug", "lamp_floor",
    "lamp_table", "ceiling_light", "plant", "toilet", "sink", "bathtub", "shower",
    "mirror", "stairs", "outlet", "cord", "window", "door", "refrigerator", "stove",
    "counter", "cabinet", "laptop", "painting", "clutter",
    # Safety- and claim-relevant items the specialist agents check for.
    "grab_bar", "handrail", "night_light", "crib", "baby_gate", "washer", "dryer",
    "dishwasher", "microwave", "fireplace", "space_heater", "stool", "ottoman", "side_table", "shelf",
]
WALLS = ("x_min", "x_max", "z_min", "z_max")
LLM_IMAGE_PX = 1024  # longest edge; small hazards (outlets, cords) need the extra detail
LLM_TIMEOUT_S = 150.0  # high effort with 30 frames; the agents allow 180 s for a build
LLM_MAX_TOKENS = 16000


# --- Response schema (flat on purpose) ---

class ExRoom(BaseModel):
    name: str
    x_min: float
    z_min: float
    x_max: float
    z_max: float
    height_m: float


class ExDoor(BaseModel):
    room_name: str
    wall: str  # one of WALLS
    offset_m: float  # door center, measured along the wall from its min-coordinate end
    width_m: float
    height_m: float


class ExObject(BaseModel):
    type: str  # one of OBJECT_CATALOG
    label: str
    room_name: str
    x: float  # footprint center on the floor plan
    z: float
    y_bottom: float  # height of the object's underside above the floor
    width_m: float  # along x before rotation
    height_m: float
    depth_m: float  # along z before rotation
    rotation_deg: float  # about the vertical axis; 0, 90, 180 or 270
    color_hex: str
    material: str
    brand_guess: str
    model_guess: str  # "55 in LED TV", "queen platform bed"; "" if unknown
    is_loose: bool
    has_cover: bool
    sharp_corners: bool
    anchored_visible: bool  # a wall strap/anchor is actually visible (tall furniture, TVs)
    has_handrail: bool  # stairs only: handrails on both sides
    seat_height_m: float  # toilets only: seat rim height above the floor; 0 otherwise
    damage_note: str  # visible damage (water stain, crack, burn); "" if none
    confidence: float
    frame_index: int


class ExScene(BaseModel):
    rooms: list[ExRoom]
    doors: list[ExDoor]
    objects: list[ExObject]


PROMPT = f"""You are measuring a home from walkthrough frames so it can be rebuilt as a 3D floor plan.
The frames are numbered in the order given. Work in meters on ONE shared top-down floor plan:
x points right, z points forward, y is up, and the origin (0, 0) is one corner of the first room.

ROOMS: return every room you can see as an axis-aligned rectangle (x_min, z_min, x_max, z_max)
on the shared plan, plus its ceiling height. Rooms that share a wall must share that exact coordinate
(e.g. the hallway's x_min equals the living room's x_max). Hallways count as rooms.
Room names are short and unique: "living room", "kitchen", "hallway", "bedroom", "bedroom 2", "bathroom".

DOORS: list each doorway once, attached to one of the rooms it connects. "wall" is which side of that
room's rectangle it sits on: "x_min", "x_max", "z_min" or "z_max". "offset_m" is the distance from the
low-coordinate end of that wall to the center of the door. Do NOT also list doors as objects.

OBJECTS: list each physical object ONCE, even if it appears in many frames; use frame_index of the
clearest frame. type must be one of: {", ".join(t for t in OBJECT_CATALOG if t != "door")}.
Use "clutter" for loose items on the floor. Give the footprint center (x, z) on the shared plan,
y_bottom (0 for things standing on the floor; e.g. 0.5 for a TV on a stand, 1.4 for a painting),
and real-world width/height/depth. rotation_deg is 0 when the object's front faces +z.

Be exhaustive about safety-relevant details, because safety inspectors rely on this list: every
visible electrical outlet (with its height), cord or cable on the floor, rug or mat, grab bar,
handrail, night light, stair, space heater, and every table or furniture edge a child could hit.
Include all furniture and appliances (washer, dryer, dishwasher, microwave, crib...), not just big items.

Fields: brand_guess and model_guess ("55 in LED TV", "queen platform bed", "French-door refrigerator")
are "" if unknown. is_loose is for rugs/mats that can slip (no visible gripper or tape). has_cover is
for outlets with a cover or plug protector. sharp_corners is for hard-cornered tables and furniture.
anchored_visible is true only if you can SEE a wall strap or anchor on tall furniture or a TV.
has_handrail is for stairs with handrails on both sides. seat_height_m is the toilet seat rim height
(standard ~0.38 m, comfort height ~0.43 m), 0 for everything else. damage_note describes visible
damage (water stain, crack, burn, mold) or is "". confidence is 0..1.

DOORS: measure each door's width from the frame (standard interior doors are 0.71-0.91 m); do not
just assume 0.81 m.

SCALE: estimate sizes from reference objects: a standard interior door is 2.03 m tall x 0.81 m wide,
a kitchen counter is 0.91 m high, an outlet cover is 0.11 m tall, a standard bed is ~2.0 m long.
Never guess a room smaller than the furniture inside it."""


def _image_b64(path: str, px: int = LLM_IMAGE_PX) -> str:
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((px, px))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=85)
        return base64.standard_b64encode(buf.getvalue()).decode("ascii")


def _call_claude(frames: list[dict], effort: str, stats: dict, image_px: int = LLM_IMAGE_PX,
                 thinking: bool = True) -> ExScene:
    import anthropic

    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set (space_service/.env)")
    # No retries: a retried timeout would blow the 120 s build budget.
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=LLM_TIMEOUT_S, max_retries=0)

    content: list = []
    for i, frame in enumerate(frames):
        ts = frame.get("timestamp_s")
        content.append({"type": "text", "text": f"Frame {i}" + (f" (t={ts:.0f}s)" if ts is not None else "")})
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": _image_b64(frame["path"], image_px)},
        })
    content.append({"type": "text", "text": PROMPT})  # images first, instructions last

    t0 = time.perf_counter()
    extra = {}
    if not thinking:
        # Sonnet 5.5 turns thinking off with "between_tools" (accepted at effort high or below):
        # the model writes the JSON directly, which is much faster.
        extra["thinking"] = {"type": "between_tools"}
    response = client.beta.messages.parse(
        model=ANTHROPIC_MODEL,
        max_tokens=LLM_MAX_TOKENS,
        messages=[{"role": "user", "content": content}],
        output_format=ExScene,
        output_config={"effort": effort},
        # On a safety decline, the API re-runs the request on a fallback model in the same call.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        **extra,
    )
    stats.update({
        "llm_s": round(time.perf_counter() - t0, 2),
        "model": response.model,
        "effort": effort,
        "thinking": thinking,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "stop_reason": response.stop_reason,
    })
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude declined to analyze these frames")
    if response.stop_reason == "max_tokens":
        raise RuntimeError(f"Claude ran out of output tokens ({LLM_MAX_TOKENS}); try fewer frames")
    if response.parsed_output is None:
        raise RuntimeError("Claude returned no parseable scene")
    return response.parsed_output


def to_raw(scene: ExScene, frames: list[dict]) -> dict:
    """The model's flat answer -> the raw scene dict the rest of the pipeline works on."""
    rooms = [
        {
            "name": r.name.strip() or f"room {i + 1}",
            "rect": [min(r.x_min, r.x_max), min(r.z_min, r.z_max), max(r.x_min, r.x_max), max(r.z_min, r.z_max)],
            "height_m": r.height_m if 2.0 <= r.height_m <= 5.0 else 2.5,
        }
        for i, r in enumerate(scene.rooms)
    ]
    seen: set[str] = set()
    for room in rooms:  # objects and doors refer to rooms by name, so names must be unique
        base, n = room["name"], 2
        while room["name"].lower() in seen:
            room["name"], n = f"{base} {n}", n + 1
        seen.add(room["name"].lower())
    doors = [
        {
            "room_name": d.room_name,
            "wall": d.wall if d.wall in WALLS else "x_max",
            "offset_m": d.offset_m,
            "width_m": d.width_m if 0.5 <= d.width_m <= 2.0 else 0.81,
            "height_m": d.height_m,
        }
        for d in scene.doors
    ]
    objects = []
    for o in scene.objects:
        if o.type == "door":
            continue  # doors are wall openings, not furniture
        size = [max(o.width_m, 0.01), max(o.height_m, 0.01), max(o.depth_m, 0.01)]
        frame = frames[o.frame_index] if 0 <= o.frame_index < len(frames) else None
        attributes = {
            "is_loose": o.is_loose,
            "has_cover": o.has_cover,
            "sharp_corners": o.sharp_corners,
            "height_from_floor": round(max(o.y_bottom, 0.0), 3),
        }
        if o.brand_guess:
            attributes["brand_guess"] = o.brand_guess
        if o.model_guess:
            attributes["model_guess"] = o.model_guess
        if o.anchored_visible:
            attributes["anchored"] = True  # otherwise unknown: an anchor that wasn't seen isn't proof
        if o.type == "stairs":
            attributes["handrail_both_sides"] = o.has_handrail
        if o.type == "toilet" and 0.3 <= o.seat_height_m <= 0.6:
            attributes["seat_height_m"] = round(o.seat_height_m, 3)
        if o.damage_note:
            attributes["damage_note"] = o.damage_note
        objects.append({
            "type": o.type if o.type in OBJECT_CATALOG else "clutter",
            "label": o.label.strip() or o.type.replace("_", " "),
            "room_name": o.room_name,
            "position": [o.x, max(o.y_bottom, 0.0) + size[1] / 2, o.z],
            "size": size,
            "rotation_y": math.radians(o.rotation_deg),
            "color": o.color_hex if o.color_hex.startswith("#") else None,
            "material": o.material or None,
            "attributes": attributes,
            "confidence": min(max(o.confidence, 0.0), 1.0),
            "evidence": [{"frame_url": frame["url"], "timestamp_s": frame.get("timestamp_s")}] if frame else [],
        })
    return {
        "source_type": "video" if any(f.get("is_video") for f in frames) else "photos",
        "rooms": rooms,
        "doors": doors,
        "objects": objects,
    }


def extract_scene(frames: list[dict], effort: Optional[str] = None, stats: Optional[dict] = None,
                  image_px: int = LLM_IMAGE_PX, thinking: bool = True, mode: Optional[str] = None,
                  tuning: Optional[dict] = None) -> dict:
    """Returns a raw scene dict: {"rooms": [...], "doors": [...], "objects": [...]}.

    `stats` (if given) is filled with latency, model and token usage.
    """
    stats = stats if stats is not None else {}
    if (mode or EXTRACT_MODE) == "parallel":
        scene = _extract_parallel(frames, effort or ROOM_EFFORT, stats, image_px, thinking, tuning)
    else:
        scene = _call_claude(frames, effort or ANTHROPIC_EFFORT, stats, image_px, thinking)
    if not scene.rooms:
        raise ValueError("Claude found no rooms in the media")
    return to_raw(scene, frames)


# --- Parallel extraction: one quick layout pass, then one objects pass per room, run concurrently ---
#
# A single call spends ~150-200 output tokens per object, so one call over a whole home takes
# 35+ s at medium effort. Splitting the objects by room keeps each call small; the wall-clock
# time becomes layout + the slowest room instead of the sum of everything.

LAYOUT_EFFORT = os.getenv("ANTHROPIC_LAYOUT_EFFORT", "low")
ROOM_EFFORT = os.getenv("ANTHROPIC_ROOM_EFFORT", "low")
# Frames sent with each room's call (spread across the room's frames). Tuned on a 32 s tour:
# layout low/640px/no thinking + rooms low x4 frames = ~25 s with 13/13 key safety items.
MAX_ROOM_FRAMES = int(os.getenv("ROOM_FRAMES", "4"))
MAX_PARALLEL_CALLS = 10


class ExRoomSeen(BaseModel):
    name: str
    x_min: float
    z_min: float
    x_max: float
    z_max: float
    height_m: float
    frame_indices: list[int]  # every frame in which this room is visible
    has_stairs: bool  # a staircase starts or ends in this room
    stairs_handrail_both_sides: bool


class ExLayout(BaseModel):
    rooms: list[ExRoomSeen]
    doors: list[ExDoor]


class ExRoomObjects(BaseModel):
    objects: list[ExObject]


_HEADER, _rest = PROMPT.split("\n\nROOMS:", 1)
_ROOMS_DOORS, _rest = ("ROOMS:" + _rest).split("\n\nOBJECTS:", 1)
_OBJECTS, _rest = ("OBJECTS:" + _rest).split("\n\nDOORS: measure", 1)
_DOOR_WIDTHS, _SCALE = ("DOORS: measure" + _rest).split("\n\nSCALE:", 1)
_SCALE = "SCALE:" + _SCALE

LAYOUT_PROMPT = f"""{_HEADER}

{_ROOMS_DOORS}

FRAMES PER ROOM: for every room, frame_indices lists every frame in which that room is visible
(the camera is inside it or looking into it). Do not list objects in this step.
STAIRS: has_stairs is true for a room where a staircase starts or ends; stairs_handrail_both_sides is
true only if handrails are visible on both sides of those stairs.

{_DOOR_WIDTHS}

{_SCALE}"""


def _room_prompt(room: ExRoomSeen) -> str:
    return f"""{_HEADER}

This request is about ONE room only: the {room.name}, the rectangle x {room.x_min:.2f}..{room.x_max:.2f},
z {room.z_min:.2f}..{room.z_max:.2f} on the shared plan. Other rooms may be visible in these frames;
ignore their contents. Every object you list must sit inside this rectangle and use
room_name "{room.name}". frame_index refers to the frames in THIS request, numbered from 0.

{_OBJECTS}

{_SCALE}"""


def _frames_content(frames: list[dict], image_px: int, prompt: str) -> list:
    content: list = []
    for i, frame in enumerate(frames):
        ts = frame.get("timestamp_s")
        content.append({"type": "text", "text": f"Frame {i}" + (f" (t={ts:.0f}s)" if ts is not None else "")})
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": _image_b64(frame["path"], image_px)},
        })
    content.append({"type": "text", "text": prompt})  # images first, instructions last
    return content


def _parse(client, content: list, schema, effort: str, thinking: bool) -> tuple:
    """One structured-output call. Returns (parsed, usage, seconds, stop_reason)."""
    extra = {} if thinking else {"thinking": {"type": "between_tools"}}
    t0 = time.perf_counter()
    response = client.beta.messages.parse(
        model=ANTHROPIC_MODEL,
        max_tokens=LLM_MAX_TOKENS,
        messages=[{"role": "user", "content": content}],
        output_format=schema,
        output_config={"effort": effort},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        **extra,
    )
    return response.parsed_output, response.usage, time.perf_counter() - t0, response.stop_reason


LAYOUT_IMAGE_PX = int(os.getenv("LAYOUT_IMAGE_PX", "640"))  # room shapes and doors need less detail
LAYOUT_THINKING = os.getenv("LAYOUT_THINKING", "off") == "on"


def _extract_parallel(frames: list[dict], effort: str, stats: dict, image_px: int, thinking: bool,
                      tuning: Optional[dict] = None) -> ExScene:
    import anthropic
    from concurrent.futures import ThreadPoolExecutor

    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set (space_service/.env)")
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=LLM_TIMEOUT_S, max_retries=0)
    t0 = time.perf_counter()

    tuning = tuning or {}
    layout_effort = tuning.get("layout_effort") or LAYOUT_EFFORT
    layout_px = tuning.get("layout_px") or LAYOUT_IMAGE_PX
    layout_thinking = tuning.get("layout_thinking", LAYOUT_THINKING)
    room_frames = tuning.get("room_frames") or MAX_ROOM_FRAMES
    layout, usage, layout_s, stop = _parse(client, _frames_content(frames, layout_px, LAYOUT_PROMPT),
                                           ExLayout, layout_effort, layout_thinking)
    if stop == "refusal" or layout is None:
        raise RuntimeError("Claude could not map the rooms in these frames")
    tokens_in, tokens_out = usage.input_tokens, usage.output_tokens

    jobs = []
    for room in layout.rooms:
        idx = sorted({i for i in room.frame_indices if 0 <= i < len(frames)})
        if len(idx) > room_frames:  # spread the room's frames evenly
            idx = [idx[round(k * (len(idx) - 1) / max(room_frames - 1, 1))] for k in range(room_frames)]
            idx = sorted(set(idx))
        if idx:
            jobs.append((room, idx))

    def run_room(job):
        room, idx = job
        content = _frames_content([frames[i] for i in idx], image_px, _room_prompt(room))
        return _parse(client, content, ExRoomObjects, effort, thinking)

    objects: list[ExObject] = []
    room_times = []
    t_rooms = time.perf_counter()
    with ThreadPoolExecutor(max_workers=max(1, min(MAX_PARALLEL_CALLS, len(jobs)))) as pool:
        for (room, idx), outcome in zip(jobs, pool.map(lambda j: _safe(run_room, j), jobs)):
            if isinstance(outcome, Exception):
                stats.setdefault("room_errors", []).append(f"{room.name}: {outcome}")
                continue
            parsed, usage, seconds, stop = outcome
            tokens_in, tokens_out = tokens_in + usage.input_tokens, tokens_out + usage.output_tokens
            room_times.append(round(seconds, 1))
            if stop == "refusal" or parsed is None:
                continue
            for o in parsed.objects:
                o.room_name = room.name
                o.frame_index = idx[o.frame_index] if 0 <= o.frame_index < len(idx) else idx[0]
                objects.append(o)
            if room.has_stairs and not any(o.type == "stairs" for o in parsed.objects):
                objects.append(_stairs_from_layout(room, idx))

    stats.update({
        "mode": "parallel",
        "llm_s": round(time.perf_counter() - t0, 2),
        "layout_s": round(layout_s, 2),
        "rooms_s": round(time.perf_counter() - t_rooms, 2),
        "room_call_s": sorted(room_times, reverse=True),
        "calls": 1 + len(jobs),
        "model": ANTHROPIC_MODEL,
        "effort": f"layout {layout_effort} ({layout_px}px, thinking {'on' if layout_thinking else 'off'}), "
                  f"rooms {effort} ({room_frames} frames)",
        "thinking": thinking,
        "input_tokens": tokens_in,
        "output_tokens": tokens_out,
    })
    rooms = [ExRoom(name=r.name, x_min=r.x_min, z_min=r.z_min, x_max=r.x_max, z_max=r.z_max, height_m=r.height_m)
             for r in layout.rooms]
    return ExScene(rooms=rooms, doors=layout.doors, objects=objects)


def _stairs_from_layout(room: ExRoomSeen, idx: list[int]) -> ExObject:
    """Stairs the layout pass saw but the room's object pass missed (safety-critical for both inspectors)."""
    return ExObject(
        type="stairs", label="staircase", room_name=room.name,
        x=(room.x_min + room.x_max) / 2, z=(room.z_min + room.z_max) / 2, y_bottom=0.0,
        width_m=0.9, height_m=2.6, depth_m=3.0, rotation_deg=0.0, color_hex="", material="",
        brand_guess="", model_guess="", is_loose=False, has_cover=False, sharp_corners=False,
        anchored_visible=False, has_handrail=room.stairs_handrail_both_sides, seat_height_m=0.0,
        damage_note="", confidence=0.6, frame_index=idx[len(idx) // 2],
    )


def _safe(fn, arg):
    try:
        return fn(arg)
    except Exception as exc:  # one failed room must not sink the whole build
        return exc
