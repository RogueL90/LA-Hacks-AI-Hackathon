"""Last Mile Home Coordinator: the only agent ASI:One talks to.

Flow: video/photos -> Space Builder -> mode cards -> intake form -> specialist ->
findings + fix plan -> service fee via the Payment Protocol (Stripe, test mode).
Session state lives in ctx.storage, keyed by the ASI:One sender.
"""
import asyncio
import json
import re
import time
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
from agents.coordinator.understand import understand
from agents.specialists.baby.logic import analyze as baby_analyze
from agents.specialists.claim.logic import analyze as claim_analyze
from agents.specialists.elder.logic import analyze as elder_analyze
from agents.specialists.transformer.logic import analyze as transformer_analyze
from shared.chat import (
    attachments,
    card_message,
    clean_text,
    parse_selection,
    text_message,
    video_frame,
    video_frame_at,
)
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
    name="Last Mile Home",
    seed=config.seed("coordinator"),
    mailbox=True,
    handle_messages_concurrently=True,  # one slow user must not block the others
    publish_agent_details=True,
    readme_path=str(Path(__file__).with_name("README.md")),
    description=(
        "Last Mile Home: upload a short video or photos of a home and get a 3D model "
        "plus elder-safety, baby-proofing, space-transformation and insurance-claim help."
    ),
)

chat = Protocol(spec=chat_protocol_spec)
payments = Protocol(spec=payment_protocol_spec, role="seller")


def _key(ctx: Context, sender: str) -> str:
    # One ASI:One conversation = one session id, the same one ASI:One reports as agent_session_id.
    # The planner relays many users from a single sender address, so the sender alone isn't enough.
    return f"session:{ctx.session}" if ctx.session else f"sender:{sender}"


def load(ctx: Context, sender: str) -> dict:
    return ctx.storage.get(_key(ctx, sender)) or {}


def save(ctx: Context, sender: str, state: dict):
    ctx.storage.set(_key(ctx, sender), state)


async def send(ctx: Context, to: str, msg: ChatMessage):
    status = await ctx.send(to, msg)
    if status.status.value == "failed":
        ctx.logger.warning(f"reply to {to[:16]}… failed: {status.detail}")


@chat.on_message(ChatMessage)
async def on_chat(ctx: Context, sender: str, msg: ChatMessage):
    await ctx.send(sender, ChatAcknowledgement(timestamp=msg.timestamp, acknowledged_msg_id=msg.msg_id))
    # The planner marks every relayed message as a session start, so state is never wiped here;
    # a new conversation gets a new session id and therefore fresh state.
    starting = any(isinstance(c, StartSessionContent) for c in msg.content)
    state = load(ctx, sender)
    text = clean_text(msg)
    # The ASI:One planner repeats the video link in every relayed message, so only new uploads count.
    files = [f for f in attachments(msg) if f["url"] not in state.get("media", [])]
    selection = parse_selection(text)
    if not selection and text:
        selection = await understand(text, state.get("last_card"))
    ctx.logger.info(f"from={sender[:16]}… session={ctx.session} text={text[:200]!r} files={len(files)} selection={selection}")

    if starting and not state:
        # Tells ASI:One this agent accepts uploads, so the user can attach a video or photos.
        await ctx.send(sender, ChatMessage(
            timestamp=msg.timestamp, msg_id=uuid4(),
            content=[MetadataContent(type="metadata", metadata={"attachments": "true"})]))
    try:
        await route(ctx, sender, state, files, selection)
    except Exception:
        # Never leave the user without a reply: the planner would otherwise wait and give up.
        ctx.logger.exception(f"session={ctx.session} handler failed")
        await send(ctx, sender, text_message(
            "Sorry, something went wrong on my side while handling that. I've logged it; please try again."))
    save(ctx, sender, state)


ANSWER_KEYS = ["person", "age", "mobility_aid", "night_trips", "child_age_months", "goal", "room_id",
               "requirements", "style", "budget_usd", "policy_type", "zip_code"]
REQUIRED = {"elder": ["mobility_aid"], "baby": ["child_age_months"],
            "transform": ["goal", "room_id"], "claim": ["policy_type", "zip_code"]}
MODE_KEYS = {
    "elder": {"person", "age", "mobility_aid", "night_trips", "budget_usd"},
    "baby": {"child_age_months", "budget_usd"},
    "transform": {"goal", "room_id", "requirements", "style", "budget_usd"},
    "claim": {"policy_type", "zip_code"},
}


