"""Client for Aditya's Space Service, with the prebuilt demo home as the fallback."""
import os

from shared import config  # noqa: F401  (loads .env before SPACE_SERVICE_URL is read)

import httpx

from shared.demo_space import DEMO_SPACE_ID, demo_space
from shared.models import Overlay, Space

SPACE_SERVICE_URL = os.getenv("SPACE_SERVICE_URL", "").rstrip("/")


VIEWER_BASE_URL = os.getenv("VIEWER_BASE_URL", "").rstrip("/")
# Aditya's service still names the space transformer mode "interior".
SERVICE_MODE = {"transform": "interior"}


async def build_space(media_urls: list[str], job_id: str, timeout_s: float = 150) -> Space:
    """POST /spaces/build -> SpaceBuildResult {job_id, ok, space, error}."""
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        r = await client.post(f"{SPACE_SERVICE_URL}/spaces/build", json={"job_id": job_id, "media_urls": media_urls})
        r.raise_for_status()
        result = r.json()
    if not result.get("ok") or not result.get("space"):
        raise RuntimeError(f"Space Service could not build the home: {result.get('error')}")
    return Space.model_validate(result["space"])


async def get_space(space_id: str) -> Space:
    if space_id == DEMO_SPACE_ID or not SPACE_SERVICE_URL:
        return demo_space()
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(f"{SPACE_SERVICE_URL}/spaces/{space_id}")
        r.raise_for_status()
        return Space.model_validate(r.json())


async def get_overlays(space_id: str, overlay_set_id: str) -> list[Overlay]:
    """The overlays of a stored overlay set (empty without the service)."""
    if not SPACE_SERVICE_URL or not overlay_set_id or space_id == DEMO_SPACE_ID:
        return []
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{SPACE_SERVICE_URL}/spaces/{space_id}/overlays/{overlay_set_id}")
        r.raise_for_status()
    return [Overlay(**o) for o in r.json().get("overlays", [])]


async def post_overlays(space_id: str, mode: str, overlays: list[Overlay], job_id: str = "") -> dict:
    """Store overlays for the viewer. Returns {"overlay_set_id", "viewer_url", "snapshot_url"} (empty without the service)."""
    if not SPACE_SERVICE_URL or space_id == DEMO_SPACE_ID:
        return {}
    service_mode = SERVICE_MODE.get(mode, mode)
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{SPACE_SERVICE_URL}/spaces/{space_id}/overlays",
            json={"mode": service_mode, "job_id": job_id, "overlays": [o.model_dump() for o in overlays]},
        )
        r.raise_for_status()
        overlay_set_id = r.json()["overlay_set_id"]
    return {
        "overlay_set_id": overlay_set_id,
        "viewer_url": (f"{VIEWER_BASE_URL}/s/{space_id}?mode={service_mode}&o={overlay_set_id}&live=1"  # follows newer checks
                       if VIEWER_BASE_URL else None),
        "snapshot_url": f"{SPACE_SERVICE_URL}/spaces/{space_id}/snapshot.png?mode={service_mode}&o={overlay_set_id}&view=hero",
    }
