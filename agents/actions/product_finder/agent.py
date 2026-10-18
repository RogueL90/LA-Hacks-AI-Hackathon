"""Product Finder agent. FindProductsRequest in, FindProductsResult out."""

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
from agents.actions.product_finder.chat import make_chat_protocol
from agents.actions.product_finder.search import ChaosFailure, find_products
from agents.actions.tracing import report_error, traced_agent
from shared.models import FindProductsRequest, FindProductsResult

load_env()
ensure_event_loop()

agent = make_action_agent(
    "product_finder",
    "Home Product Finder",
    (  # Agentverse allows 300 characters
        "Finds and checks real products for a shopper who names them, like \"two 27 inch monitors under $150\" or \"a baby gate for a 39 in stair\", and replies with verified links. For products to fix a home checked by Maestro, use Maestro: it builds the cart and checkout."
    ),
    Path(__file__).parent,
    port=8011,
)
protocol = Protocol(name="HomeProductSearch", version="0.1.0")


@protocol.on_message(FindProductsRequest, replies=FindProductsResult)
@traced_agent("product_finder", "find_products")
async def on_find(ctx: Context, sender: str, msg: FindProductsRequest) -> None:
    try:
        result = await find_products(msg)
    except ChaosFailure as exc:
        await report_error(
            ctx,
            msg.job_id,
            "product_finder",
            "find_products",
            exc,
            True,
            msg.model_dump(),
        )
        result = FindProductsResult(job_id=msg.job_id, ok=False, error=str(exc))
    except Exception as exc:
        await report_error(
            ctx,
            msg.job_id,
            "product_finder",
            "find_products",
            exc,
            True,
            msg.model_dump(),
        )
        result = FindProductsResult(job_id=msg.job_id, ok=False, error=str(exc))
    await ctx.send(sender, result)


agent.include(protocol, publish_manifest=True)
# Chat Protocol: ASI:One (and anyone on Agentverse) can ask the Product Finder directly.
agent.include(make_chat_protocol(), publish_manifest=True)

if __name__ == "__main__":
    agent.run()
