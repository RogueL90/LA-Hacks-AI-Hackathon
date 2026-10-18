"""End-to-end smoke test: a fake ASI:One user drives the coordinator through one mode and the payment.

Runs every agent in one Bureau on a spare port, so nothing leaves the process except
Almanac/mailbox registration. Run: .venv/bin/python -m scripts.smoke_test [mode]
"""
import json
import secrets
import sys
from datetime import datetime, timezone
from uuid import uuid4

from shared import config
from uagents import Agent, Bureau, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    MetadataContent,
    Resource,
    ResourceContent,
    StartSessionContent,
    TextContent,
    chat_protocol_spec,
)
from uagents_core.contrib.protocols.payment import (
    CancelPayment,
    CommitPayment,
    CompletePayment,
    RequestPayment,
    payment_protocol_spec,
)

import run.bureau as live

MODE = sys.argv[1] if len(sys.argv) > 1 else "elder"
VIDEO = "https://res.cloudinary.com/fetch-ai/video/upload/v1792289759/chat-images/ttxwol79hg5looafhcif.mov"
INTAKE = {
    "elder": {"person": "Mom", "age": "78", "mobility_aid": "walker", "night_trips": True, "budget_usd": "300"},
    "baby": {"child_age_months": "14", "budget_usd": "200"},
    "transform": {"goal": "home office", "room_id": "bedroom", "requirements": "two monitors", "style": "warm modern", "budget_usd": "800"},
    "claim": {"policy_type": "replacement_cost", "zip_code": "90024"},
}

user = Agent(name="smoke-user", seed=f"lmh-smoke-{secrets.token_hex(8)}")
chat = Protocol(spec=chat_protocol_spec)
pay = Protocol(spec=payment_protocol_spec, role="buyer")
COORD = live.coordinator.address
seen = []


def say(text: str) -> ChatMessage:
    return ChatMessage(timestamp=datetime.now(timezone.utc), msg_id=uuid4(),
                       content=[TextContent(type="text", text=f"@{COORD} {text}")])


@user.on_event("startup")
async def start(ctx: Context):
    await ctx.send(COORD, ChatMessage(
        timestamp=datetime.now(timezone.utc), msg_id=uuid4(),
        content=[
            StartSessionContent(type="start-session"),
            TextContent(type="text", text=f"@{COORD} here is my mom's place"),
            ResourceContent(resource_id=uuid4(), resource=Resource(
                uri=VIDEO, metadata={"mime_type": "video/quicktime", "description": "home.mov"})),
        ]))


@chat.on_message(ChatMessage)
async def on_chat(ctx: Context, sender: str, msg: ChatMessage):
    await ctx.send(sender, ChatAcknowledgement(timestamp=datetime.now(timezone.utc), acknowledged_msg_id=msg.msg_id))
    for c in msg.content:
        if isinstance(c, TextContent):
            print(f"  AGENT: {c.text[:220]}")
            if "aren't switched on" in c.text:
                print(f"SMOKE TEST PASSED ({MODE}): cards seen {seen}; Stripe keys not set, so no payment request")
        elif isinstance(c, MetadataContent) and "card_kind" in c.metadata:
            kind = c.metadata["card_kind"]
            payload = json.loads(c.metadata["card_payload"])
            print(f"  CARD [{kind}] {payload.get('title')} ({len(json.dumps(payload))} bytes)")
            seen.append(kind)
            if kind == "carousel" and "choose_mode" in json.dumps(payload):
                await ctx.send(COORD, say(json.dumps({"action": "choose_mode", "mode": MODE})))
            elif kind == "carousel":
                for item in payload["items"]:
                    print(f"     - {item['title']} | {item['subtitle']}")
            elif kind == "form":
                await ctx.send(COORD, say(json.dumps({**INTAKE[MODE], "action": "submit_intake", "mode": MODE})))
            elif kind == "review":
                await ctx.send(COORD, say(json.dumps(payload["approve_cta"]["selection"])))
            elif kind == "custom":
                root = payload["root"]
                items = next((c["items"] for c in root["children"] if c["type"] == "list"), [])
                for item in items:
                    print("     - " + " | ".join(c.get("value", c.get("label", "")) for c in item["children"]))
                buttons = [b for c in root["children"] if c["type"] == "group" for b in c["children"]]
                approve = next((b for b in buttons if b["action"]["selection"].get("action") == "approve_plan"), None)
                if approve:
                    await ctx.send(COORD, say(json.dumps(approve["action"]["selection"])))
                else:
                    print(f"SMOKE TEST PASSED ({MODE}): cards seen {seen}; no payment step for this mode")
        elif isinstance(c, MetadataContent):
            print(f"  META {c.metadata}")


@chat.on_message(ChatAcknowledgement)
async def on_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    pass


@pay.on_message(RequestPayment)
async def on_request(ctx: Context, sender: str, msg: RequestPayment):
    f = msg.accepted_funds[0]
    stripe = (msg.metadata or {}).get("stripe", {})
    print(f"  PAYMENT REQUEST {f.amount} {f.currency} via {f.payment_method}; "
          f"embedded checkout ready: {bool(stripe.get('client_secret'))}")
    # A test card can't be paid without a browser, so commit an unpaid session: the agent must cancel it.
    await ctx.send(sender, CommitPayment(funds=f, recipient=msg.recipient,
                                         transaction_id=stripe.get("checkout_session_id", "none"),
                                         reference=msg.reference))


@pay.on_message(CompletePayment)
async def on_complete(ctx: Context, sender: str, msg: CompletePayment):
    print(f"  PAYMENT COMPLETE tx={msg.transaction_id}\nSMOKE TEST PASSED ({MODE}): cards seen {seen}")


@pay.on_message(CancelPayment)
async def on_cancel(ctx: Context, sender: str, msg: CancelPayment):
    print(f"  PAYMENT CANCELLED (expected for an unpaid session): {msg.reason}")
    print(f"SMOKE TEST PASSED ({MODE}): cards seen {seen}; unpaid checkout correctly refused")


user.include(chat)
user.include(pay)

bureau = Bureau(port=8291)
for a in live.AGENTS + [user]:
    bureau.add(a)

if __name__ == "__main__":
    bureau.run()
