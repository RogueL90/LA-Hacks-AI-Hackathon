"""Local checks for Product Finder. Bureau test plus fit / cache rules."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from agents.actions.envload import load_env
from agents.actions.product_finder.search import chaos_tripped, choose_for_query
from shared.models import FindProductsRequest, ProductQuery, ProductQuote

load_env()
SAMPLES = ROOT / "evals" / "samples"


def check_fit_rules() -> None:
    query = ProductQuery(
        query="18 in bathroom grab bar",
        quantity=2,
        constraints={"length_in": 18},
    )
    candidates = [
        ProductQuote(
            title="Blocked listing",
            url="https://example.invalid/blocked",
            merchant="unknown",
            price_usd=4,
            url_verified=False,
            specs={"length_in": 12},
        ),
        ProductQuote(
            title="Too long bar",
            url="https://example.com/long",
            merchant="example",
            price_usd=9,
            url_verified=True,
            specs={"length_in": 24},
        ),
        ProductQuote(
            title="Fits pricey",
            url="https://example.com/pricey",
            merchant="example",
            price_usd=22,
            url_verified=True,
            specs={"length_in": 16},
        ),
        ProductQuote(
            title="Fits cheap",
            url="https://example.com/cheap",
            merchant="example",
            price_usd=15,
            url_verified=True,
            specs={"length_in": 18},
        ),
    ]
    chosen = choose_for_query(query, candidates)
    titles = [quote.title for quote in chosen]
    if titles != ["Fits cheap", "Fits pricey"]:
        raise SystemExit(f"expected cheapest fit plus backup, got {titles}")
    if chosen[0].specs.get("role") != "primary" or chosen[1].specs.get("role") != "backup":
        raise SystemExit("primary and backup roles were not set")
    if chosen[0].specs.get("quantity") != 2:
        raise SystemExit("quantity was not copied onto the quote")
    if not chosen[0].url_verified:
        raise SystemExit("unverified quote was returned")
    if choose_for_query(query, candidates[:1]):
        raise SystemExit("an unverified quote was treated as a result")
    print("fit rules ok")


def check_chaos_once() -> None:
    from agents.actions.product_finder import search

    search._chaos_used = False
    os.environ["CHAOS_PRODUCT_FINDER"] = "1"
    first = chaos_tripped()
    second = chaos_tripped()
    os.environ["CHAOS_PRODUCT_FINDER"] = "0"
    search._chaos_used = False
    if not first or second:
        raise SystemExit(f"chaos flag failed first={first} second={second}")
    print("chaos flag ok")


def main() -> None:
    check_fit_rules()
    check_chaos_once()
    request = FindProductsRequest.model_validate_json((SAMPLES / "elder_products.json").read_text())
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))

    def check(msg) -> None:
        if has_key:
            if not msg.ok:
                raise SystemExit(msg.error or "search failed")
            if not msg.quotes:
                raise SystemExit(msg.error or "no quotes")
            if any(not quote.url_verified for quote in msg.quotes):
                raise SystemExit("unverified quote returned")
            return
        if msg.ok or "ANTHROPIC_API_KEY" not in (msg.error or ""):
            raise SystemExit(f"expected a missing-key error, got {msg.error}")

    from agent import agent
    from agents.actions.harness import run_bureau
    from shared.models import FindProductsResult

    run_bureau(agent, request, FindProductsResult, check, timeout_s=90)


if __name__ == "__main__":
    main()
