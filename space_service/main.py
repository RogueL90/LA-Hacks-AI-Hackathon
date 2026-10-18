"""Space Service: media -> Space JSON, overlay sets, snapshot PNGs (ADITYA.md §2).

Run:  uvicorn main:app --reload --port 8000   (from space_service/)
"""
import logging
import time
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

import storage
from config import CORS_ORIGINS, DEMO_SPACE_ID, PUBLIC_BASE_URL
from pipeline import build_space, load_prebuilt, run_pipeline
from schemas import (
    OverlaySet,
    OverlaySetCreate,
    OverlaySetCreated,
    Space,
    SpaceBuildRequest,
    SpaceBuildResult,
)
from pydantic import BaseModel
from snapshots import render_snapshot

log = logging.getLogger("space_service")

app = FastAPI(title="Maestro — Space Service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/files/media", StaticFiles(directory=storage.MEDIA_DIR), name="media")


@app.middleware("http")
async def public_is_read_only(request, call_next):
    """Through the public tunnel (Cloudflare adds cf-connecting-ip) the service only serves reads:
    homes, findings and media. Builds, uploads and debug calls come from our agents on this machine."""
    if "cf-connecting-ip" in request.headers and request.method not in ("GET", "HEAD", "OPTIONS"):
        from fastapi.responses import JSONResponse

        return JSONResponse({"detail": "read-only from the public address"}, status_code=403)
    return await call_next(request)

# The prebuilt demo space is always available (stage fallback).
storage.save_space(load_prebuilt(DEMO_SPACE_ID))


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.post("/spaces/build", response_model=SpaceBuildResult)
def build(request: SpaceBuildRequest) -> SpaceBuildResult:
    try:
        space = build_space(request)
        storage.save_space(space)
        return SpaceBuildResult(job_id=request.job_id, ok=True, space=space)
    except Exception as exc:  # never hang or 500 the agent; return ok=False
        log.exception("space build failed job_id=%s", request.job_id)
        return SpaceBuildResult(job_id=request.job_id, ok=False, error=str(exc))


@app.get("/spaces/{space_id}", response_model=Space)
def get_space(space_id: str) -> Space:
    space = storage.load_space(space_id)
    if space is None:
        raise HTTPException(404, f"space {space_id} not found")
    return space


@app.post("/spaces/{space_id}/overlays", response_model=OverlaySetCreated)
def create_overlays(space_id: str, body: OverlaySetCreate) -> OverlaySetCreated:
    if storage.load_space(space_id) is None:
        raise HTTPException(404, f"space {space_id} not found")
    overlay_set_id = storage.save_overlay_set(
        space_id, OverlaySet(mode=body.mode, overlays=body.overlays), job_id=body.job_id
    )
    return OverlaySetCreated(overlay_set_id=overlay_set_id)


@app.get("/spaces/{space_id}/overlays/latest")
def latest_overlays(space_id: str, follow: Optional[str] = None) -> dict:
    """The newest overlay set for a space, so an open viewer can follow new checks live.
    `follow` (the set the viewer opened with) limits it to checks from the same conversation."""
    latest = storage.latest_overlay_set(space_id, follow)
    if latest is None:
        raise HTTPException(404, f"no overlays for space {space_id}")
    return latest


@app.get("/spaces/{space_id}/overlays/{overlay_set_id}", response_model=OverlaySet)
def get_overlays(space_id: str, overlay_set_id: str) -> OverlaySet:
    overlay_set = storage.load_overlay_set(space_id, overlay_set_id)
    if overlay_set is None:
        raise HTTPException(404, f"overlay set {overlay_set_id} not found")
    return overlay_set


@app.get("/spaces/{space_id}/snapshot.png")
def snapshot(
    space_id: str,
    mode: Optional[str] = None,
    o: Optional[str] = None,
    view: str = "hero",
) -> Response:
    if storage.load_space(space_id) is None:
        raise HTTPException(404, f"space {space_id} not found")
    png = render_snapshot(space_id, mode, o, view)
    return Response(content=png, media_type="image/png")


@app.post("/media/upload")
async def upload_media(file: UploadFile = File(...)) -> dict:
    stored = storage.save_media(file.filename or "upload", await file.read())
    return {"url": f"{PUBLIC_BASE_URL}/files/media/{stored}"}


# --- Latency test bench (dev only): GET /test, upload a video, see per-step timings ---

class DebugBuildRequest(BaseModel):
    media_urls: list[str]
    max_frames: int = 30
    effort: Literal["low", "medium", "high"] = "low"
    floor_plan_urls: list[str] = []
    notes: Optional[str] = None


@app.get("/test", response_class=HTMLResponse)
def test_page() -> str:
    return (Path(__file__).parent / "test_page.html").read_text(encoding="utf-8")


@app.post("/debug/build")
def debug_build(body: DebugBuildRequest) -> dict:
    """Runs the real pipeline (even with USE_PREBUILT=1) and reports timings + token usage."""
    stats: dict = {}
    job_id = f"test_{int(time.time())}"
    try:
        space = run_pipeline(
            SpaceBuildRequest(
                job_id=job_id, media_urls=body.media_urls, floor_plan_urls=body.floor_plan_urls, notes=body.notes
            ),
            max_frames=max(1, min(body.max_frames, 60)),
            effort=body.effort,
            stats=stats,
        )
        storage.save_space(space)
    except Exception as exc:
        log.exception("debug build failed job_id=%s", job_id)
        return {"ok": False, "error": str(exc), "stats": stats}
    return {"ok": True, "stats": stats, "space": space.model_dump()}