def child_months(text: str) -> int | None:
    number = _number(text, float)
    if number is None:
        return 0 if "newborn" in text.lower() else None
    return round(number * 12) if "year" in text.lower() else round(number)


def has_answers(state: dict, mode: str) -> bool:
    answers = state.get("answers", {})
    return mode in REQUIRED and all(answers.get(k) not in (None, "") for k in REQUIRED[mode])


async def route(ctx: Context, sender: str, state: dict, files: list[dict], selection: dict):
    merge_build(ctx, sender, state)
    action = selection.get("action")
    mode = selection.get("mode")
    if mode == "baby" and not selection.get("child_age_months") and selection.get("age"):
        # A child's age that landed in the adult "age" field: "18 months", "2 years", "1-year-old".
        months = child_months(str(selection["age"]))
        if months is not None:
            selection["child_age_months"] = months
    allowed = MODE_KEYS.get(mode, set(ANSWER_KEYS))
    answers = {k: v for k, v in selection.items() if k in ANSWER_KEYS and k in allowed}
    if answers:
        state.setdefault("answers", {}).update(answers)
    if selection.get("mode") in cards.MODES and action in ("choose_mode", "submit_intake"):
        state["wanted_mode"] = selection["mode"]

    if files:
        await on_media(ctx, sender, state, files, state.get("wanted_mode"))
    elif not state.get("job_id") and action != "check_payment":
        # Nothing to work on yet: remember what they asked for and ask for the home.
        wanted = cards.MODES.get(state.get("wanted_mode", ""), {}).get("title")
        if wanted or action != "other":
            lead = f"Happy to do the {wanted.lower()} check. " if wanted else ""
            await send(ctx, sender, text_message(
                f"{lead}Please attach a 30-second video or a few photos of the home "
                "(as a file, not a YouTube or web link) and I'll map it in 3D."))
        else:
            await send(ctx, sender, text_message(GREETING))
    elif action == "choose_mode" and has_answers(state, selection.get("mode", "")):
        # e.g. "actually, turn the bedroom into an office": everything needed is already known.
        await on_intake(ctx, sender, state, {"mode": selection["mode"]})
    elif action == "choose_mode":
        await on_choose_mode(ctx, sender, state, selection.get("mode", ""))
    elif action == "submit_intake":
        await on_intake(ctx, sender, state, selection)
    elif action == "finding_detail":
        await on_finding_detail(ctx, sender, state, selection.get("finding_id", ""))
    elif action == "approve_plan":
        if isinstance(selection.get("fix_ids"), list) and selection["fix_ids"]:
            state["chosen_fixes"] = selection["fix_ids"]
        await request_fee(ctx, sender, state)
    elif action == "payment_opened":
        await send(ctx, sender, text_message("Finish the checkout in the new tab, then tap I've paid."))
    elif action == "show_results" and state.get("result"):
        await show_results(ctx, sender, state, "Here are your results again.")
    elif action == "check_payment":
        await check_payment(ctx, sender, state)
    elif action == "decline_plan":
        await send(ctx, sender, text_message("No problem. Your results are saved; say \"approve\" whenever you're ready."))
    else:
        await show_modes(ctx, sender, state, "What would you like to do next?")


async def send_card(ctx: Context, to: str, state: dict, narration: str, kind: str, payload: dict):
    """Send an Interactive Card and remember it, so prose replies can be matched to it."""
    state["last_card"] = {"kind": kind, "payload": payload}
    await send(ctx, to, card_message(narration, kind, payload))


@chat.on_message(ChatAcknowledgement)
async def on_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    pass


BUILD_WAIT_S = 50  # ASI:One's planner waits about 60 s for a reply


def _build_key(ctx: Context, sender: str) -> str:
    return f"build:{_key(ctx, sender)}"


def home_intro(state: dict) -> str:
    intro = f"Your home is mapped: {len(state['rooms'])} rooms and {state.get('object_count', 0)} objects."
    if state.get("prebuilt"):
        intro += " (Live 3D building is still in progress, so this run uses our demo apartment's measurements.)"
    return intro


def merge_build(ctx: Context, sender: str, state: dict) -> bool:
    """Copy a finished background build into the conversation state. True once the home is ready."""
    if state.get("space_id"):
        return True
    build = ctx.storage.get(_build_key(ctx, sender)) or {}
    if build.get("status") != "done" or build.get("job_id") != state.get("job_id"):
        return False
    state.update({k: build[k] for k in ("space_id", "rooms", "prebuilt", "viewer_url", "object_count")})
    state["stats"] = (f"{len(state['rooms'])} rooms · {state['object_count']} objects"
                      + (" · demo measurements" if state["prebuilt"] else ""))
    return True


