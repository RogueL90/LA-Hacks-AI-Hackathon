"""Shared shell for the four specialist agents: ModeRequest in, ModeResult out.

Each specialist supplies an `analyze(space, profile) -> (summary, findings, overlays)`
function; this module handles loading the Space, storing overlays and error replies.
"""
from collections.abc import Callable
from pathlib import Path

from uagents import Agent, Context, Protocol

from shared import config
from shared.models import Finding, ModeRequest, ModeResult, Overlay, Profile, Space
from shared.space_client import get_space, post_overlays

Analyze = Callable[[Space, Profile], tuple[str, list[Finding], list[Overlay]]]


def make_specialist(key: str, name: str, mode: str, description: str, analyze: Analyze, folder: Path) -> Agent:
    agent = Agent(
        name=name,
        seed=config.seed(key),
        mailbox=True,
        publish_agent_details=True,
        readme_path=str(folder / "README.md"),
        description=description,
    )
    protocol = Protocol(name="HomeModeAnalysis", version="0.1.0")

    @protocol.on_message(ModeRequest, replies=ModeResult)
    async def handle(ctx: Context, sender: str, req: ModeRequest):
        ctx.logger.info(f"job={req.job_id} mode={req.mode} space={req.space_id}")
        try:
            space = await get_space(req.space_id)
            summary, findings, overlays = analyze(space, req.profile)
            stored = await post_overlays(space.space_id, mode, overlays)
            result = ModeResult(
                job_id=req.job_id,
                mode=mode,
                ok=True,
                summary=summary,
                findings=findings,
                overlay_set_id=stored.get("overlay_set_id"),
                viewer_url=stored.get("viewer_url"),
                snapshot_url=stored.get("snapshot_url"),
            )
        except Exception as exc:
            ctx.logger.exception(f"job={req.job_id} analysis failed")
            result = ModeResult(job_id=req.job_id, mode=mode, ok=False, summary="", error=str(exc))
        await ctx.send(sender, result)

    agent.include(protocol, publish_manifest=True)
    return agent
