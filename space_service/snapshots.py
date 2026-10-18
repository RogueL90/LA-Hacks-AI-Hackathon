"""Snapshot PNGs (1200x800) for ASI:One cards.

Target: headless Chromium (Playwright) opens the viewer deep link with
?snapshot=1&view=hero and screenshots it; PNGs are cached in data/snapshots.
Until that is wired up, a plain placeholder image is returned so cards never break.
"""
import io
from typing import Optional

from PIL import Image, ImageDraw

from config import DATA_DIR

SNAPSHOTS_DIR = DATA_DIR / "snapshots"
SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)

WIDTH, HEIGHT = 1200, 800
BACKGROUND = "#F6F2EC"  # warm off-white
TEXT = "#3A3A3A"


def render_snapshot(space_id: str, mode: Optional[str], overlay_set_id: Optional[str], view: str) -> bytes:
    cache_key = f"{space_id}_{mode or 'none'}_{overlay_set_id or 'none'}_{view}.png"
    cached = SNAPSHOTS_DIR / cache_key
    if cached.exists():
        return cached.read_bytes()

    # TODO(Sun 12 AM): Playwright render of the viewer deep link.
    return _placeholder(space_id, mode)


def _placeholder(space_id: str, mode: Optional[str]) -> bytes:
    img = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(img)
    draw.text((60, 60), f"Space {space_id}", fill=TEXT)
    draw.text((60, 90), f"Mode: {mode or 'overview'} (snapshot preview pending)", fill=TEXT)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
