"""Chat with the Home Product Finder directly (ASI:One, Agentverse): "find two 27 inch monitors under $150
each" -> real products with verified store pages, prices and links.

Claude splits the request into product searches; the searches use the same verification and product
pools as Maestro's fix plans. Greetings and probes get a short help message without searching.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field
from uagents import Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    TextContent,
    chat_protocol_spec,
)

from agents.actions.product_finder.search import find_products
from shared.models import FindProductsRequest, ProductQuery

MODEL = os.getenv("PRODUCT_CHAT_MODEL", "claude-sonnet-5-5")
MAX_ITEMS = 6
HELP = (
    "I'm the Home Product Finder. Tell me what you need and I'll search real stores, check each product page "
    "and price, and send you the links. For example: \"two 27 inch monitors under $150 each\", \"grab bars for a "
    "bathroom\" or \"a baby gate for a 39 in wide stair\". To get products that fit a measured room and check out "
    "the whole cart, send a home video to Maestro."
)


class Item(BaseModel):
    query: str = Field(description="A store search for one product, e.g. '27 inch IPS monitor'")
    quantity: int = Field(ge=1, le=10)
    max_price_usd: Optional[float] = Field(default=None, description="Per-unit price limit if the user gave one")


class ShoppingList(BaseModel):
    is_shopping: bool = Field(description="True if the message asks to find or price products")
    items: list[Item]


def _text(msg: ChatMessage) -> str:
    return " ".join(c.text for c in msg.content if isinstance(c, TextContent)).strip()


async def shopping_list(text: str) -> ShoppingList:
    """The products a message asks for. Without Claude, the whole message is one search."""
    try:
        import anthropic

        client = anthropic.AsyncAnthropic(timeout=20, max_retries=0)
        response = await client.beta.messages.parse(
            model=MODEL, max_tokens=800, output_format=ShoppingList, output_config={"effort": "low"},
            messages=[{"role": "user", "content": (
                f"Split this request into product searches a store would understand (at most {MAX_ITEMS}). "
                "Keep sizes and key specs in each query; put a per-unit price limit only if the user gave one. "
                f"If it isn't asking for products, set is_shopping false.\n\nRequest: {text}")}])
        if response.parsed_output is not None:
            return response.parsed_output
    except Exception:
        pass
    return ShoppingList(is_shopping=True, items=[Item(query=text[:120], quantity=1)])


def _reply(found, items: list[Item]) -> str:
    by_query: dict[str, list] = {}
    for q in found.quotes:
        by_query.setdefault((q.specs or {}).get("query", ""), []).append(q)
    lines = ["Here's what I found, each checked on the store's page:"]
    for item in items:
        quotes = by_query.get(item.query, [])
        if not quotes:
            lines.append(f"\n**{item.query}**: no product page I could confirm right now.")
            continue
        qty = f" (×{item.quantity})" if item.quantity > 1 else ""
        lines.append(f"\n**{item.query}**{qty}")
        for q in quotes[:2]:
            role = "backup pick" if (q.specs or {}).get("role") == "backup" else "best pick"
            note = " Over your price limit." if "share of your budget" in (q.fit_note or "") else ""
            lines.append(f"- [{q.title[:70]}]({q.url}): ${q.price_usd:,.2f} at {q.merchant} ({role}).{note}")
    lines.append("\nWant these fitted to your room's measurements and checked out in one cart? Send a home video "
                 "to Maestro.")
    return "\n".join(lines)


async def answer(text: str) -> str:
    """The reply to one chat message: products with links, or how to ask."""
    if len(text) < 8 or re.fullmatch(r"(hi|hello|hey|test|ping|help)[!.? ]*", text.lower()):
        return HELP
    wanted = await shopping_list(text)
    if not wanted.is_shopping or not wanted.items:
        return HELP
    items = wanted.items[:MAX_ITEMS]
    queries = [ProductQuery(query=i.query, quantity=i.quantity, max_price_usd=i.max_price_usd) for i in items]
    found = await find_products(FindProductsRequest(job_id=f"chat_{uuid4().hex[:8]}", queries=queries))
    return _reply(found, items)


def make_chat_protocol() -> Protocol:
    chat = Protocol(spec=chat_protocol_spec)

    @chat.on_message(ChatMessage)
    async def on_chat(ctx: Context, sender: str, msg: ChatMessage):
        await ctx.send(sender, ChatAcknowledgement(timestamp=msg.timestamp, acknowledged_msg_id=msg.msg_id))
        reply = await answer(_text(msg))
        await ctx.send(sender, ChatMessage(timestamp=datetime.now(timezone.utc), msg_id=uuid4(),
                                           content=[TextContent(type="text", text=reply)]))

    @chat.on_message(ChatAcknowledgement)
    async def on_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
        pass

    return chat