async def wait_for_home(ctx: Context, sender: str, state: dict, wait_s: float = BUILD_WAIT_S) -> bool:
    deadline = time.monotonic() + wait_s
    while not merge_build(ctx, sender, state):
        if not state.get("job_id") or time.monotonic() > deadline:
            return False
        await asyncio.sleep(0.5)
    return True


def start_build(ctx: Context, sender: str, state: dict, files: list[dict]):
    """Map the home in the background so the user can answer questions meanwhile."""
    job_id = str(uuid4())
    urls = [f["url"] for f in files]
    video = next((f["url"] for f in files if f["mime_type"].startswith("video")), None)
    photos = [f["url"] for f in files if not f["mime_type"].startswith("video")] or urls
    state.update({
        "job_id": job_id, "media": urls, "video": video,
        "frames": {m: video_frame(video, info["frame"]) if video else photos[i % len(photos)]
                   for i, (m, info) in enumerate(cards.MODES.items())},
        "space_id": None, "rooms": [], "stats": "Mapping your home in 3D…",
        "result": None, "payment": None, "deliver": None,
    })
    key = _build_key(ctx, sender)
    ctx.storage.set(key, {"status": "running", "job_id": job_id})

    async def build():
        reply, status = await ctx.send_and_receive(
            ADDRESSES["space_builder"], SpaceBuildRequest(job_id=job_id, media_urls=urls),
            response_type=SpaceBuildResult, timeout=180)
        if isinstance(reply, SpaceBuildResult) and reply.ok and reply.space:
            space = reply.space
        else:
            ctx.logger.warning(f"job={job_id} space build failed ({status.detail}); using the demo home")
            space = demo_space(snapshot_url=video_frame(urls[0]))
        ctx.storage.set(key, {
            "status": "done", "job_id": job_id, "space_id": space.space_id,
            "rooms": [{"value": r.id, "label": r.name} for r in space.rooms],
            "prebuilt": space.scale_method == "prebuilt", "viewer_url": space.viewer_url,
            "object_count": len(space.objects),
        })
        ctx.logger.info(f"job={job_id} home ready: {len(space.rooms)} rooms, {len(space.objects)} objects")
        # Answers arrived while the home was still being mapped: post the results now.
        later = load(ctx, sender)
        if later.get("job_id") == job_id and later.get("deliver"):
            selection = later.pop("deliver")
            merge_build(ctx, sender, later)
            try:
                await on_intake(ctx, sender, later, selection, home_intro(later))
            finally:
                save(ctx, sender, later)

    asyncio.get_running_loop().create_task(build())


async def on_media(ctx: Context, sender: str, state: dict, files: list[dict], mode: str | None = None):
    start_build(ctx, sender, state, files)
    if mode in cards.MODES and has_answers(state, mode):
        # They already told us everything this mode needs: wait for the home, then run it.
        await on_intake(ctx, sender, state, {"mode": mode})
    elif mode in cards.MODES:
        # Ask this mode's questions while the home is being mapped.
        await on_choose_mode(ctx, sender, state, mode, "Mapping your home in 3D now.")
    else:
        await show_modes(ctx, sender, state, "Mapping your home in 3D now. While that runs, what should we look at?")


async def show_modes(ctx: Context, sender: str, state: dict, narration: str):
    if not state.get("frames"):
        await send(ctx, sender, text_message(GREETING))
        return
    await send_card(ctx, sender, state, narration, "carousel", cards.space_ready(state["frames"], state.get("stats", "")))


async def on_choose_mode(ctx: Context, sender: str, state: dict, mode: str, intro: str = ""):
    if mode not in cards.MODES or not state.get("job_id"):
        await show_modes(ctx, sender, state, "Pick one of these to start.")
        return
    state["mode"] = mode
    narration = f"{intro} " if intro else ""
    narration += f"{cards.MODES[mode]['title']}: a few quick questions first."
    await send_card(ctx, sender, state, narration, "form", cards.intake_form(mode, state["rooms"]))


def _number(value, cast):
    if value in (None, "") or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return cast(value)
    match = re.search(r"\d[\d,]*(?:\.\d+)?", str(value))
    try:
        return cast(float(match.group(0).replace(",", ""))) if match else None
    except (TypeError, ValueError):
        return None


