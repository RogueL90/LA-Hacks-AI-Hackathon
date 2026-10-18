"""Payment Verifier. VerifyPaymentRequest in, VerifyPaymentResult out."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from uagents import Context, Protocol

from agents.actions.envload import ensure_event_loop, load_env
from agents.actions.service import make_action_agent
from agents.actions.payment_verifier.verify import verify_payment
from agents.actions.tracing import report_error, traced_agent
from shared.models import VerifyPaymentRequest, VerifyPaymentResult
from shared.payments import StripeKeyError

load_env()
ensure_event_loop()

agent = make_action_agent(
    "payment_verifier",
    "Stripe Payment Verifier",
    (
        "Confirms a Last Mile Home service fee was paid through Stripe (test mode only): checks "
        "the user's Checkout Session, or charges Stripe's test card. Never takes a real charge."
    ),
    Path(__file__).parent,
    port=8013,
)
protocol = Protocol(name="HomePaymentVerify", version="0.1.0")


@protocol.on_message(VerifyPaymentRequest, replies=VerifyPaymentResult)
@traced_agent("payment_verifier", "verify_payment")
async def on_verify(ctx: Context, sender: str, msg: VerifyPaymentRequest) -> None:
    try:
        result = await verify_payment(msg)
    except StripeKeyError as exc:
        result = VerifyPaymentResult(
            job_id=msg.job_id,
            ok=False,
            verified=False,
            detail=str(exc),
        )
    except Exception as exc:
        await report_error(
            ctx,
            msg.job_id,
            "payment_verifier",
            "verify_payment",
            exc,
            True,
            msg.model_dump(),
        )
        result = VerifyPaymentResult(
            job_id=msg.job_id,
            ok=False,
            verified=False,
            detail=str(exc),
        )
    await ctx.send(sender, result)


agent.include(protocol, publish_manifest=True)

if __name__ == "__main__":
    agent.run()
