"""Insurance Filer. ClaimRequest in, ClaimPackage out.

The package is ready to send. It is not filed with an insurer.
"""

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
from agents.actions.insurance_filer.package import build_claim_package
from agents.actions.tracing import report_error, traced_agent
from shared.models import ClaimPackage, ClaimRequest

load_env()
ensure_event_loop()

agent = make_action_agent(
    "insurance_filer",
    "Insurance Claim Filer",
    (
        "Turns a home contents inventory into a ready-to-send insurance claim package: xlsx and "
        "csv inventory with replacement costs and evidence frames, plus a cover letter PDF. Part "
        "of Maestro."
    ),
    Path(__file__).parent,
    port=8014,
)
protocol = Protocol(name="HomeClaimPackage", version="0.1.0")


@protocol.on_message(ClaimRequest, replies=ClaimPackage)
@traced_agent("insurance_filer", "build_package")
async def on_claim(ctx: Context, sender: str, msg: ClaimRequest) -> None:
    try:
        result = await build_claim_package(msg)
        if not result.ok and result.error and "upload" in result.error.lower():
            await report_error(
                ctx,
                msg.job_id,
                "insurance_filer",
                "build_package",
                RuntimeError(result.error),
                True,
                msg.model_dump(),
            )
    except Exception as exc:
        await report_error(
            ctx,
            msg.job_id,
            "insurance_filer",
            "build_package",
            exc,
            True,
            msg.model_dump(),
        )
        result = ClaimPackage(job_id=msg.job_id, ok=False, error=str(exc))
    await ctx.send(sender, result)


agent.include(protocol, publish_manifest=True)

if __name__ == "__main__":
    agent.run()
