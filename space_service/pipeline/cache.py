"""Build cache: the same video (or photos) gives the same Space without calling Claude again.

ASI:One gives every upload a new link, so entries are keyed by the media itself, not the URL.
To answer fast, the fingerprint is the file size plus its first 1 MB (one ranged request,
about a second, instead of downloading the whole video); two different videos practically
never share both. Entries live in data/cache/{key}.json and point at the saved Space.
Bump CACHE_VERSION when the pipeline's output changes so old builds aren't reused.
"""
import hashlib
import json
import os
from pathlib import Path
from typing import Optional

import httpx

import storage
from config import DATA_DIR, PUBLIC_BASE_URL
from schemas import Space

CACHE_VERSION = "2"
CACHE_DIR = DATA_DIR / "cache"
ENABLED = os.getenv("BUILD_CACHE", "1") == "1"
MIN_SECONDS = float(os.getenv("CACHE_MIN_SECONDS", "5"))  # a cache hit still takes this long
HEAD_BYTES = 1 << 20
LOCAL_MEDIA_PREFIX = f"{PUBLIC_BASE_URL}/files/media/"


def fingerprint(url: str) -> str:
    """sha256 of "size|first 1 MB" of the file behind a URL."""
    if url.startswith(LOCAL_MEDIA_PREFIX):
        path = storage.MEDIA_DIR / Path(url[len(LOCAL_MEDIA_PREFIX):]).name
        with open(path, "rb") as f:
            head = f.read(HEAD_BYTES)
        size = path.stat().st_size
    else:
        with httpx.stream("GET", url, headers={"Range": f"bytes=0-{HEAD_BYTES - 1}"},
                          follow_redirects=True, timeout=30) as res:
            res.raise_for_status()
            head = b""
            for chunk in res.iter_bytes():
                head += chunk
                if len(head) >= HEAD_BYTES:
                    break
            head = head[:HEAD_BYTES]
            total = res.headers.get("content-range", "").rpartition("/")[2]  # "bytes 0-1048575/17744872"
            size = int(total) if total.isdigit() else int(res.headers.get("content-length", len(head)))
    return hashlib.sha256(f"{size}|".encode() + head).hexdigest()


def key(media_urls: list[str], floor_plan_urls: list[str], notes: Optional[str]) -> str:
    h = hashlib.sha256(f"v{CACHE_VERSION}".encode())
    for url in [*media_urls, "|plans|", *floor_plan_urls]:
        h.update((fingerprint(url) if url != "|plans|" else url).encode())
    h.update((notes or "").encode())
    return h.hexdigest()[:32]


def lookup(cache_key: str) -> Optional[Space]:
    if not ENABLED:
        return None
    entry = CACHE_DIR / f"{cache_key}.json"
    if not entry.exists():
        return None
    space_id = json.loads(entry.read_text(encoding="utf-8")).get("space_id", "")
    return storage.load_space(space_id)  # None if that Space was deleted


def store(cache_key: str, space: Space) -> None:
    if not ENABLED:
        return
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / f"{cache_key}.json").write_text(json.dumps({"space_id": space.space_id}), encoding="utf-8")
