"""Helpers for Agent Chat Protocol messages and ASI:One Interactive Cards."""
import json
import os
import re
from datetime import datetime, timezone
from urllib.parse import urlparse
from uuid import uuid4

from uagents_core.contrib.protocols.chat import (
    ChatMessage,
    EndSessionContent,
    MetadataContent,
    ResourceContent,
    TextContent,
)


def text_message(text: str, end_session: bool = False) -> ChatMessage:
    content = [TextContent(type="text", text=text)]
    if end_session:
        content.append(EndSessionContent(type="end-session"))
    return ChatMessage(timestamp=datetime.now(timezone.utc), msg_id=uuid4(), content=content)


def card_message(narration: str, card_kind: str, card_payload: dict, terminal: bool = False) -> ChatMessage:
    """A text bubble plus an Interactive Card. ASI:One falls back to the text if the card is invalid."""
    metadata = {
        "card_protocol_version": "1",
        "requires_card_interaction": "false" if terminal else "true",
        "card_kind": card_kind,
        "card_payload": json.dumps(card_payload),
        "preferred_drawer_width_px": "560",
    }
    if terminal:
        metadata["is_terminal"] = "true"
    return ChatMessage(
        timestamp=datetime.now(timezone.utc),
        msg_id=uuid4(),
        content=[TextContent(type="text", text=narration), MetadataContent(type="metadata", metadata=metadata)],
    )


MEDIA_TYPES = {
    ".mov": "video/quicktime", ".mp4": "video/mp4", ".m4v": "video/mp4", ".webm": "video/webm",
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".heic": "image/heic",
}
_MD_LINK = re.compile(r"!?\[([^\]]*)\]\((https?://[^\s)]+)\)")
_BARE_URL = re.compile(r"https?://[^\s)\]<>\"']+")
_TRAILING = ".,;:!?"  # sentence punctuation right after a link isn't part of it


def _media_type(url: str) -> str:
    path = urlparse(url).path.lower()
    mime = MEDIA_TYPES.get(os.path.splitext(path)[1], "")
    if not mime and "res.cloudinary.com" in url:
        mime = "video/*" if "/video/upload/" in url else "image/*"
    return mime


def attachments(msg: ChatMessage) -> list[dict]:
    """Every attached video or photo as {"url", "mime_type", "name"}.

    ASI:One sends uploads either as ResourceContent or as a Markdown link in the text
    (for example when its planner forwards the message), so both are read.
    """
    found = []
    for item in msg.content:
        if isinstance(item, ResourceContent):
            resources = item.resource if isinstance(item.resource, list) else [item.resource]
            for r in resources:
                found.append({
                    "url": r.uri,
                    "mime_type": r.metadata.get("mime_type", "") or _media_type(r.uri),
                    "name": r.metadata.get("description", ""),
                })
    text = msg.text()
    links = [(name, url) for name, url in _MD_LINK.findall(text)]
    linked = {url for _, url in links}
    links += [("", url.rstrip(_TRAILING)) for url in _BARE_URL.findall(text) if url.rstrip(_TRAILING) not in linked]
    seen = {f["url"] for f in found}
    for name, url in links:
        mime = _media_type(url)
        if mime and url not in seen:
            found.append({"url": url, "mime_type": mime, "name": name})
            seen.add(url)
    return found


_MENTION = re.compile(r"^\s*@\S+\s*")


def clean_text(msg: ChatMessage) -> str:
    """The user's text without the leading @agent mention that direct chats include."""
    return _MENTION.sub("", msg.text()).strip()


def parse_selection(text: str) -> dict:
    """A card selection. Direct @mention chats send JSON; planner-routed chats send prose, which returns {}."""
    start = text.find("{")
    if start == -1:
        return {}
    try:
        value = json.loads(text[start:])
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def video_frame(url: str, percent: int = 10, width: int = 800) -> str:
    """A still image for cards: a frame `percent` of the way into an ASI:One (Cloudinary) video, or the photo itself."""
    if "res.cloudinary.com" in url and "/video/upload/" in url:
        framed = url.replace("/video/upload/", f"/video/upload/so_{percent}p,w_{width}/", 1)
        return re.sub(r"\.[A-Za-z0-9]+$", ".jpg", framed)
    return url


def video_frame_at(url: str, seconds: float, width: int = 800) -> str | None:
    """A public still `seconds` into an ASI:One (Cloudinary) video; None for other hosts."""
    if "res.cloudinary.com" in url and "/video/upload/" in url:
        framed = url.replace("/video/upload/", f"/video/upload/so_{max(seconds, 0):.1f},w_{width}/", 1)
        return re.sub(r"\.[A-Za-z0-9]+$", ".jpg", framed)
    return None
