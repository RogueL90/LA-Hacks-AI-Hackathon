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

from agents.coordinator import cards, summary
from agents.coordinator.understand import fill_missing, fix_mode, understand
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
from agents.actions.cart.logic import build_cart
from agents.actions.insurance_filer.package import build_claim_package as local_build_claim_package
from agents.actions.product_finder.search import find_products as local_find_products
from shared.models import (
    CartRequest,
    CartResult,
    ClaimPackage,
    ClaimRequest,
    FindProductsRequest,
    FindProductsResult,
    Finding,
    ModeRequest,
    ModeResult,
    ProductQuery,
    Profile,
    Space,
    SpaceBuildRequest,
    SpaceBuildResult,
    VerifyPaymentRequest,
    VerifyPaymentResult,
)
from shared import stripe_pay, uagents_patch
from shared.payments import FLAT_SERVICE_FEE_USD, format_service_fee_usd
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
    description=(  # Agentverse allows 300 characters
        "Send a home video: get a 3D model and elder-safety, baby-proofing, room makeover or insurance help. "
        "Then it shops for you: furniture, safety gear and electronics like monitors that fit the space, in "
        "one cart within budget, checked out with Stripe. No other agent needed."
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


FLAG_UPLOADS: dict = {}  # session -> the next reply should also say "this agent accepts uploads"


SEND_ATTEMPTS = 3
RETRY_WITHIN_S = 45  # ASI:One's planner stops waiting for a reply after about 60 s


async def send(ctx: Context, to: str, msg):
    """Send a reply (chat message or payment message), retrying a failed delivery.

    Live: while Agentverse was slow, an address lookup failed and raised, and a send hit the time cap.
    A failure that never left (a lookup error, a refused or failed request) is sent again, the same
    message with the same msg_id. A send stopped at the time cap is not: that results card still
    arrived, and resending would have shown it twice.
    """
    if isinstance(msg, ChatMessage) and FLAG_UPLOADS.pop(ctx.session, False):
        msg = ChatMessage(timestamp=msg.timestamp, msg_id=msg.msg_id,
                          content=[*msg.content, MetadataContent(type="metadata", metadata={"attachments": "true"})])
    t0 = time.monotonic()
    for attempt in range(1, SEND_ATTEMPTS + 1):
        try:
            status = await ctx.send(to, msg)
            failed, detail = status.status.value == "failed", status.detail
        except Exception as exc:  # e.g. the Almanac lookup timed out and the fallback resolver raised
            failed, detail = True, f"{type(exc).__name__}: {exc}"
        took = time.monotonic() - t0
        if not failed:
            if attempt > 1:
                ctx.logger.warning(f"reply to {to[:16]}… delivered on attempt {attempt} after {took:.1f} s")
            elif took > 3:
                ctx.logger.warning(f"reply to {to[:16]}… took {took:.1f} s to deliver")
            return
        last = attempt == SEND_ATTEMPTS or took > RETRY_WITHIN_S or uagents_patch.timed_out(detail)
        ctx.logger.warning(f"reply to {to[:16]}… failed (attempt {attempt}) after {took:.1f} s: {detail}"
                           + ("; not resending" if last else "; retrying"))
        if last:
            return
        await asyncio.sleep(1)


@chat.on_message(ChatMessage)
async def on_chat(ctx: Context, sender: str, msg: ChatMessage):
    t_ack = time.monotonic()
    await ctx.send(sender, ChatAcknowledgement(timestamp=msg.timestamp, acknowledged_msg_id=msg.msg_id))
    if time.monotonic() - t_ack > 3:
        ctx.logger.warning(f"acknowledgement to {sender[:16]}… took {time.monotonic() - t_ack:.1f} s")
    # The planner marks every relayed message as a session start, so state is never wiped here;
    # a new conversation gets a new session id and therefore fresh state.
    t_in = time.monotonic()
    starting = any(isinstance(c, StartSessionContent) for c in msg.content)
    state = load(ctx, sender)
    text = clean_text(msg)
    # The ASI:One planner repeats the video link in every relayed message, so only new uploads count.
    files = [f for f in attachments(msg) if f["url"] not in state.get("media", [])]
    selection = parse_selection(text)
    if not selection and text:
        selection = fix_mode(text, fill_missing(text, await understand(text, state.get("last_card"))))
    ctx.logger.info(f"{_now()} from={sender[:16]}… session={ctx.session} text={text[:200]!r} files={len(files)} "
                    f"selection={selection} (understood in {time.monotonic() - t_in:.1f} s)")

    # Tells ASI:One this agent accepts uploads. It rides on the first reply instead of being its own
    # message: ASI:One takes several seconds to accept each chat message, and a separate one ahead of
    # the reply doubled the first answer's wait (30 s seen live).
    FLAG_UPLOADS[ctx.session] = starting and not state
    try:
        await route(ctx, sender, state, files, selection, text)
    except Exception:
        # Never leave the user without a reply: the planner would otherwise wait and give up.
        ctx.logger.exception(f"session={ctx.session} handler failed")
        await send(ctx, sender, text_message(
            "Sorry, something went wrong on my side while handling that. I've logged it; please try again."))
    save(ctx, sender, state)
    ctx.logger.info(f"{_now()} session={ctx.session} handled in {time.monotonic() - t_in:.1f} s")


def _now() -> str:
    return time.strftime("%H:%M:%S")


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


MENTIONS_MEDIA = re.compile(r"\b(video|photos?|pictures?|footage|clip|upload(ed)?|attach(ed|ment)?)\b", re.I)


def has_answers(state: dict, mode: str) -> bool:
    answers = state.get("answers", {})
    return mode in REQUIRED and all(answers.get(k) not in (None, "") for k in REQUIRED[mode])


SHOP_WORDS = re.compile(r"\b(products?|buy|shop(ping)?|cart|recommend\w*|purchase|prices?|order|proceed|approve\w*|"
                        r"go ahead|links?|checkout|pay)\b", re.I)


def repeats_answers(state: dict, selection: dict) -> bool:
    """The planner restates earlier answers in every relayed message. Same mode as the shown results
    and nothing new in the answers means this isn't a new intake."""
    result = state.get("result") or {}
    mode = selection.get("mode")
    if not result or mode != result.get("mode"):
        return False
    known = state.get("answers", {})
    given = {k: v for k, v in selection.items() if k in MODE_KEYS.get(mode, set())}
    return all(str(known.get(k, "")).strip().lower() == str(v).strip().lower() for k, v in given.items())


async def route(ctx: Context, sender: str, state: dict, files: list[dict], selection: dict, text: str = ""):
    merge_build(ctx, sender, state)
    shown = (state.get("result") or {}).get("mode")
    if selection.get("action") == "approve_plan" and selection.get("mode") in cards.MODES and shown \
            and selection["mode"] != shown:
        # "And list everything for insurance" on baby results: a switch to the claim, not approving baby fixes.
        selection = {**selection, "action": "choose_mode"}
        ctx.logger.info(f"approve for {selection['mode']} while {shown} results are shown -> choose_mode")
    child = selection.get("child_age_months")
    if child not in (None, "") and shown and shown != "baby" and selection.get("mode") == shown \
            and str((state.get("answers") or {}).get("child_age_months", "")) != str(child):
        # Live: "now check the same house for my 1 year old too" became "do BOTH checks" with mode=elder.
        # The elder results are already shown, so the new part is the baby-proofing check.
        selection = {**selection, "mode": "baby", "action": "choose_mode"}
        ctx.logger.info(f"child age given while {shown} results are shown -> baby-proofing")
    if selection.get("action") in ("submit_intake", "choose_mode") and not files and repeats_answers(state, selection):
        # e.g. "Following up on the assessment... Dad is 84, uses a walker... recommend products within $300".
        selection = {**selection, "action": "approve_plan" if SHOP_WORDS.search(text) else "show_results"}
        ctx.logger.info(f"repeat of earlier answers -> {selection['action']}")
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
            if MENTIONS_MEDIA.search(text):
                # Live: ASI:One's planner wrote "see uploaded video" but left the link out. Ask for the
                # link itself, or the planner reads "no web links" as a dead end and shops elsewhere.
                ask = ("Your video didn't come through with this message. Please send it again, as a file or "
                       "the direct video link (e.g. the .mp4 link), and I'll map the home in 3D.")
            else:
                ask = ("Please attach a 30-second video or a few photos of the home, as a file or a direct "
                       "video link (YouTube pages don't work), and I'll map it in 3D.")
            await send(ctx, sender, text_message(lead + ask))
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
    elif action == "approve_plan" and not state.get("result") and has_answers(state, state.get("wanted_mode") or mode or ""):
        # "Approve" before any results, but every answer is known (the planner can run ahead): run the check.
        await on_intake(ctx, sender, state, {"mode": state.get("wanted_mode") or mode})
    elif action == "approve_plan":
        if isinstance(selection.get("fix_ids"), list) and selection["fix_ids"]:
            state["chosen_fixes"] = selection["fix_ids"]
        if (state.get("result") or {}).get("mode") == "claim":
            await build_claim(ctx, sender, state)
        else:
            await shop(ctx, sender, state)
    elif action == "payment_opened":
        await send(ctx, sender, text_message("Finish the checkout in the new tab, then tap I've paid."))
    elif action == "link_opened":
        await send(ctx, sender, text_message("Opened in a new tab."))
    elif action == "show_results" and state.get("result"):
        await show_results(ctx, sender, state, "Here are your results again.")
    elif action == "check_payment":
        await check_payment(ctx, sender, state)
    elif action == "decline_plan":
        await send(ctx, sender, text_message("No problem. Your results are saved; say \"approve\" whenever you're ready."))
    else:
        await show_modes(ctx, sender, state, "What would you like to do next?")


async def send_card(ctx: Context, to: str, state: dict, narration: str, kind: str, payload: dict,
                    terminal: bool = False):
    """Send an Interactive Card and remember it, so prose replies can be matched to it.
    terminal: the card has nothing to tap (a cart waiting for payment), so ASI:One doesn't wait on it."""
    state["last_card"] = {"kind": kind, "payload": payload}
    await send(ctx, to, card_message(narration, kind, payload, terminal=terminal))


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
    # A new check starts a new plan: its own cart, fee and claim package.
    for stale in ("cart", "cart_for", "cart_notes", "chosen_fixes", "claim_package", "claim_running"):
        state.pop(stale, None)
    state["payment"] = None
    # One reply per message: ASI:One's planner treats the first text reply as the agent's whole answer.
    result = await run_mode(ctx, state, mode, profile)
    state["result"] = result.model_dump()
    state["result_id"] = str(uuid4())
    if not result.findings:
        await send(ctx, sender, text_message(result.summary))
        return
    next_step = ("Tap Build my claim package (or say \"build the package\") and I'll price each item at today's "
                 "replacement cost and build it myself." if mode == "claim" else
                 "Pick the fixes and tap Find products (or say \"find products\"). I find everything myself, "
                 "furniture, safety gear and electronics like monitors, build one cart within your budget and check "
                 "it out with Stripe; no other agent is needed.")
    view = (f"\n\n**[Open the 3D view of your home]({result.viewer_url})**: every finding is pinned on its object; "
            "click one to see why it was flagged." if result.viewer_url else "")
    await show_results(ctx, sender, state, f"{intro} {result.summary}\n\n{findings_text(result)}\n\n{next_step}{view}".strip())
    prefetch(ctx, state)


def findings_text(result: ModeResult, limit: int = 8) -> str:
    """The card's content as a short list in the message itself, so it reads without the card too."""
    if result.mode == "claim":
        rooms: dict[str, int] = {}
        for f in result.findings:
            rooms[(f.fix_summary or "Home").split(" · ")[0]] = rooms.get((f.fix_summary or "Home").split(" · ")[0], 0) + 1
        return "\n".join(f"- {room}: {n} item{'s' if n != 1 else ''}" for room, n in rooms.items())
    lines = []
    for f in result.findings[:limit]:
        if f.kind == "hazard":
            label = cards.SEVERITY.get(f.severity, ("Moderate",))[0]
            lines.append(f"- **{f.title}** ({label.lower()})" + (f": {f.fix_summary}" if f.fix_summary else ""))
        else:
            lines.append(f"- **{f.title}**" + (f": {f.fix_summary}" if f.fix_summary else ""))
    more = len(result.findings) - limit
    return "\n".join(lines) + (f"\n- …and {more} more in the card" if more > 0 else "")


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


def _short(title: str, limit: int = 60) -> str:
    """A store title short enough for a link: "Amazon Basics Grab Bar, 18 Inch…"."""
    title = title.replace("[", "(").replace("]", ")")
    return title if len(title) <= limit else title[:limit].rsplit(" ", 1)[0] + "…"


def fee_label(state: dict | None = None) -> str:
    """The service fee: what the Cart agent set for this plan, else the flat fee."""
    fee = ((state or {}).get("cart") or {}).get("service_fee_usd") or FLAT_SERVICE_FEE_USD
    return f"${format_service_fee_usd(fee)}"


SHOP_TIMEOUT_S = 50   # Product Finder stops each search at 30 s and runs them all at once
CLAIM_PRICE_LIMIT = 120  # replacement-price searches per claim (most come from the deep-search pools)


async def ask(ctx: Context, agent: str, request, response_type, timeout: float):
    """One request to one of Pranay's action agents; None if it doesn't answer in time."""
    reply, status = await ctx.send_and_receive(ADDRESSES[agent], request, response_type=response_type, timeout=timeout)
    if isinstance(reply, response_type):
        return reply
    ctx.logger.warning(f"{agent} did not answer ({status.detail})")
    return None


async def find_quotes(ctx: Context, job_id: str, queries: list[ProductQuery]) -> FindProductsResult:
    """Ask the Product Finder agent; if it's unreachable, run the same search here."""
    found = await ask(ctx, "product_finder", FindProductsRequest(job_id=job_id, queries=queries),
                      FindProductsResult, SHOP_TIMEOUT_S)
    if found is not None and found.ok:
        return found
    ctx.logger.warning(f"job={job_id} Product Finder failed ({found.error if found else 'no reply'}); searching here")
    return await local_find_products(FindProductsRequest(job_id=job_id, queries=queries))


# Product searches started while the user reads the results, keyed by result_id, so approving
# (or asking for the claim package) doesn't wait for them. One process, so memory is enough.
PREFETCH: dict[str, asyncio.Task] = {}


def prefetch(ctx: Context, state: dict):
    """Search for every fix's products (or every claim item's price) in the background."""
    result_id, job_id = state.get("result_id"), state.get("job_id")
    if not result_id or not job_id or result_id in PREFETCH:
        return
    claim = (state.get("result") or {}).get("mode") == "claim"
    queries = claim_queries(state) if claim else plan_queries(state, everything=True)
    if not queries:
        return
    async def run() -> FindProductsResult:
        t0 = time.monotonic()
        found = await find_quotes(ctx, job_id, queries)
        ctx.logger.info(f"{_now()} job={job_id} prefetch: {len(queries)} searches -> {len(found.quotes)} quotes "
                        f"in {time.monotonic() - t0:.1f} s")
        return found

    ctx.logger.info(f"{_now()} job={job_id} prefetch started: {len(queries)} searches")
    PREFETCH[result_id] = asyncio.get_running_loop().create_task(run())
    for old in list(PREFETCH)[:-50]:  # keep memory bounded
        PREFETCH.pop(old, None)


async def quotes_for(ctx: Context, state: dict, queries: list[ProductQuery]) -> FindProductsResult:
    """The prefetched search when there is one (waiting for it if it's still running), else a new search."""
    task = PREFETCH.get(state.get("result_id") or "")
    if task is not None:
        try:
            found = await asyncio.wait_for(asyncio.shield(task), SHOP_TIMEOUT_S)
            wanted = {q.constraints.get("finding_id") for q in queries}
            return found.copy(update={"quotes": [q for q in found.quotes if q.finding_id in wanted]})
        except Exception:
            ctx.logger.exception("prefetched product search failed; searching again")
    return await find_quotes(ctx, state["job_id"], queries)


def claim_queries(state: dict) -> list[ProductQuery]:
    result = ModeResult.model_validate(state["result"])
    items = [f for f in result.findings if f.kind == "item" and f.product_query][:CLAIM_PRICE_LIMIT]
    return [f.product_query.copy(update={"constraints": {**f.product_query.constraints, "finding_id": f.id}})
            for f in items]


def plan_queries(state: dict, everything: bool = False) -> list[ProductQuery]:
    """One product search per chosen fix, most severe first, tagged with the finding it fixes."""
    result = ModeResult.model_validate(state["result"])
    chosen = set() if everything else set(state.get("chosen_fixes") or [])
    fixes = [f for f in result.findings if f.product_query and (not chosen or f.id in chosen)]
    fixes.sort(key=lambda f: -f.severity)
    return [f.product_query.copy(update={"constraints": {**f.product_query.constraints, "finding_id": f.id}})
            for f in fixes]


async def shop(ctx: Context, sender: str, state: dict):
    """Approve -> Product Finder -> Cart -> cart card with the Stripe service fee."""
    result = state.get("result")
    if not result or not result.get("findings"):
        await show_modes(ctx, sender, state, "There's no fix plan to approve yet. Pick a check to run first.")
        return
    if (state.get("payment") or {}).get("status") == "paid":
        await after_payment(ctx, sender, state, state["payment"].get("session", ""), again=True)
        return
    if state.get("cart") and (state.get("payment") or {}).get("status") in ("requested", "rejected") \
            and state.get("cart_for") == state.get("chosen_fixes"):
        await send_card(ctx, sender, state, "Here's your cart again. Tap Pay on the payment request to check out.", "custom",
                        cards.cart_card(CartResult.model_validate(state["cart"]), state.get("profile", {}).get("budget_usd"),
                                        fee_label(state), None, state.get("cart_notes"),
                                        f"${state['payment'].get('amount') or fee_label(state)[1:]}"), terminal=True)
        return
    queries = plan_queries(state)
    if not queries:
        await send(ctx, sender, text_message(
            "None of the fixes you picked need anything bought: they're about moving things or changing habits."))
        return
    job_id = state["job_id"]
    t0 = time.monotonic()
    found = await quotes_for(ctx, state, queries)
    t1 = time.monotonic()
    budget = (state.get("profile") or {}).get("budget_usd")
    cart = await ask(ctx, "cart", CartRequest(job_id=job_id, quotes=found.quotes, budget_usd=budget), CartResult, 20)
    if cart is None or not cart.ok:
        cart = build_cart(CartRequest(job_id=job_id, quotes=found.quotes, budget_usd=budget))
    ctx.logger.info(f"job={job_id} shop: {len(queries)} searches -> {len(found.quotes)} quotes -> {len(cart.items)} in cart "
                    f"(products {t1 - t0:.1f} s, cart {time.monotonic() - t1:.1f} s)")
    state["cart"] = cart.model_dump()
    state["cart_for"] = state.get("chosen_fixes")
    state["cart_notes"] = cart_notes(state, queries, found, cart)
    if not cart.items:
        await send(ctx, sender, text_message(
            f"I searched for {len(queries)} fix{'es' if len(queries) != 1 else ''} but couldn't confirm a product page "
            "with a price for any of them right now, so there's nothing to charge. Say \"approve\" to try again."))
        return
    await request_fee(ctx, sender, state)


def cart_notes(state: dict, queries: list[ProductQuery], found: FindProductsResult, cart: CartResult) -> dict:
    """Which picked fixes didn't make the cart: left out to stay in budget, or no product found."""
    names = {f["id"]: (f.get("fix_summary") or f["title"]).split(" (")[0].split(", which")[0]
             for f in (state.get("result") or {}).get("findings", [])}
    in_cart = {q.url for q in cart.items}
    quotes: dict[str, list] = {}
    for q in found.quotes:
        quotes.setdefault(q.finding_id or "", []).append(q)
    left_out, not_found = [], []
    for fid in (q.constraints.get("finding_id") for q in queries):
        if not quotes.get(fid):
            not_found.append(names.get(fid, fid))
        elif not any(q.url in in_cart for q in quotes[fid]):
            left_out.append(names.get(fid, fid))
    return {"left_out": list(dict.fromkeys(left_out)), "not_found": list(dict.fromkeys(not_found))}


def _qty(q) -> int:
    return max(1, int((q.specs or {}).get("quantity", 1) or 1))


async def request_fee(ctx: Context, sender: str, state: dict):
    """The cart becomes a demo order: one Stripe test-mode checkout with every product as its own line
    plus the service fee. Nothing is ordered from the stores; the store pages come with the receipt."""
    cart = CartResult.model_validate(state["cart"])
    if not stripe_pay.enabled():
        ctx.logger.error("Stripe test keys are missing; cannot take the payment")
        await send(ctx, sender, text_message(
            "Payments aren't switched on yet, so I can't check out right now. Your cart is saved."))
        return
    fee = format_service_fee_usd(cart.service_fee_usd)
    total = format_service_fee_usd(round(cart.subtotal_usd + float(fee), 2))
    lines = [{"name": _short(q.title, 120), "unit_usd": q.price_usd, "quantity": _qty(q), "image": q.image_url,
              "description": f"From {q.merchant} (demo order: nothing is actually bought)"} for q in cart.items]
    lines.append({"name": "Last Mile Home service fee", "unit_usd": float(fee), "quantity": 1,
                  "description": "Finding products that fit your measured home"})
    reference = state.get("job_id") or str(uuid4())
    t0 = time.monotonic()
    try:
        checkout = await stripe_pay.create_checkout(
            reference, f"{len(cart.items)} products that fit your measured space", total, items=lines)
    except Exception:
        ctx.logger.exception("Stripe checkout failed")
        await send(ctx, sender, text_message("I couldn't reach the payment provider. Please say \"approve\" again in a moment."))
        return
    t_stripe = time.monotonic() - t0
    # Send RequestPayment before anything slow (or any LLM call) so ASI:One renders the payment card.
    await send(ctx, sender, RequestPayment(
        accepted_funds=[Funds(currency="USD", amount=total, payment_method="stripe")],
        recipient=str(coordinator.address),
        deadline_seconds=1800,
        reference=reference,
        description=f"Last Mile Home demo order: {len(cart.items)} products + ${fee} service fee = ${total}",
        metadata={
            "stripe": checkout["embedded"],
            "service": "last_mile_home",
            "content": f"Check out your cart of {len(cart.items)} products (${total}, Stripe test mode).",
        },
    ))
    state["payment"] = {
        "status": "requested",
        "reference": reference,
        "fee": fee,
        "amount": total,
        "stripe_sessions": [checkout["embedded_id"]],  # one checkout: ASI:One's Pay button opens it
    }
    budget = (state.get("profile") or {}).get("budget_usd")
    notes = state.get("cart_notes") or {}
    over = ""
    if notes.get("left_out"):
        over += f" To stay within your ${budget:,.0f} budget I left out: {'; '.join(notes['left_out']).lower()}."
    if notes.get("not_found"):
        over += f" I couldn't confirm a product page for: {'; '.join(notes['not_found']).lower()}."
    await send_card(
        ctx, sender, state,
        f"I found {len(cart.items)} product{'s' if len(cart.items) != 1 else ''} that fit and added "
        f"{'them' if len(cart.items) != 1 else 'it'} to your cart.{over}\n\n"
        + "\n".join(f"- {_short(q.title)}: ${q.price_usd:,.2f}" + (f" × {_qty(q)}" if _qty(q) > 1 else "")
                    + f" at {q.merchant}" for q in cart.items[:10])
        + f"\n\nProducts ${cart.subtotal_usd:,.2f} + ${fee} service fee = **${total}**.\n\n"
        f"Tap **Pay** on the payment request to check out **${total}** with Stripe. It's a demo checkout in "
        "Stripe test mode: use card 4242 4242 4242 4242, nothing is really charged or shipped. "
        "I'll confirm your order here as soon as it goes through.",
        "custom", cards.cart_card(cart, budget, f"${fee}", None, notes, f"${total}"), terminal=True)
    watch_payment(ctx, sender, reference)
    ctx.logger.info(f"job={reference} checkout requested (${total}): Stripe {t_stripe:.1f} s, "
                    f"replies {time.monotonic() - t0 - t_stripe:.1f} s")


# ASI:One's payment notice (CommitPayment) and the user's "I've paid" tap can arrive together. Two
# verifier requests in one conversation would both get the first reply (uagents matches replies by
# agent and session), so they take turns, and a checkout already confirmed isn't asked about again.
VERIFY_LOCKS: dict[str, asyncio.Lock] = {}
CONFIRMED: set[tuple[str, str]] = set()   # (conversation, checkout session) known paid
RECEIPTS: set[tuple[str, str]] = set()    # (conversation, checkout session) receipt already sent


async def verify_paid(ctx: Context, state: dict, session_id: str) -> bool:
    """Ask Pranay's Payment Verifier; if it doesn't answer, check with Stripe directly.

    Only sessions this conversation created count, so a forged or reused id can't unlock anything.
    """
    payment = state.get("payment") or {}
    if session_id not in payment.get("stripe_sessions", []):
        ctx.logger.warning(f"PAYMENT rejected: {session_id} is not one of this conversation's checkout sessions")
        return False
    async with VERIFY_LOCKS.setdefault(str(ctx.session), asyncio.Lock()):
        if (str(ctx.session), session_id) in CONFIRMED:
            return True
        paid = await _verify(ctx, state, session_id)
        if paid:
            CONFIRMED.add((str(ctx.session), session_id))
        return paid


async def _verify(ctx: Context, state: dict, session_id: str) -> bool:
    payment = state.get("payment") or {}
    fee = payment.get("amount") or payment.get("fee") or format_service_fee_usd(FLAT_SERVICE_FEE_USD)  # the order total
    req = VerifyPaymentRequest(job_id=state.get("job_id") or "", service_fee_usd=fee, transaction_id=session_id)
    reply = await ask(ctx, "payment_verifier", req, VerifyPaymentResult, 20)
    if reply is not None and reply.ok:
        ctx.logger.info(f"PAYMENT verifier: verified={reply.verified} {reply.detail}")
        return reply.verified
    ctx.logger.info("Payment Verifier unavailable; checking Stripe directly")
    try:
        return await stripe_pay.is_paid(session_id, expected_usd=float(fee))
    except Exception:
        ctx.logger.exception(f"Stripe lookup failed for {session_id}")
        return False


PAYMENT_POLL_FAST_S, PAYMENT_POLL_SLOW_S = 5, 20   # every 5 s for 5 minutes, then every 20 s
PAYMENT_WATCH_FAST_S, PAYMENT_WATCH_S = 300, 1800


def watch_payment(ctx: Context, sender: str, reference: str):
    """No "I've paid" button: after the cart goes out, check Stripe in the background and post the
    receipt as soon as the checkout is paid. ASI:One's own payment window reports through
    CommitPayment; whichever comes first sends the receipt, the other is a no-op."""

    async def run():
        started = time.monotonic()
        while time.monotonic() - started < PAYMENT_WATCH_S:
            await asyncio.sleep(PAYMENT_POLL_FAST_S if time.monotonic() - started < PAYMENT_WATCH_FAST_S
                                else PAYMENT_POLL_SLOW_S)
            state = load(ctx, sender)
            payment = state.get("payment") or {}
            if payment.get("reference") != reference or payment.get("status") not in ("requested", "rejected"):
                return  # paid through another path, or a new plan replaced this one
            try:
                session_id = await find_paid_session(ctx, state)
            except Exception:
                ctx.logger.exception("payment watch failed; trying again")
                continue
            if session_id:
                ctx.logger.info(f"PAYMENT seen by the watcher: {session_id}")
                await after_payment(ctx, sender, state, session_id)
                save(ctx, sender, state)
                return

    asyncio.get_running_loop().create_task(run())


async def find_paid_session(ctx: Context, state: dict) -> str | None:
    """Which of this conversation's checkouts (the one inside ASI:One, the Pay link) was paid.

    Stripe is asked about all of them at once, then the Payment Verifier agent confirms the paid
    one. One verifier request at a time: uagents matches replies by (agent, session), so two
    requests to the same agent in one conversation both receive the first reply.
    """
    payment = state.get("payment") or {}
    sessions = payment.get("stripe_sessions", [])
    fee = float(payment.get("amount") or payment.get("fee") or FLAT_SERVICE_FEE_USD)  # the order total
    looked = await asyncio.gather(*(stripe_pay.is_paid(sid, expected_usd=fee) for sid in sessions), return_exceptions=True)
    if any(isinstance(x, Exception) for x in looked):
        ctx.logger.warning("Stripe lookup failed; asking the Payment Verifier about each checkout in turn")
        candidates = sessions
    else:
        candidates = [sid for sid, paid in zip(sessions, looked) if paid]
    for session_id in candidates:
        if await verify_paid(ctx, state, session_id):
            return session_id
    return None


async def after_payment(ctx: Context, sender: str, state: dict, session_id: str, again: bool = False):
    if (str(ctx.session), session_id) in RECEIPTS:
        again = True  # the other path (payment notice or "I paid") already sent the receipt
    RECEIPTS.add((str(ctx.session), session_id))
    state["payment"] = {**state.get("payment", {}), "status": "paid", "session": session_id}
    cart = CartResult.model_validate(state["cart"]) if state.get("cart") else None
    total = f"${state['payment'].get('amount') or format_service_fee_usd(FLAT_SERVICE_FEE_USD)}"
    links = "\n".join(f"- [{_short(q.title)}]({q.url}): ${q.price_usd:,.2f}" + (f" × {_qty(q)}" if _qty(q) > 1 else "")
                      + f" at {q.merchant}" for q in (cart.items if cart else [])[:10])
    if again:
        text = f"Your order is already placed.\n\nYour products and their store pages:\n{links}" if links \
            else "Your order is already placed."
    else:
        # The wrap-up: summary, what was ordered (store links), next steps, and the 3D view.
        result = ModeResult.model_validate(state["result"]) if state.get("result") else None
        text = await summary.wrap_up(result, cart, state.get("cart_notes") or {}, total,
                                     result.viewer_url, _short) if result else \
            f"**Order placed (demo):** {total} paid in Stripe test mode.\n\n{links}"
    await send_card(ctx, sender, state, text, "custom", cards.receipt_card(total, session_id[-12:], cart))


async def check_payment(ctx: Context, sender: str, state: dict):
    payment = state.get("payment") or {}
    if not payment.get("stripe_sessions") and payment.get("status") != "paid":
        await send(ctx, sender, text_message(
            "There's nothing to pay yet. Once you approve a fix plan I'll find products, add them to a cart and send you a Stripe checkout."))
        return
    if payment.get("status") == "paid":
        await after_payment(ctx, sender, state, payment.get("session", ""), again=True)
        return
    session_id = await find_paid_session(ctx, state)
    if session_id:
        await after_payment(ctx, sender, state, session_id)
        return
    total = f"${payment.get('amount') or payment.get('fee') or FLAT_SERVICE_FEE_USD}"
    await send_card(ctx, sender, state, f"I don't see the payment yet. Tap **Pay** on the payment request to "
                    f"check out {total} with Stripe; I'll confirm your order here as soon as it goes through.",
                    "custom", cards.payment_card(total, None), terminal=True)


CLAIM_INLINE_WAIT_S = 30  # wait this long for the prices, then file and answer; else post the package later


async def make_claim_package(ctx: Context, state: dict) -> dict:
    """Prices (from the search started with the results) -> Insurance Claim Filer -> saved package."""
    job_id = state["job_id"]
    result = ModeResult.model_validate(state["result"])
    items = [f for f in result.findings if f.kind == "item"]
    found = await quotes_for(ctx, state, claim_queries(state))
    price = {}
    for q in found.quotes:  # the primary pick (cheapest verified) is the replacement price
        if q.finding_id and (q.specs or {}).get("role") != "backup":
            price.setdefault(q.finding_id, q)
    priced, unpriced = [], 0
    for f in items:
        q = price.get(f.id)
        frame = evidence_image(state, f)
        evidence = [e.copy(update={"frame_url": frame}) for e in f.evidence[:1]] if frame else f.evidence
        if q:
            priced.append(f.copy(update={"value_usd": q.price_usd, "value_basis": "estimate", "evidence": evidence}))
        else:
            unpriced += 1
            priced.append(f.copy(update={"value_basis": "needs_price", "evidence": evidence}))
    request = ClaimRequest(job_id=job_id, space_id=state["space_id"], findings=priced,
                           profile=Profile.model_validate(state.get("profile") or {}))
    pkg = await ask(ctx, "insurance_filer", request, ClaimPackage, 45)
    if pkg is None:
        pkg = await local_build_claim_package(request)
    ctx.logger.info(f"job={job_id} claim package: {pkg.item_count} items, ${pkg.total_usd:,.2f}, ok={pkg.ok}")
    return {"package": pkg.model_dump(), "findings": [f.model_dump() for f in priced], "unpriced": unpriced}


async def build_claim(ctx: Context, sender: str, state: dict):
    """Price every item (Product Finder), then the Insurance Claim Filer builds the package.

    Pricing starts when the inventory is shown, so it's usually done by the time the user asks:
    then the package is the reply. If not, this answers now and posts the package when ready.
    """
    if state.get("claim_package"):
        await show_claim_package(ctx, sender, state, "Here's your claim package again.")
        return
    if state.get("claim_running"):
        await send(ctx, sender, text_message("Still pricing your items; the claim package will appear here when it's ready."))
        return
    prefetch(ctx, state)  # no-op if the prices are already being searched
    task = PREFETCH.get(state.get("result_id") or "")
    if task is not None:
        try:
            await asyncio.wait_for(asyncio.shield(task), CLAIM_INLINE_WAIT_S)
        except asyncio.TimeoutError:
            pass
    if task is not None and task.done():
        try:
            state["claim_package"] = await make_claim_package(ctx, state)
            await show_claim_package(ctx, sender, state, "")
            return
        except Exception:
            ctx.logger.exception(f"job={state['job_id']} claim package failed inline; retrying in the background")
    result = ModeResult.model_validate(state["result"])
    count = min(CLAIM_PRICE_LIMIT, sum(1 for f in result.findings if f.kind == "item"))
    state["claim_running"] = True
    await send(ctx, sender, text_message(
        f"Pricing {count} items at today's replacement cost, then building your claim package "
        "(spreadsheet and cover letter). It takes about a minute; I'll post it here."))
    job_id = state["job_id"]
    snapshot = dict(state)

    async def run():
        saved = None
        try:
            saved = await make_claim_package(ctx, snapshot)
        except Exception:
            ctx.logger.exception(f"job={job_id} claim package failed")
        # The user may have done other things during the minute this took: update the latest state.
        fresh = load(ctx, sender)
        fresh.pop("claim_running", None)
        if fresh.get("job_id") != job_id:
            save(ctx, sender, fresh)
            return
        if saved:
            fresh["claim_package"] = saved
            await show_claim_package(ctx, sender, fresh, "")
        else:
            await send(ctx, sender, text_message(
                "Sorry, I couldn't finish the claim package. Your inventory is saved; tap Build my claim package to try again."))
        save(ctx, sender, fresh)

    asyncio.get_running_loop().create_task(run())


async def show_claim_package(ctx: Context, sender: str, state: dict, lead: str):
    saved = state["claim_package"]
    pkg = ClaimPackage.model_validate(saved["package"])
    findings = [Finding.model_validate(f) for f in saved["findings"]]
    priced = [f for f in findings if f.value_usd]
    links = " · ".join(f"[{label}]({url})" for label, url in (("Excel", pkg.inventory_xlsx_url), ("CSV", pkg.inventory_csv_url),
                                                             ("Cover letter", pkg.letter_pdf_url)) if url)
    unpriced = saved["unpriced"]
    still = f" ({unpriced} still need a price)" if unpriced else ""
    download = f"\n\nDownload: {links}.\n\n" if links else ""
    narration = (f"{lead} Your claim package is ready: {pkg.item_count} items, ${pkg.total_usd:,.2f} replacement cost{still}. "
                 f"{download}It's ready to send to your insurer; nothing has been filed.").strip()
    hero = state.get("frames", {}).get("claim") or next(iter(state.get("frames", {}).values()), "")
    await send_card(ctx, sender, state, narration, "custom", cards.claim_package_card(pkg, priced, saved["unpriced"], hero))


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
        await send(ctx, sender, CancelPayment(transaction_id=msg.transaction_id, reason="We couldn't verify this payment."))
    save(ctx, sender, state)


async def settle_commit(ctx: Context, sender: str, state: dict, msg: CommitPayment):
    if msg.funds.payment_method != "stripe" or not msg.transaction_id:
        await send(ctx, sender, CancelPayment(transaction_id=msg.transaction_id, reason="Only card payments via Stripe are accepted."))
        return
    if not await verify_paid(ctx, state, msg.transaction_id):
        await send(ctx, sender, CancelPayment(
            transaction_id=msg.transaction_id, reason="Stripe checkout isn't complete yet. Finish it, then pay again."))
        return
    await send(ctx, sender, CompletePayment(transaction_id=msg.transaction_id))
    await after_payment(ctx, sender, state, msg.transaction_id)


@payments.on_message(RejectPayment)
async def on_reject(ctx: Context, sender: str, msg: RejectPayment):
    ctx.logger.info(f"PAYMENT rejected by {sender[:16]}…: {msg.reason}")
    state = load(ctx, sender)
    # Keep the checkouts: the user may still pay with the card's Pay link and tap I've paid.
    state["payment"] = {**(state.get("payment") or {}), "status": "rejected"}
    save(ctx, sender, state)
    await send(ctx, sender, text_message("No problem, the payment was cancelled. Say \"approve\" when you're ready."))


coordinator.include(chat, publish_manifest=True)
coordinator.include(payments, publish_manifest=True)

if __name__ == "__main__":
    coordinator.run()
