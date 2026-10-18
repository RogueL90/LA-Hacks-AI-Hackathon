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
import time
from typing import Optional

from PIL import Image
from pydantic import BaseModel

from config import ANTHROPIC_API_KEY, ANTHROPIC_EFFORT, ANTHROPIC_MODEL

OBJECT_CATALOG = [
    "bed", "nightstand", "sofa", "armchair", "coffee_table", "dining_table", "chair",
    "desk", "tv", "tv_stand", "bookshelf", "dresser", "wardrobe", "rug", "lamp_floor",
    "lamp_table", "ceiling_light", "plant", "toilet", "sink", "bathtub", "shower",
    "mirror", "stairs", "outlet", "cord", "window", "door", "refrigerator", "stove",
    "counter", "cabinet", "laptop", "painting", "clutter",
]
WALLS = ("x_min", "x_max", "z_min", "z_max")
LLM_IMAGE_PX = 768  # longest edge; Claude bills ~w*h/750 tokens per image (~450 for 768x432)
LLM_TIMEOUT_S = 90.0  # keeps the whole build inside the 120 s budget
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
    is_loose: bool
    has_cover: bool
    sharp_corners: bool
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
Fill brand_guess with "" if unknown. is_loose is for rugs/mats that can slip, has_cover for outlets,
sharp_corners for tables and furniture with hard corners. confidence is 0..1.

SCALE: estimate sizes from reference objects: a standard interior door is 2.03 m tall x 0.81 m wide,
a kitchen counter is 0.91 m high, an outlet cover is 0.11 m tall, a standard bed is ~2.0 m long.
Never guess a room smaller than the furniture inside it."""


def _image_b64(path: str) -> str:
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((LLM_IMAGE_PX, LLM_IMAGE_PX))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=85)
        return base64.standard_b64encode(buf.getvalue()).decode("ascii")


def _call_claude(frames: list[dict], effort: str, stats: dict) -> ExScene:
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
            "source": {"type": "base64", "media_type": "image/jpeg", "data": _image_b64(frame["path"])},
        })
    content.append({"type": "text", "text": PROMPT})  # images first, instructions last

    t0 = time.perf_counter()
    response = client.beta.messages.parse(
        model=ANTHROPIC_MODEL,
        max_tokens=LLM_MAX_TOKENS,
        messages=[{"role": "user", "content": content}],
        output_format=ExScene,
        output_config={"effort": effort},
        # On a safety decline, the API re-runs the request on a fallback model in the same call.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    stats.update({
        "llm_s": round(time.perf_counter() - t0, 2),
        "model": response.model,
        "effort": effort,
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


def extract_scene(frames: list[dict], effort: Optional[str] = None, stats: Optional[dict] = None) -> dict:
    """Returns a raw scene dict: {"rooms": [...], "doors": [...], "objects": [...]}.

    `stats` (if given) is filled with latency, model and token usage.
    """
    scene = _call_claude(frames, effort or ANTHROPIC_EFFORT, stats if stats is not None else {})
    if not scene.rooms:
        raise ValueError("Claude found no rooms in the media")
    return to_raw(scene, frames)
