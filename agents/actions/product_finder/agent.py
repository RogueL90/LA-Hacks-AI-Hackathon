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
from agents.actions.product_finder.search import ChaosFailure, find_products
from agents.actions.tracing import report_error, traced_agent
from shared.models import FindProductsRequest, FindProductsResult

load_env()
ensure_event_loop()

agent = make_action_agent(
    "product_finder",
    "Home Product Finder",
    (
        "Finds real products for a home fix plan (grab bars, baby gates, a desk that fits a "
        "measured wall) with verified store pages, prices and a backup pick. Part of Last Mile "
        "Home."
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

if __name__ == "__main__":
    agent.run()
