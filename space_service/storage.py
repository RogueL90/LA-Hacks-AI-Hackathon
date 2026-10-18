"""JSON-folder storage: data/spaces/{id}.json, data/overlays/{id}.json, data/media/*."""
import json
import uuid
from pathlib import Path
from typing import Optional

from config import DATA_DIR
from schemas import OverlaySet, Space

SPACES_DIR = DATA_DIR / "spaces"
OVERLAYS_DIR = DATA_DIR / "overlays"
MEDIA_DIR = DATA_DIR / "media"

for _d in (SPACES_DIR, OVERLAYS_DIR, MEDIA_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


def save_space(space: Space) -> None:
    _write_json(SPACES_DIR / f"{space.space_id}.json", space.model_dump())


def load_space(space_id: str) -> Optional[Space]:
    path = SPACES_DIR / f"{space_id}.json"
    if not path.exists():
        return None
    return Space.model_validate_json(path.read_text(encoding="utf-8"))


def save_overlay_set(space_id: str, overlay_set: OverlaySet) -> str:
    overlay_set_id = f"ov_{uuid.uuid4().hex[:10]}"
    payload = {"space_id": space_id, **overlay_set.model_dump()}
    _write_json(OVERLAYS_DIR / f"{overlay_set_id}.json", payload)
    return overlay_set_id


def latest_overlay_set(space_id: str) -> Optional[dict]:
    """{"overlay_set_id", "mode"} of the newest overlay set saved for a space (the viewer's live mode)."""
    if not OVERLAYS_DIR.exists():
        return None
    for path in sorted(OVERLAYS_DIR.glob("ov_*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("space_id") == space_id:
            return {"overlay_set_id": path.stem, "mode": payload.get("mode")}
    return None


def load_overlay_set(space_id: str, overlay_set_id: str) -> Optional[OverlaySet]:
    path = OVERLAYS_DIR / f"{overlay_set_id}.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("space_id") != space_id:
        return None
    return OverlaySet.model_validate(payload)


def save_media(filename: str, content: bytes) -> str:
    """Store an uploaded file; returns the stored file name."""
    suffix = Path(filename).suffix.lower()[:10]
    stored = f"{uuid.uuid4().hex[:12]}{suffix}"
    (MEDIA_DIR / stored).write_bytes(content)
    return stored
