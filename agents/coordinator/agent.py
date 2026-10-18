"""Last Mile Home Coordinator: the only agent ASI:One talks to.

Flow: video/photos -> Space Builder -> mode cards -> intake form -> specialist ->
findings + fix plan -> service fee via the Payment Protocol (Stripe, test mode).
Session state lives in ctx.storage, keyed by the ASI:One sender.
"""
import json
from pathlib import Path
from uuid import uuid4

from shared import config
from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    MetadataContent,
    StartSessionContent,
    chat_protocol_spec,
)
from uagents_core.contrib.protocols.payment import (
    CancelPayment,
    CommitPayment,
    CompletePayment,
    Funds,
    RejectPayment,
    RequestPayment,
    payment_protocol_spec,
)

from agents.coordinator import cards
from agents.specialists.baby.logic import analyze as baby_analyze
from agents.specialists.claim.logic import analyze as claim_analyze
from agents.specialists.elder.logic import analyze as elder_analyze
from agents.specialists.transformer.logic import analyze as transformer_analyze
from shared.chat import attachments, card_message, clean_text, parse_selection, text_message, video_frame
from shared.demo_space import demo_space
from shared.models import (
    ModeRequest,
    ModeResult,
    Profile,
    Space,
    SpaceBuildRequest,
    SpaceBuildResult,
    VerifyPaymentRequest,
    VerifyPaymentResult,
)
from shared import stripe_pay
from shared.space_client import get_space

ADDRESSES = json.loads((config.ROOT / "shared" / "addresses.json").read_text())
MODE_AGENT = {"elder": "elder", "baby": "baby", "transform": "transformer", "claim": "claim"}
LOCAL_ANALYZE = {"elder": elder_analyze, "baby": baby_analyze, "transform": transformer_analyze, "claim": claim_analyze}

GREETING = (
    "Hi, I'm Last Mile Home. Attach a 30-second video or a few photos of a home, and I'll map it in 3D. "
    "Then I can check it for elder safety or baby-proofing, plan a room makeover (for example a home office), "
    "or list everything for an insurance claim."
)

coordinator = Agent(
    name="lmh-coordinator",
    seed=config.seed("coordinator"),
    mailbox=True,
    publish_agent_details=True,
    readme_path=str(Path(__file__).with_name("README.md")),
    description=(
        "Last Mile Home: upload a short video or photos of a home and get a 3D model "
        "plus elder-safety, baby-proofing, space-transformation and insurance-claim help."
    ),
)

chat = Protocol(spec=chat_protocol_spec)
payments = Protocol(spec=payment_protocol_spec, role="seller")


def load(ctx: Context, sender: str) -> dict:
    return ctx.storage.get(sender) or {}


def save(ctx: Context, sender: str, state: dict):
    ctx.storage.set(sender, state)


async def send(ctx: Context, to: str, msg: ChatMessage):
    status = await ctx.send(to, msg)
    if status.status.value == "failed":
        ctx.logger.warning(f"reply to {to[:16]}… failed: {status.detail}")


@chat.on_message(ChatMessage)
async def on_chat(ctx: Context, sender: str, msg: ChatMessage):
    await ctx.send(sender, ChatAcknowledgement(timestamp=msg.timestamp, acknowledged_msg_id=msg.msg_id))
    files = attachments(msg)
    text = clean_text(msg)
    selection = parse_selection(text)
    action = selection.get("action")
    starting = any(isinstance(c, StartSessionContent) for c in msg.content)
    ctx.logger.info(f"from={sender[:16]}… text={text[:200]!r} files={len(files)} action={action}")

    state = {} if starting else load(ctx, sender)
    if starting:
        # Tells ASI:One this agent accepts uploads, so the user can attach a video or photos.
        await ctx.send(sender, ChatMessage(
            timestamp=msg.timestamp, msg_id=uuid4(),
            content=[MetadataContent(type="metadata", metadata={"attachments": "true"})]))
    if files:
        await on_media(ctx, sender, state, files)
    elif action == "choose_mode":
        await on_choose_mode(ctx, sender, state, selection.get("mode", ""))
    elif action == "submit_intake":
        await on_intake(ctx, sender, state, selection)
    elif action == "finding_detail":
        await on_finding_detail(ctx, sender, state, selection.get("finding_id", ""))
    elif action == "approve_plan" or text.lower() in {"pay", "approve"}:
        await request_fee(ctx, sender, state)
    elif action == "check_payment" or text.lower() in {"paid", "i've paid", "i paid", "done"}:
        await check_payment(ctx, sender, state)
    elif action == "decline_plan":
        await send(ctx, sender, text_message("No problem. Your results are saved; say \"approve\" whenever you're ready."))
    elif action == "show_modes" or state.get("space_id"):
        await show_modes(ctx, sender, state, "What would you like to do next?")
    else:
        await send(ctx, sender, text_message(GREETING))
    save(ctx, sender, state)


