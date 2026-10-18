"""Video -> frames with ffmpeg (1 fps, max ~30). Photos pass through as-is.

Each frame is saved under data/media and exposed as a public URL so it can be
used as Evidence.frame_url.
"""
import re
import subprocess
import uuid
from pathlib import Path

import httpx

import storage
from config import PUBLIC_BASE_URL

MAX_FRAMES = 30
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}
LOCAL_MEDIA_PREFIX = f"{PUBLIC_BASE_URL}/files/media/"


def _media_url(name: str) -> str:
    return f"{LOCAL_MEDIA_PREFIX}{name}"


def _resolve_local(url: str) -> Path:
    """Our own /files/media URLs map straight to disk; anything else is downloaded."""
    if url.startswith(LOCAL_MEDIA_PREFIX):
        path = storage.MEDIA_DIR / Path(url[len(LOCAL_MEDIA_PREFIX):]).name
        if not path.exists():
            raise FileNotFoundError(f"media not found: {url}")
        return path
    suffix = Path(httpx.URL(url).path).suffix.lower()[:10]
    path = storage.MEDIA_DIR / f"{uuid.uuid4().hex[:12]}{suffix}"
    with httpx.stream("GET", url, follow_redirects=True, timeout=60) as res:
        res.raise_for_status()
        with path.open("wb") as f:
            for chunk in res.iter_bytes():
                f.write(chunk)
    return path


def _video_frames(video: Path, prefix: str, limit: int) -> list[dict]:
    for stale in storage.MEDIA_DIR.glob(f"{prefix}_*.jpg"):  # a re-run of the same job
        stale.unlink()
    pattern = storage.MEDIA_DIR / f"{prefix}_%03d.jpg"
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(video),
            "-vf", "fps=1,scale='min(1280,iw)':-2",
            "-frames:v", str(limit),
            "-q:v", "3",
            str(pattern),
        ],
        check=True,
        timeout=90,
    )
    frames = []
    for i, path in enumerate(sorted(storage.MEDIA_DIR.glob(f"{prefix}_*.jpg"))):
        # fps=1 emits the frame at t = i seconds.
        frames.append({"url": _media_url(path.name), "timestamp_s": float(i), "path": str(path), "is_video": True})
    return frames


def extract_frames(media_urls: list[str], job_id: str, max_frames: int = MAX_FRAMES) -> list[dict]:
    """Returns [{"url": public_frame_url, "timestamp_s": float, "path": local_path}, ...]."""
    if not media_urls:
        raise ValueError("no media_urls given")
    safe_job = re.sub(r"[^A-Za-z0-9_-]", "_", job_id)[:40] or "job"
    frames: list[dict] = []
    for n, url in enumerate(media_urls):
        remaining = max_frames - len(frames)
        if remaining <= 0:
            break
        path = _resolve_local(url)
        if path.suffix.lower() in VIDEO_SUFFIXES:
            frames += _video_frames(path, f"{safe_job}_{n}", remaining)
        else:
            frames.append({"url": _media_url(path.name), "timestamp_s": None, "path": str(path), "is_video": False})
    if not frames:
        raise ValueError("no frames could be extracted from the media")
    return frames
