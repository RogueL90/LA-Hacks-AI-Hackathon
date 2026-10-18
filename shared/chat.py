"""Helpers for Agent Chat Protocol messages and ASI:One Interactive Cards."""
import json
import re
from datetime import datetime, timezone
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


def attachments(msg: ChatMessage) -> list[dict]:
    """Every attached file as {"url", "mime_type", "name"}."""
    found = []
    for item in msg.content:
        if isinstance(item, ResourceContent):
            resources = item.resource if isinstance(item.resource, list) else [item.resource]
            for r in resources:
                found.append({
                    "url": r.uri,
                    "mime_type": r.metadata.get("mime_type", ""),
                    "name": r.metadata.get("description", ""),
                })
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
