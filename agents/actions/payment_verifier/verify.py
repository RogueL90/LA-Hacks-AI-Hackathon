"""Charge the flat service fee in Stripe test mode and check the PaymentIntent."""

from __future__ import annotations

import asyncio

from shared.models import VerifyPaymentRequest, VerifyPaymentResult
from shared.payments import StripeKeyError, charge_test_fee, verify_charge


async def verify_payment(request: VerifyPaymentRequest) -> VerifyPaymentResult:
    try:
        intent = await asyncio.to_thread(
            charge_test_fee,
            request.service_fee_usd,
            job_id=request.job_id,
        )
    except StripeKeyError as exc:
        return VerifyPaymentResult(
            job_id=request.job_id,
            ok=False,
            verified=False,
            detail=str(exc),
        )
    matched, detail = verify_charge(intent, request.service_fee_usd)
    return VerifyPaymentResult(
        job_id=request.job_id,
        ok=matched,
        verified=matched,
        detail=detail,
    )
