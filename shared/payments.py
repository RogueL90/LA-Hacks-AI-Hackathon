"""Stripe test-mode service fee helpers.

Shresth imports these for the Coordinator card. The Payment Verifier charges
with the secret key. Test keys only: sk_test_ / pk_test_. There is no
transaction hash and no chain lookup.

Fee rule: one flat 1.00 USD per cart that contains at least one item.
"""

from __future__ import annotations

import os
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

FLAT_SERVICE_FEE_USD = "1.00"
TEST_CARD_PAYMENT_METHOD = "pm_card_visa"
DUMMY_CARD_NUMBER = "4242424242424242"


class StripeKeyError(ValueError):
    """Raised when a Stripe key is missing or is not a test-mode key."""


def format_service_fee_usd(amount: str | float | Decimal) -> str:
    quantized = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{quantized:.2f}"


def dollars_to_cents(amount: str | float | Decimal) -> int:
    quantized = (Decimal(str(amount)) * Decimal("100")).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    return int(quantized)


def require_test_secret(secret: str | None = None) -> str:
    key = secret if secret is not None else os.environ.get("STRIPE_SECRET_KEY", "")
    if not key or not key.startswith("sk_test_"):
        raise StripeKeyError(
            "STRIPE_SECRET_KEY must start with sk_test_. Refusing to charge."
        )
    return key


def require_test_publishable(key: str | None = None) -> str:
    pub = key if key is not None else os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
    if pub and not pub.startswith("pk_test_"):
        raise StripeKeyError(
            "STRIPE_PUBLISHABLE_KEY must start with pk_test_. Refusing to charge."
        )
    return pub


def charge_test_fee(
    service_fee_usd: str,
    *,
    job_id: str | None = None,
    secret_key: str | None = None,
) -> Any:
    """Create and confirm a Stripe test PaymentIntent for the service fee.

    Uses the dummy Visa PaymentMethod pm_card_visa (card 4242424242424242).
    A job_id becomes the Stripe idempotency key so a retry does not charge twice.
    """
    import stripe

    secret = require_test_secret(secret_key)
    require_test_publishable()
    fee = format_service_fee_usd(service_fee_usd)
    cents = dollars_to_cents(fee)
    if cents < 50:
        raise StripeKeyError(
            f"Stripe test charges need at least 0.50 USD; got {fee}."
        )

    stripe.api_key = secret
    kwargs: dict[str, Any] = {
        "amount": cents,
        "currency": "usd",
        "payment_method": TEST_CARD_PAYMENT_METHOD,
        "confirm": True,
        "automatic_payment_methods": {"enabled": True, "allow_redirects": "never"},
        "description": (
            "Maestro service fee. Stripe test mode, not a real charge."
        ),
        "metadata": {"service_fee_usd": fee, "mode": "stripe_test"},
    }
    if job_id:
        kwargs["idempotency_key"] = f"lmh-{job_id}"[:255]
    return stripe.PaymentIntent.create(**kwargs)


def _field(intent: Any, name: str) -> Any:
    if isinstance(intent, dict):
        return intent.get(name)
    return getattr(intent, name)


def verify_charge(intent: Any, service_fee_usd: str) -> tuple[bool, str]:
    """True only when the intent succeeded in usd for the exact fee."""
    status = _field(intent, "status")
    currency = _field(intent, "currency")
    amount = _field(intent, "amount")
    intent_id = _field(intent, "id")
    expected = dollars_to_cents(service_fee_usd)
    try:
        amount_cents = int(amount)
    except (TypeError, ValueError):
        amount_cents = -1
    matched = status == "succeeded" and currency == "usd" and amount_cents == expected
    detail = (
        "Stripe test mode, not a real charge. "
        f"PaymentIntent {intent_id}. "
        f"status={status} currency={currency} "
        f"amount_cents={amount_cents} expected_cents={expected}."
    )
    return matched, detail


def verify_checkout_session(
    session_id: str,
    service_fee_usd: str,
    *,
    secret_key: str | None = None,
) -> tuple[bool, str]:
    """True only when the Checkout Session the user paid is paid, in usd, for the exact fee."""
    import stripe

    secret = require_test_secret(secret_key)
    session = stripe.StripeClient(secret).v1.checkout.sessions.retrieve(session_id)
    expected = dollars_to_cents(service_fee_usd)
    status = session.payment_status
    currency = session.currency
    amount = session.amount_total
    matched = status == "paid" and currency == "usd" and amount == expected
    detail = (
        "Stripe test mode, not a real charge. "
        f"Checkout Session {session_id}. "
        f"payment_status={status} currency={currency} "
        f"amount_cents={amount} expected_cents={expected}."
    )
    return matched, detail
