"""Stripe Checkout (test mode only): one embedded session per order, which ASI:One's Pay button
opens in the chat through the Payment Protocol (the cart's products as lines plus the service fee).
"""
import asyncio
import os
import time

import stripe

from shared import config  # noqa: F401  (loads .env)

SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "").strip()
PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "").strip()
FEE_USD = os.getenv("SERVICE_FEE_USD", "1.00")  # fallback only: the Cart agent sets each plan's fee
RETURN_URL = os.getenv("STRIPE_SUCCESS_URL", "https://agentverse.ai/payment-success")
PRODUCT = "Maestro fix plan"


def enabled() -> bool:
    """Only test-mode keys are accepted, so a live key can never charge a real card."""
    return SECRET_KEY.startswith("sk_test_") and PUBLISHABLE_KEY.startswith("pk_test_")


def _client() -> stripe.StripeClient:
    return stripe.StripeClient(SECRET_KEY)


def _cents(amount_usd: str | float) -> int:
    return round(float(amount_usd) * 100)


def _line_items(description: str, amount_usd: str, items: list[dict] | None = None) -> list[dict]:
    """One line per product in the cart (demo order) plus the service fee, or just the fee."""
    if not items:
        return [{
            "price_data": {
                "currency": "usd",
                "product_data": {"name": PRODUCT, "description": description},
                "unit_amount": _cents(amount_usd),
            },
            "quantity": 1,
        }]
    lines = []
    for item in items:
        product = {"name": item["name"][:250]}
        if item.get("description"):
            product["description"] = item["description"][:500]
        if str(item.get("image") or "").startswith("https://"):
            product["images"] = [item["image"]]
        lines.append({"price_data": {"currency": "usd", "product_data": product, "unit_amount": _cents(item["unit_usd"])},
                      "quantity": max(1, int(item.get("quantity", 1)))})
    return lines


def _create(reference: str, description: str, amount_usd: str, items: list[dict] | None = None) -> dict:
    """One embedded Checkout Session: ASI:One's Pay button opens it in the chat (Payment Protocol)."""
    client = _client()
    expires_at = int(time.time()) + 1800  # Stripe's minimum is 30 minutes
    metadata = {"reference": reference, "service": "maestro"}
    embedded = client.v1.checkout.sessions.create(params={
        "ui_mode": "embedded_page",  # Stripe renamed "embedded"; ASI:One metadata below keeps "embedded"
        "redirect_on_completion": "if_required",
        "mode": "payment",
        "return_url": f"{RETURN_URL}?session_id={{CHECKOUT_SESSION_ID}}",
        "expires_at": expires_at,
        "line_items": _line_items(description, amount_usd, items),
        "metadata": metadata,
    })
    return {
        # Shape the Payment Protocol UI expects in RequestPayment.metadata["stripe"] (all strings).
        "embedded": {
            "ui_mode": "embedded",
            "publishable_key": PUBLISHABLE_KEY,
            "client_secret": embedded.client_secret,
            "checkout_session_id": embedded.id,
            "currency": "usd",
            "amount_cents": str(_cents(amount_usd)),
        },
        "embedded_id": embedded.id,
    }


def _paid(session_id: str, expected_usd: float | None) -> bool:
    session = _client().v1.checkout.sessions.retrieve(session_id)
    if session.payment_status != "paid":
        return False
    return expected_usd is None or session.amount_total == round(expected_usd * 100)


async def create_checkout(reference: str, description: str, amount_usd: str = FEE_USD,
                          items: list[dict] | None = None) -> dict:
    """items (demo order): [{"name", "unit_usd", "quantity", "image"?, "description"?}], including the
    service fee as a line; amount_usd must equal their total."""
    return await asyncio.to_thread(_create, reference, description, amount_usd, items)


async def is_paid(session_id: str, expected_usd: float | None = None) -> bool:
    """True only if Stripe says the session is paid (and, if given, for the expected amount)."""
    return await asyncio.to_thread(_paid, session_id, expected_usd)