def resolve_room(state: dict, room: str | None) -> str | None:
    """Match "the bedroom", "Bedroom" or "bedroom" to a room id in this home."""
    if not room:
        return None
    wanted = room.lower().replace("the ", "").strip()
    for r in state.get("rooms", []):
        label = r["label"].lower()
        if wanted in (r["value"].lower(), label) or wanted in label or label in wanted:
            return r["value"]
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


async def on_intake(ctx: Context, sender: str, state: dict, selection: dict, intro: str = ""):
    mode = selection.get("mode") or state.get("mode")
    if mode not in cards.MODES or not state.get("job_id"):
        await show_modes(ctx, sender, state, "Pick what you'd like to do first.")
        return
    if not state.get("space_id"):
        if not await wait_for_home(ctx, sender, state):
            state["mode"] = mode
            state["deliver"] = {**selection, "mode": mode}
            await send(ctx, sender, text_message(
                "Still mapping your home in 3D; it's a big one. I'll post your results here as soon as it's done."))
            return
        intro = intro or home_intro(state)
    selection = {**state.get("answers", {}), **selection}
    if mode == "transform":
        room_id = resolve_room(state, selection.get("room_id"))
        if not room_id:
            asked = selection.get("room_id")
            names = ", ".join(r["label"] for r in state["rooms"])
            lead = f"I don't see a {asked} in this home. " if asked else ""
            state["mode"] = mode
            await send_card(ctx, sender, state, f"{intro} {lead}Which room should I transform? This home has: {names}.".strip(),
                            "form", cards.intake_form(mode, state["rooms"]))
            return
        selection["room_id"] = room_id
    profile = profile_from(selection)
    state["mode"] = mode
    state["profile"] = profile.model_dump()
    # One reply per message: ASI:One's planner treats the first text reply as the agent's whole answer.
    result = await run_mode(ctx, state, mode, profile)
    state["result"] = result.model_dump()
    if not result.findings:
        await send(ctx, sender, text_message(result.summary))
        return
    next_step = ("Next I'll price each item at today's replacement cost and build your claim package."
                 if mode == "claim" else "Pick the fixes you want and approve; I'll find products that fit.")
    view = f" [Open the 3D view]({result.viewer_url}) to see every finding pinned on your home." if result.viewer_url else ""
    await show_results(ctx, sender, state, f"{intro} {result.summary} {next_step}{view}".strip())


def evidence_image(state: dict, finding) -> str | None:
    """The moment in the user's own video where this finding was seen (public Cloudinary frame)."""
    seconds = next((e.timestamp_s for e in finding.evidence if e.timestamp_s is not None), None)
    video = state.get("video")
    return video_frame_at(video, seconds) if video and seconds is not None else None


async def show_results(ctx: Context, sender: str, state: dict, narration: str):
    result = ModeResult.model_validate(state["result"])
    fee = None if result.mode == "claim" else fee_label()
    hero = next((img for f in result.findings if (img := evidence_image(state, f))), None) or state["frames"][result.mode]
    await send_card(ctx, sender, state, narration, "custom", cards.results_card(result, hero, fee))


async def on_finding_detail(ctx: Context, sender: str, state: dict, finding_id: str):
    result = ModeResult.model_validate(state["result"]) if state.get("result") else None
    finding = next((f for f in result.findings if f.id == finding_id), None) if result else None
    if not finding and result and finding_id:
        # Prose like "the armchair hazard" can arrive as a made-up id: match on the words instead.
        words = {w for w in re.split(r"[^a-z]+", finding_id.lower()) if len(w) > 3} - {"hazard", "finding", "fall", "safety"}
        finding = max(result.findings, key=lambda f: len(words & set(re.split(r"[^a-z]+", f"{f.title} {f.id}".lower()))),
                      default=None)
        if finding and not words & set(re.split(r"[^a-z]+", f"{finding.title} {finding.id}".lower())):
            finding = None
    if not finding:
        await show_modes(ctx, sender, state, "I couldn't find that item. Pick a mode to start again.")
        return
    payload = cards.finding_detail(finding, evidence_image(state, finding) or state["frames"][result.mode])
    await send_card(ctx, sender, state, finding.title, "detail", payload)


def fee_label() -> str:
    return f"${stripe_pay.FEE_USD}"


