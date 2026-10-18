"""Build pipeline: media (video/photos) -> Space.

Steps, one module each (ADITYA.md §3):
  frames.py   video -> 1 fps frames (public URLs become Evidence.frame_url)
  plan.py     Claude pass 1: rooms, levels, connections -> placed by code
  extract.py  Claude pass 2 (per room, parallel): objects; also runs plan.py
  scale.py    scale factor from reference objects (doors, counters)
  layout.py   deterministic solver: wall snap, floor snap, de-overlap, clamp
  ids.py      stable ids: obj_{type}_{nn}, room_{name}, door_{nn}
"""
import json
import time
from typing import Optional

from config import DEMO_SPACE_ID, PREBUILT_DIR, PUBLIC_BASE_URL, USE_PREBUILT, VIEWER_BASE_URL
from pipeline.catalog import MOVABLE
from schemas import Space, SpaceBuildRequest


def public_urls(space_id: str) -> tuple[str, str]:
    """(viewer_url, snapshot_url) for a space."""
    return (
        f"{VIEWER_BASE_URL}/s/{space_id}",
        f"{PUBLIC_BASE_URL}/spaces/{space_id}/snapshot.png",
    )


def load_prebuilt(space_id: str = DEMO_SPACE_ID) -> Space:
    raw = json.loads((PREBUILT_DIR / "demo_space.json").read_text(encoding="utf-8"))
    raw["space_id"] = space_id
    raw["viewer_url"], raw["snapshot_url"] = public_urls(space_id)
    for o in raw["objects"]:  # same derived attribute the real pipeline adds
        o.setdefault("attributes", {}).setdefault("is_movable", o["type"] in MOVABLE)
    return Space.model_validate(raw)


def build_space(request: SpaceBuildRequest) -> Space:
    """Run the full pipeline. Until it is wired up, returns the prebuilt demo space."""
    if USE_PREBUILT:
        return load_prebuilt()
    return run_pipeline(request)


def run_pipeline(
    request: SpaceBuildRequest,
    max_frames: Optional[int] = None,
    effort: Optional[str] = None,
    stats: Optional[dict] = None,
) -> Space:
    """The real pipeline (ignores USE_PREBUILT). `stats` gets per-step timings and token usage."""
    from pipeline import extract, frames, ids, layout, scale

    stats = stats if stats is not None else {}
    t0 = time.perf_counter()
    frame_set = frames.extract_frames(request.media_urls, request.job_id, max_frames or frames.MAX_FRAMES)
    stats["frames"] = len(frame_set)
    stats["frames_s"] = round(time.perf_counter() - t0, 2)
    floor_plans = [str(frames.resolve_local(u)) for u in request.floor_plan_urls]
    raw = extract.extract_scene(frame_set, effort=effort, stats=stats, floor_plans=floor_plans, notes=request.notes)
    t1 = time.perf_counter()
    raw = scale.apply_scale(raw)
    raw = layout.solve(raw)
    space = ids.assign_ids(raw)
    space.viewer_url, space.snapshot_url = public_urls(space.space_id)
    stats["post_s"] = round(time.perf_counter() - t1, 3)
    stats["total_s"] = round(time.perf_counter() - t0, 2)
    return space
