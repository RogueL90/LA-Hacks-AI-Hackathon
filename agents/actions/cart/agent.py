"""Cart agent. CartRequest in, CartResult out."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from uagents import Agent, Context

from agents.actions.cart.logic import build_cart
from agents.actions.envload import ensure_event_loop, load_env
from agents.actions.tracing import report_error, traced_agent
from shared.models import CartRequest, CartResult

load_env()
ensure_event_loop()

agent = Agent(
    name="lmh-cart",
    seed=os.getenv("CART_SEED", "lmh-cart-local-seed"),
    port=8012,
    mailbox=False,
)


@agent.on_message(CartRequest)
@traced_agent("cart", "build_cart")
async def on_cart(ctx: Context, sender: str, msg: CartRequest) -> None:
    try:
        result = build_cart(msg)
    except Exception as exc:
        await report_error(
            ctx,
            msg.job_id,
            "cart",
            "build_cart",
            exc,
            True,
            msg.model_dump(),
        )
        result = CartResult(job_id=msg.job_id, ok=False, error=str(exc))
    await ctx.send(sender, result)


if __name__ == "__main__":
    agent.run()