async def request_fee(ctx: Context, sender: str, state: dict):
    result = state.get("result")
    if not result or result.get("mode") == "claim" or not result.get("findings"):
        await show_modes(ctx, sender, state, "There's no fix plan to approve yet. Pick a check to run first.")
        return
    if (state.get("payment") or {}).get("status") == "paid":
        await send(ctx, sender, text_message("You've already paid for this plan. Next I'll find products that fit."))
        return
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
        "checkout_url": checkout["hosted_url"],
    }
    # Plain ASI:One chat may not render embedded Stripe checkout, so the card's Pay button opens the hosted page.
    await send_card(ctx, sender, state,
                    f"Here's your secure checkout for the ${stripe_pay.FEE_USD} service fee: "
                    f"[pay with Stripe]({checkout['hosted_url']}). Then tap I've paid.",
                    "custom", cards.payment_card(fee_label(), checkout["hosted_url"]))


async def verify_paid(ctx: Context, state: dict, session_id: str) -> bool:
    """Ask Pranay's Payment Verifier; if it doesn't answer, check with Stripe directly.

    Only sessions this conversation created count, so a forged or reused id can't unlock anything.
    """
    if session_id not in (state.get("payment") or {}).get("stripe_sessions", []):
        ctx.logger.warning(f"PAYMENT rejected: {session_id} is not one of this conversation's checkout sessions")
        return False
    req = VerifyPaymentRequest(
        job_id=state.get("job_id") or "", transaction_id=session_id,
        expected_amount_usd=float(stripe_pay.FEE_USD))
    reply, status = await ctx.send_and_receive(
        ADDRESSES["payment_verifier"], req, response_type=VerifyPaymentResult, timeout=15)
    if isinstance(reply, VerifyPaymentResult) and reply.ok:
        return reply.verified
    ctx.logger.info(f"Payment Verifier unavailable ({status.detail}); checking Stripe directly")
    try:
        return await stripe_pay.is_paid(session_id, expected_usd=float(stripe_pay.FEE_USD))
    except Exception:
        ctx.logger.exception(f"Stripe lookup failed for {session_id}")
        return False


async def after_payment(ctx: Context, sender: str, state: dict, session_id: str):
    state["payment"] = {**state.get("payment", {}), "status": "paid", "session": session_id}
    await send_card(ctx, sender, state, f"Payment received: ${stripe_pay.FEE_USD}. Thank you!", "custom",
                    cards.receipt_card(f"${stripe_pay.FEE_USD}", session_id[-12:]))


async def check_payment(ctx: Context, sender: str, state: dict):
    payment = state.get("payment") or {}
    if not payment.get("stripe_sessions") and payment.get("status") != "paid":
        await send(ctx, sender, text_message(
            "There's nothing to pay yet. Once you approve a fix plan I'll send you a secure Stripe checkout."))
        return
    if payment.get("status") == "paid":
        await send(ctx, sender, text_message("You're all paid. Next I'll find products that fit."))
        return
    for session_id in payment.get("stripe_sessions", []):
        if await verify_paid(ctx, state, session_id):
            await after_payment(ctx, sender, state, session_id)
            return
    await send_card(ctx, sender, state, "I don't see the payment yet. Finish the Stripe checkout, then tap I've paid again.",
                    "custom", cards.payment_card(fee_label(), payment.get("checkout_url", "https://checkout.stripe.com")))


@payments.on_message(CommitPayment)
async def on_commit(ctx: Context, sender: str, msg: CommitPayment):
    ctx.logger.info(
        f"PAYMENT commit from={sender[:16]}… tx={msg.transaction_id} funds={msg.funds.amount} {msg.funds.currency} "
        f"method={msg.funds.payment_method}")
    state = load(ctx, sender)
    try:
        await settle_commit(ctx, sender, state, msg)
    except Exception:
        ctx.logger.exception("PAYMENT commit handling failed")
        await ctx.send(sender, CancelPayment(transaction_id=msg.transaction_id, reason="We couldn't verify this payment."))
    save(ctx, sender, state)


async def settle_commit(ctx: Context, sender: str, state: dict, msg: CommitPayment):
    if msg.funds.payment_method != "stripe" or not msg.transaction_id:
        await ctx.send(sender, CancelPayment(transaction_id=msg.transaction_id, reason="Only card payments via Stripe are accepted."))
        return
    if not await verify_paid(ctx, state, msg.transaction_id):
        await ctx.send(sender, CancelPayment(
            transaction_id=msg.transaction_id, reason="Stripe checkout isn't complete yet. Finish it, then pay again."))
        return
    await ctx.send(sender, CompletePayment(transaction_id=msg.transaction_id))
    await after_payment(ctx, sender, state, msg.transaction_id)


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
