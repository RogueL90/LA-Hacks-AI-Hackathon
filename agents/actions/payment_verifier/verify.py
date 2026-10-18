"""Check the service fee in Stripe test mode.

Two ways in:
- With a transaction_id (a Checkout Session the user paid inside ASI:One), confirm Stripe
  says it is paid, in usd, for exactly the fee.
- Without one, charge the flat fee to Stripe's test card and check the PaymentIntent.
"""

from __future__ import annotations

import asyncio

from shared.models import VerifyPaymentRequest, VerifyPaymentResult
from shared.payments import StripeKeyError, charge_test_fee, verify_charge, verify_checkout_session


async def verify_payment(request: VerifyPaymentRequest) -> VerifyPaymentResult:
    try:
        if request.transaction_id:
            matched, detail = await asyncio.to_thread(
                verify_checkout_session, request.transaction_id, request.service_fee_usd
            )
        else:
            intent = await asyncio.to_thread(
                charge_test_fee,
                request.service_fee_usd,
                job_id=request.job_id,
            )
            matched, detail = verify_charge(intent, request.service_fee_usd)
    except StripeKeyError as exc:
        return VerifyPaymentResult(
            job_id=request.job_id,
            ok=False,
            verified=False,
            detail=str(exc),
        )
    return VerifyPaymentResult(
        job_id=request.job_id,
        ok=True,
        verified=matched,
        detail=detail,
    )