@chat.on_message(ChatAcknowledgement)
async def on_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    pass


async def on_media(ctx: Context, sender: str, state: dict, files: list[dict]):
    job_id = str(uuid4())
    urls = [f["url"] for f in files]
    await send(ctx, sender, text_message("Got it. Mapping your home in 3D now; this takes about a minute."))
    reply, status = await ctx.send_and_receive(
        ADDRESSES["space_builder"], SpaceBuildRequest(job_id=job_id, media_urls=urls),
        response_type=SpaceBuildResult, timeout=180,
    )
    space: Space
    if isinstance(reply, SpaceBuildResult) and reply.ok and reply.space:
        space = reply.space
    else:
        ctx.logger.warning(f"job={job_id} space build failed ({status.detail}); using the demo home")
        space = demo_space(snapshot_url=video_frame(urls[0]))
    video = next((f["url"] for f in files if f["mime_type"].startswith("video")), urls[0])
    state.update({
        "job_id": job_id,
        "media": urls,
        "space_id": space.space_id,
        "viewer_url": space.viewer_url,
        "prebuilt": space.scale_method == "prebuilt",
        "rooms": [{"value": r.id, "label": r.name} for r in space.rooms],
        "frames": {m: video_frame(video, info["frame"]) for m, info in cards.MODES.items()},
    })
    intro = f"Your home is mapped: {len(space.rooms)} rooms and {len(space.objects)} objects."
    if state["prebuilt"]:
        intro += " (Live 3D building is still in progress, so this run uses our demo apartment's measurements.)"
    await show_modes(ctx, sender, state, intro)


async def show_modes(ctx: Context, sender: str, state: dict, narration: str):
    if not state.get("frames"):
        await send(ctx, sender, text_message(GREETING))
        return
    await send(ctx, sender, card_message(narration, "carousel", cards.space_ready(state["frames"], state.get("viewer_url"))))


async def on_choose_mode(ctx: Context, sender: str, state: dict, mode: str):
    if mode not in cards.MODES or not state.get("space_id"):
        await show_modes(ctx, sender, state, "Pick one of these to start.")
        return
    state["mode"] = mode
    await send(ctx, sender, card_message(
        f"{cards.MODES[mode]['title']}: a few quick questions first.", "form", cards.intake_form(mode, state["rooms"])))


