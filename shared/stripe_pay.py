"""Stripe Checkout (test mode only) for the service fee: an embedded session for the Payment
Protocol card and a hosted session whose link we post in the chat as a fallback.
"""
import asyncio
import os
import time

import stripe

from shared import config  # noqa: F401  (loads .env)

SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "").strip()
PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "").strip()
FEE_USD = os.getenv("SERVICE_FEE_USD", "4.99")
RETURN_URL = os.getenv("STRIPE_SUCCESS_URL", "https://agentverse.ai/payment-success")
PRODUCT = "Last Mile Home fix plan"


def enabled() -> bool:
    """Only test-mode keys are accepted, so a live key can never charge a real card."""
    return SECRET_KEY.startswith("sk_test_") and PUBLISHABLE_KEY.startswith("pk_test_")


def _client() -> stripe.StripeClient:
    return stripe.StripeClient(SECRET_KEY)


def _line_items(description: str) -> list[dict]:
    return [{
        "price_data": {
            "currency": "usd",
            "product_data": {"name": PRODUCT, "description": description},
            "unit_amount": round(float(FEE_USD) * 100),
        },
        "quantity": 1,
    }]


def _create(reference: str, description: str) -> dict:
    client = _client()
    expires_at = int(time.time()) + 1800  # Stripe's minimum is 30 minutes
    metadata = {"reference": reference, "service": "last_mile_home"}
    embedded = client.v1.checkout.sessions.create(params={
        "ui_mode": "embedded_page",  # Stripe renamed "embedded"; ASI:One metadata below keeps "embedded"
        "redirect_on_completion": "if_required",
        "mode": "payment",
        "return_url": f"{RETURN_URL}?session_id={{CHECKOUT_SESSION_ID}}",
        "expires_at": expires_at,
        "line_items": _line_items(description),
        "metadata": metadata,
    })
    hosted = client.v1.checkout.sessions.create(params={
        "mode": "payment",
        "success_url": f"{RETURN_URL}?session_id={{CHECKOUT_SESSION_ID}}",
        "expires_at": expires_at,
        "line_items": _line_items(description),
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
            "amount_cents": str(round(float(FEE_USD) * 100)),
        },
        "embedded_id": embedded.id,
        "hosted_id": hosted.id,
        "hosted_url": hosted.url,
    }


def _paid(session_id: str, expected_usd: float | None) -> bool:
    session = _client().v1.checkout.sessions.retrieve(session_id)
    if session.payment_status != "paid":
        return False
    return expected_usd is None or session.amount_total == round(expected_usd * 100)


async def create_checkout(reference: str, description: str) -> dict:
    return await asyncio.to_thread(_create, reference, description)


async def is_paid(session_id: str, expected_usd: float | None = None) -> bool:
    """True only if Stripe says the session is paid (and, if given, for the expected amount)."""
    return await asyncio.to_thread(_paid, session_id, expected_usd)
