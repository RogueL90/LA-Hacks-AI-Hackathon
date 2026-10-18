"""Last Mile Home Space Builder: wraps Aditya's Space Service (video/photos -> 3D Space).

Falls back to the prebuilt demo home when the service is not configured or fails, and
says so via scale_method="prebuilt" so the coordinator can label it.
"""
from pathlib import Path

from uagents import Agent, Context, Protocol

from shared import config
from shared.chat import video_frame
from shared.demo_space import demo_space
from shared.models import SpaceBuildRequest, SpaceBuildResult
from shared.space_client import SPACE_SERVICE_URL, build_space

agent = Agent(
    name="Home 3D Space Builder",
    seed=config.seed("space_builder"),
    mailbox=True,
    handle_messages_concurrently=True,  # one slow user must not block the others
    publish_agent_details=True,
    readme_path=str(Path(__file__).with_name("README.md")),
    description="Last Mile Home Space Builder: turns a short home video or photos into a 3D model where every object has a real type, size and position.",
)
protocol = Protocol(name="HomeSpaceBuild", version="0.1.0")


@protocol.on_message(SpaceBuildRequest, replies=SpaceBuildResult)
async def handle(ctx: Context, sender: str, req: SpaceBuildRequest):
    ctx.logger.info(f"job={req.job_id} building from {len(req.media_urls)} file(s)")
    snapshot = video_frame(req.media_urls[0], percent=10) if req.media_urls else ""
    if SPACE_SERVICE_URL:
        try:
            space = await build_space(req.media_urls, req.job_id)
            await ctx.send(sender, SpaceBuildResult(job_id=req.job_id, ok=True, space=space))
            return
        except Exception:
            ctx.logger.exception(f"job={req.job_id} Space Service failed; using the prebuilt demo home")
    await ctx.send(sender, SpaceBuildResult(job_id=req.job_id, ok=True, space=demo_space(snapshot_url=snapshot)))


agent.include(protocol, publish_manifest=True)

if __name__ == "__main__":
    agent.run()
