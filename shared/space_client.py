"""Client for Aditya's Space Service, with the prebuilt demo home as the fallback."""
import os

from shared import config  # noqa: F401  (loads .env before SPACE_SERVICE_URL is read)

import httpx

from shared.demo_space import DEMO_SPACE_ID, demo_space
from shared.models import Overlay, Space

SPACE_SERVICE_URL = os.getenv("SPACE_SERVICE_URL", "").rstrip("/")


async def build_space(media_urls: list[str], timeout_s: float = 150) -> Space:
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        r = await client.post(f"{SPACE_SERVICE_URL}/spaces/build", json={"media_urls": media_urls})
        r.raise_for_status()
        return Space.model_validate(r.json())


async def get_space(space_id: str) -> Space:
    if space_id == DEMO_SPACE_ID or not SPACE_SERVICE_URL:
        return demo_space()
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(f"{SPACE_SERVICE_URL}/spaces/{space_id}")
        r.raise_for_status()
        return Space.model_validate(r.json())


async def post_overlays(space_id: str, mode: str, overlays: list[Overlay]) -> dict:
    """Store overlays for the viewer. Returns {"overlay_set_id", "viewer_url", "snapshot_url"} (empty without the service)."""
    if not SPACE_SERVICE_URL or space_id == DEMO_SPACE_ID:
        return {}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{SPACE_SERVICE_URL}/spaces/{space_id}/overlays",
            json={"mode": mode, "overlays": [o.model_dump() for o in overlays]},
        )
        r.raise_for_status()
        return r.json()
