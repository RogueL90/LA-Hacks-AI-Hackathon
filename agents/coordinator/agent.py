"""Last Mile Home Coordinator (connection stub).

Proves the Agentverse + ASI:One connection: replies to chat messages and logs
every content type that arrives, so we can see what ASI:One sends when a user
attaches a photo or video.
"""
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from shared import config
from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    ResourceContent,
    TextContent,
    chat_protocol_spec,
)

coordinator = Agent(
    name="lmh-coordinator",
    seed=config.seed("coordinator"),
    port=config.port("coordinator", 8200),
    mailbox=True,
    publish_agent_details=True,
    readme_path=str(Path(__file__).with_name("README.md")),
    description=(
        "Last Mile Home: upload a short video or photos of a home and get a 3D model "
        "plus elder-safety, baby-proofing, interior-design and insurance-claim help."
    ),
)

chat = Protocol(spec=chat_protocol_spec)


@chat.on_message(ChatMessage)
async def on_chat(ctx: Context, sender: str, msg: ChatMessage):
    await ctx.send(
        sender,
        ChatAcknowledgement(timestamp=datetime.now(timezone.utc), acknowledged_msg_id=msg.msg_id),
    )

    seen = []
    for item in msg.content:
        if isinstance(item, ResourceContent):
            resources = item.resource if isinstance(item.resource, list) else [item.resource]
            for r in resources:
                ctx.logger.info(f"ATTACHMENT uri={r.uri} metadata={r.metadata}")
                seen.append(f"attachment ({r.metadata.get('mime_type', 'unknown type')})")
        else:
            ctx.logger.info(f"CONTENT type={item.type} data={item.model_dump()}")
            seen.append(item.type)

    text = msg.text().strip()
    reply = (
        "Hi, I'm the Last Mile Home coordinator. I'm connected and still being built. "
        f"I received: {', '.join(seen) or 'nothing'}."
    )
    if text:
        reply += f' You said: "{text}"'
    status = await ctx.send(
        sender,
        ChatMessage(
            timestamp=datetime.now(timezone.utc),
            msg_id=uuid4(),
            content=[TextContent(type="text", text=reply)],
        ),
    )
    ctx.logger.info(f"REPLY to={sender[:16]}… status={status.status} detail={status.detail}")


@chat.on_message(ChatAcknowledgement)
async def on_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    ctx.logger.info(f"ACK from={sender[:16]}… for={msg.acknowledged_msg_id}")


coordinator.include(chat, publish_manifest=True)

if __name__ == "__main__":
    coordinator.run()
