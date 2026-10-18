"""Payment Verifier. VerifyPaymentRequest in, VerifyPaymentResult out."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from uagents import Agent, Context

from agents.actions.envload import ensure_event_loop, load_env
from agents.actions.payment_verifier.verify import verify_payment
from agents.actions.tracing import report_error, traced_agent
from shared.models import VerifyPaymentRequest, VerifyPaymentResult
from shared.payments import StripeKeyError

load_env()
ensure_event_loop()

agent = Agent(
    name="lmh-payment-verifier",
    seed=os.getenv("PAYMENT_VERIFIER_SEED", "lmh-payment-verifier-local-seed"),
    port=8013,
    mailbox=False,
)


@agent.on_message(VerifyPaymentRequest)
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


if __name__ == "__main__":
    agent.run()
