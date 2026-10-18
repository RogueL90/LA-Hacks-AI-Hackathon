"""Product Finder agent. FindProductsRequest in, FindProductsResult out."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from uagents import Agent, Context

from agents.actions.envload import ensure_event_loop, load_env
from agents.actions.product_finder.search import ChaosFailure, find_products
from agents.actions.tracing import report_error, traced_agent
from shared.models import FindProductsRequest, FindProductsResult

load_env()
ensure_event_loop()

agent = Agent(
    name="lmh-product-finder",
    seed=os.getenv("PRODUCT_FINDER_SEED", "lmh-product-finder-local-seed"),
    port=8011,
    mailbox=False,
)


@agent.on_message(FindProductsRequest)
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


if __name__ == "__main__":
    agent.run()