def _number(value, cast):
    try:
        return cast(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def profile_from(selection: dict) -> Profile:
    aid = selection.get("mobility_aid")
    return Profile(
        person=selection.get("person") or None,
        age=_number(selection.get("age"), int),
        mobility_aid=None if aid in (None, "", "none") else aid,
        night_trips=selection.get("night_trips") in (True, "true", "on", "yes"),
        child_age_months=_number(selection.get("child_age_months"), int),
        goal=selection.get("goal") or None,
        room_id=selection.get("room_id") or None,
        requirements=selection.get("requirements") or None,
        style=selection.get("style") or None,
        budget_usd=_number(selection.get("budget_usd"), float),
        policy_type=selection.get("policy_type") or None,
        zip_code=selection.get("zip_code") or None,
    )


async def run_mode(ctx: Context, state: dict, mode: str, profile: Profile) -> ModeResult:
    """Ask the specialist agent; if it fails, run the same checks here so the user still gets results."""
    req = ModeRequest(job_id=state["job_id"], mode=mode, space_id=state["space_id"], profile=profile)
    reply, status = await ctx.send_and_receive(
        ADDRESSES[MODE_AGENT[mode]], req, response_type=ModeResult, timeout=90)
    if isinstance(reply, ModeResult) and reply.ok:
        return reply
    ctx.logger.warning(f"job={req.job_id} {mode} agent failed ({getattr(reply, 'error', None) or status.detail}); running locally")
    space = await get_space(state["space_id"])
    summary, findings, _ = LOCAL_ANALYZE[mode](space, profile)
    return ModeResult(job_id=req.job_id, mode=mode, ok=True, summary=summary, findings=findings)


async def on_intake(ctx: Context, sender: str, state: dict, selection: dict):
    mode = selection.get("mode") or state.get("mode")
    if mode not in cards.MODES or not state.get("space_id"):
        await show_modes(ctx, sender, state, "Pick what you'd like to do first.")
        return
    profile = profile_from(selection)
    state["mode"] = mode
    state["profile"] = profile.model_dump()
    await send(ctx, sender, text_message(f"Running the {cards.MODES[mode]['title'].lower()} check..."))
    result = await run_mode(ctx, state, mode, profile)
    state["result"] = result.model_dump()
    fallback_image = state["frames"][mode]
    if not result.findings:
        await send(ctx, sender, text_message(result.summary))
        return
    await send(ctx, sender, card_message(result.summary, "carousel", cards.findings_carousel(result, fallback_image)))
    if mode == "claim":
        await send(ctx, sender, text_message(
            "Next I'll price each item at today's replacement cost and build your claim package."))
    else:
        await send(ctx, sender, card_message(
            "Here's the fix plan. Approve it and I'll find products that fit and prepare checkout links.",
            "review", cards.fix_plan_review(result, fee_label())))


async def on_finding_detail(ctx: Context, sender: str, state: dict, finding_id: str):
    result = ModeResult.model_validate(state["result"]) if state.get("result") else None
    finding = next((f for f in result.findings if f.id == finding_id), None) if result else None
    if not finding:
        await show_modes(ctx, sender, state, "I couldn't find that item. Pick a mode to start again.")
        return
    rows = [{"label": m.name.replace("_", " ").capitalize(),
             "value": f"{m.value:g} {m.unit}" + (f" (needs {m.required:g} {m.unit})" if m.required is not None else "")}
            for m in finding.measurements]
    if finding.fix_summary:
        rows.append({"label": "Fix", "value": finding.fix_summary})
    if finding.kind == "hazard":
        rows.append({"label": "Severity", "value": f"{finding.severity} of 5"})
    payload = {
        "title": finding.title,
        "hero_image": state["frames"][result.mode],
        "summary_rows": rows or [{"label": "Note", "value": finding.title}],
        "ctas": [
            {"label": "Approve fix plan", "primary": True, "selection": {"action": "approve_plan"}},
            {"label": "Back to modes", "selection": {"action": "show_modes"}},
        ],
    }
    await send(ctx, sender, card_message(finding.title, "detail", payload))


def fee_label() -> str:
    return f"${stripe_pay.FEE_USD} by card (Stripe test mode)"


async def request_fee(ctx: Context, sender: str, state: dict):
    if not stripe_pay.enabled():
        ctx.logger.error("Stripe test keys are missing; cannot request the service fee")
        await send(ctx, sender, text_message(
            "Payments aren't switched on yet, so I can't take the service fee right now. Your results are saved."))
        return
    reference = state.get("job_id") or str(uuid4())
    try:
        checkout = await stripe_pay.create_checkout(reference, "Products that fit your measured space, with checkout links")
    except Exception:
        ctx.logger.exception("Stripe checkout failed")
        await send(ctx, sender, text_message("I couldn't reach the payment provider. Please say \"approve\" again in a moment."))
        return
    # Send RequestPayment before anything slow (or any LLM call) so ASI:One renders the payment card.
    await ctx.send(sender, RequestPayment(
        accepted_funds=[Funds(currency="USD", amount=stripe_pay.FEE_USD, payment_method="stripe")],
        recipient=str(coordinator.address),
        deadline_seconds=1800,
        reference=reference,
        description=f"Last Mile Home service fee: {fee_label()}",
        metadata={
            "stripe": checkout["embedded"],
            "service": "last_mile_home",
            "content": "Pay the service fee to get products that fit and checkout links.",
        },
    ))
    state["payment"] = {
        "status": "requested",
        "reference": reference,
        "stripe_sessions": [checkout["embedded_id"], checkout["hosted_id"]],
    }
    # Plain ASI:One chat may not render embedded Stripe checkout, so also offer the hosted page.
    await send(ctx, sender, card_message(
        f"To pay ${stripe_pay.FEE_USD}, [open the secure Stripe checkout]({checkout['hosted_url']}) "
        "(test mode: card 4242 4242 4242 4242, any future date, any CVC), then tap **I've paid**.",
        "review", cards.payment_check(fee_label())))


async def verify_paid(ctx: Context, state: dict, session_id: str) -> bool:
    """Ask Pranay's Payment Verifier; if it doesn't answer, check with Stripe directly."""
    req = VerifyPaymentRequest(
        job_id=state.get("job_id") or "", transaction_id=session_id,
        expected_amount_usd=float(stripe_pay.FEE_USD))
    reply, status = await ctx.send_and_receive(
        ADDRESSES["payment_verifier"], req, response_type=VerifyPaymentResult, timeout=15)
    if isinstance(reply, VerifyPaymentResult) and reply.ok:
        return reply.verified
    ctx.logger.info(f"Payment Verifier unavailable ({status.detail}); checking Stripe directly")
    try:
        return await stripe_pay.is_paid(session_id)
    except Exception:
        ctx.logger.exception(f"Stripe lookup failed for {session_id}")
        return False


async def after_payment(ctx: Context, sender: str, state: dict, session_id: str):
    state["payment"] = {**state.get("payment", {}), "status": "paid", "session": session_id}
    await send(ctx, sender, text_message(
        f"Payment received: ${stripe_pay.FEE_USD} by card (Stripe test mode). "
        "Next I'll find products that fit and prepare checkout links."))


async def check_payment(ctx: Context, sender: str, state: dict):
    payment = state.get("payment") or {}
    if payment.get("status") == "paid":
        await send(ctx, sender, text_message("You're all paid. Next I'll find products that fit."))
        return
    for session_id in payment.get("stripe_sessions", []):
        if await verify_paid(ctx, state, session_id):
            await after_payment(ctx, sender, state, session_id)
            return
    await send(ctx, sender, card_message(
        "I don't see the payment yet. Finish the Stripe checkout, then tap I've paid again.",
        "review", cards.payment_check(fee_label())))


@payments.on_message(CommitPayment)
async def on_commit(ctx: Context, sender: str, msg: CommitPayment):
    ctx.logger.info(
        f"PAYMENT commit from={sender[:16]}… tx={msg.transaction_id} funds={msg.funds.amount} {msg.funds.currency} "
        f"method={msg.funds.payment_method}")
    state = load(ctx, sender)
    if msg.funds.payment_method != "stripe" or not msg.transaction_id:
        await ctx.send(sender, CancelPayment(transaction_id=msg.transaction_id, reason="Only card payments via Stripe are accepted."))
        return
    if not await verify_paid(ctx, state, msg.transaction_id):
        await ctx.send(sender, CancelPayment(
            transaction_id=msg.transaction_id, reason="Stripe checkout isn't complete yet. Finish it, then pay again."))
        return
    await ctx.send(sender, CompletePayment(transaction_id=msg.transaction_id))
    await after_payment(ctx, sender, state, msg.transaction_id)
    save(ctx, sender, state)


@payments.on_message(RejectPayment)
async def on_reject(ctx: Context, sender: str, msg: RejectPayment):
    ctx.logger.info(f"PAYMENT rejected by {sender[:16]}…: {msg.reason}")
    state = load(ctx, sender)
    state["payment"] = {"status": "rejected"}
    save(ctx, sender, state)
    await send(ctx, sender, text_message("No problem, the payment was cancelled. Say \"approve\" when you're ready."))


coordinator.include(chat, publish_manifest=True)
coordinator.include(payments, publish_manifest=True)

if __name__ == "__main__":
    coordinator.run()
