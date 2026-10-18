"""Build a cart from verified quotes and a flat Stripe test fee."""

from __future__ import annotations

import logging

from shared.models import CartRequest, CartResult, ProductQuote
from shared.payments import FLAT_SERVICE_FEE_USD, format_service_fee_usd

log = logging.getLogger("lmh.cart")


def line_total(quote: ProductQuote) -> float:
    quantity = quote.specs.get("quantity", 1) if quote.specs else 1
    try:
        count = int(quantity)
    except (TypeError, ValueError):
        count = 1
    if count < 1:
        count = 1
    return round(quote.price_usd * count, 2)


def _group_key(quote: ProductQuote) -> str:
    if quote.finding_id:
        return quote.finding_id
    if quote.specs and quote.specs.get("query"):
        return str(quote.specs["query"])
    return quote.title


def select_items(quotes: list[ProductQuote]) -> list[ProductQuote]:
    """Keep verified quotes. Drop a backup when its primary is already in the cart."""
    verified = [quote for quote in quotes if quote.url_verified]
    primaries: list[ProductQuote] = []
    backups: list[ProductQuote] = []
    for quote in verified:
        role = (quote.specs or {}).get("role")
        if role == "backup":
            backups.append(quote)
        else:
            primaries.append(quote)
    covered = {_group_key(quote) for quote in primaries}
    kept = list(primaries)
    for quote in backups:
        if _group_key(quote) not in covered:
            kept.append(quote)
    return kept


def build_cart(request: CartRequest) -> CartResult:
    items = select_items(request.quotes)
    dropped_unverified = len(request.quotes) - len([quote for quote in request.quotes if quote.url_verified])
    if dropped_unverified:
        log.info("left out %s quotes whose pages were not verified", dropped_unverified)

    budget = request.budget_usd
    dropped: list[str] = []
    if budget is not None:
        while items and round(sum(line_total(quote) for quote in items), 2) > budget:
            removed = items.pop()
            dropped.append(removed.title)
    if dropped:
        log.info(
            "dropped lowest-impact items to meet the budget: %s",
            ", ".join(dropped),
        )

    subtotal = round(sum(line_total(quote) for quote in items), 2)
    within = True if budget is None else subtotal <= budget + 0.001
    fee = format_service_fee_usd(FLAT_SERVICE_FEE_USD) if items else "0.00"
    note = None
    if not items:
        note = "No url_verified items to put in the cart."
    return CartResult(
        job_id=request.job_id,
        ok=True,
        cart_id=f"cart_{request.job_id}",
        items=items,
        subtotal_usd=subtotal,
        within_budget=within,
        checkout_links=[quote.url for quote in items],
        service_fee_usd=fee,
        error=note,
    )
