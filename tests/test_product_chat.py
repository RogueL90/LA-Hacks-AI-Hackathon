"""Chatting with the Home Product Finder directly (ASI:One can call it now)."""
import asyncio

from agents.actions.product_finder import chat
from shared.models import FindProductsResult, ProductQuote


def run(coro):
    return asyncio.run(coro)


def test_greetings_and_probes_get_help_without_searching(monkeypatch):
    async def boom(*a, **k):
        raise AssertionError("should not search")

    monkeypatch.setattr(chat, "find_products", boom)
    monkeypatch.setattr(chat, "shopping_list", boom)
    for text in ("hi", "Hello!", "test", "ping"):
        assert run(chat.answer(text)) == chat.HELP


def test_a_shopping_request_returns_checked_products_with_links(monkeypatch):
    async def wants(text):
        return chat.ShoppingList(is_shopping=True, items=[chat.Item(query="27 inch IPS monitor", quantity=2, max_price_usd=150),
                                                          chat.Item(query="wireless keyboard and mouse combo", quantity=1)])

    async def finds(req):
        q = req.queries[0]
        return FindProductsResult(job_id=req.job_id, ok=True, quotes=[ProductQuote(
            title="ASUS 27 inch IPS monitor", url="https://store/asus", merchant="Walmart", price_usd=119.0,
            url_verified=True, specs={"query": q.query, "role": "primary"})])

    monkeypatch.setattr(chat, "shopping_list", wants)
    monkeypatch.setattr(chat, "find_products", finds)
    reply = run(chat.answer("Find two 27 inch monitors under $150 each and a wireless keyboard and mouse"))
    assert "**27 inch IPS monitor** (×2)" in reply
    assert "[ASUS 27 inch IPS monitor](https://store/asus): $119.00 at Walmart (best pick)" in reply
    assert "**wireless keyboard and mouse combo**: no product page I could confirm" in reply
    assert "Maestro" in reply


def test_without_claude_the_whole_message_is_one_search(monkeypatch):
    import anthropic

    class Broken:
        def __init__(self, *a, **k):
            raise RuntimeError("offline")

    monkeypatch.setattr(anthropic, "AsyncAnthropic", Broken)
    wanted = run(chat.shopping_list("a baby gate for a 39 in wide stair"))
    assert wanted.is_shopping and [i.query for i in wanted.items] == ["a baby gate for a 39 in wide stair"]
