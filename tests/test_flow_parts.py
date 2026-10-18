"""Smaller parts of the flow: product cache, message understanding, cards, claim package, send order."""
import asyncio
import json

import pytest

from agents.coordinator import agent as coord
from agents.coordinator import cards
from agents.coordinator.understand import fill_missing, fix_mode
from shared.models import (CartResult, ClaimPackage, ClaimRequest, Finding, FindProductsResult, ModeResult,
                           ProductQuery, ProductQuote)
from tests.conftest import FakeCtx, USER


def run(coro):
    return asyncio.run(coro)


# --- Product Finder cache (live bug: cached quotes kept an old finding id and were dropped) ----

def test_cached_quotes_are_chosen_again_for_this_request(tmp_path, monkeypatch):
    from agents.actions.product_finder import search

    monkeypatch.setattr(search, "CACHE_PATH", tmp_path / "queries.json")
    old = [ProductQuote(title="Handrail kit", url="https://s/rail", merchant="S", price_usd=40, url_verified=True,
                        finding_id="elder_OLD", specs={"quantity": 1, "role": "primary"}),
           ProductQuote(title="Handrail premium", url="https://s/rail2", merchant="S", price_usd=150, url_verified=True,
                        finding_id="elder_OLD", specs={"quantity": 1, "role": "backup"})]
    search._cache_store("stair handrail kit", old)

    async def fetch():
        q = ProductQuery(query="stair handrail kit", max_price_usd=100, quantity=2, constraints={"finding_id": "elder_NEW"})
        return await search.resolve_query(None, q)

    quotes, note = run(fetch())
    assert note is None
    # Re-tagged for this request; the $150 one is over the $100 cap, so it's the backup, not hidden.
    assert [(x.url, x.finding_id, x.specs["quantity"]) for x in quotes] == [("https://s/rail", "elder_NEW", 2),
                                                                         ("https://s/rail2", "elder_NEW", 2)]
    assert "share of your budget" in quotes[1].fit_note


# --- understanding what the planner relays -------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("the resident is an 84-year-old man who uses a walker and gets up at night. Budget: $300.",
     {"mobility_aid": "walker", "night_trips": "true", "age": "84", "budget_usd": "300"}),
    ("Grandpa is 88 and uses a wheelchair, $1,200 budget", {"mobility_aid": "wheelchair", "age": "88", "budget_usd": "1200"}),
    ("She's 70, walks fine, sleeps through the night.", {"night_trips": "false", "age": "70"}),
    ("My toddler is 14 months old", {"child_age_months": "14"}),
    ("my son is 2 years old", {"child_age_months": "24"}),
    ("Replacement cost policy, ZIP 90024", {"policy_type": "replacement_cost", "zip_code": "90024"}),
])
def test_answers_the_interpreter_missed_are_filled(text, expected):
    got = fill_missing(text, {"action": "choose_mode"})
    assert {k: got.get(k) for k in expected} == expected


def test_the_interpreters_answers_win():
    assert fill_missing("uses a walker", {"mobility_aid": "cane"})["mobility_aid"] == "cane"


def test_making_a_nursery_is_a_room_makeover_not_baby_proofing():
    assert fix_mode("Make a nursery in the attic please.", {"action": "choose_mode", "mode": "baby"}) == \
        {"action": "choose_mode", "mode": "transform", "goal": "nursery"}
    assert fix_mode("Baby-proof the nursery, she's 9 months", {"action": "choose_mode", "mode": "baby"})["mode"] == "baby"


def test_restated_answers_after_results_are_not_a_new_intake():
    """Live bug: the planner rewrote "find products" as the whole intake again and the check re-ran."""
    state = {"result": {"mode": "elder"}, "answers": {"person": "Dad", "age": "84", "mobility_aid": "walker",
                                                      "night_trips": "true", "budget_usd": "300"}}
    restated = {"action": "submit_intake", "mode": "elder", "age": "84", "mobility_aid": "walker",
                "night_trips": "true", "budget_usd": "300", "person": "Dad"}
    assert coord.repeats_answers(state, restated)
    assert coord.SHOP_WORDS.search("recommend specific products within the $300 budget")
    assert not coord.repeats_answers(state, {**restated, "mobility_aid": "wheelchair"})  # a real change re-runs


def test_restated_request_for_products_goes_to_the_cart(fake_stripe):
    calls = []

    async def fake_shop(ctx, sender, state):
        calls.append("shop")

    ctx = FakeCtx()
    state = {"job_id": "j", "space_id": "s", "result": {"mode": "elder", "findings": []},
             "answers": {"mobility_aid": "walker", "budget_usd": "300"}}
    orig = coord.shop
    coord.shop = fake_shop
    try:
        run(coord.route(ctx, USER, state, [], {"action": "submit_intake", "mode": "elder", "mobility_aid": "walker",
                                               "budget_usd": "300"}, "Please recommend products for these fixes"))
    finally:
        coord.shop = orig
    assert calls == ["shop"]


# --- cards ---------------------------------------------------------------------------------------

def result(mode, viewer="http://127.0.0.1:5173/s/sp1?mode=elder&o=ov1"):
    f = [Finding(id="f1", kind="hazard" if mode != "claim" else "item", title="Thing", severity=4,
                 fix_summary="Room · fix it", product_query=ProductQuery(query="q"))]
    if mode == "transform":
        f = [Finding(id="transform_item_0", kind="suggestion", title="Add: Desk", fix_summary="fits",
                     product_query=ProductQuery(query="desk"))]
    return ModeResult(job_id="j", mode=mode, ok=True, summary="s", findings=f, viewer_url=viewer)


@pytest.mark.parametrize("mode", ["elder", "baby", "transform", "claim"])
def test_cards_have_no_link_buttons(mode):
    """ASI:One card buttons only submit a selection and the first click locks the card (seen live: an
    "Open at Walmart" click disabled every other button), so links live in the message text instead."""
    card = json.dumps(cards.results_card(result(mode), "https://img", "$1.00" if mode != "claim" else None))
    assert "redirect" not in card and "View in 3D" not in card


def test_results_message_links_the_3d_view():
    async def fake_run_mode(ctx, state, mode, profile):
        return result("elder")

    ctx = FakeCtx()
    state = {"job_id": "j", "space_id": "sp1", "rooms": [], "frames": {"elder": "https://img"}, "answers": {}}
    orig = coord.run_mode
    coord.run_mode = fake_run_mode
    try:
        run(coord.on_intake(ctx, USER, state, {"mode": "elder", "mobility_aid": "walker"}))
    finally:
        coord.run_mode = orig
    assert any("[Open the 3D view of your home](http://127.0.0.1:5173/s/sp1" in t for t in ctx.texts())


def cart():
    q = ProductQuote(title="Grab bar", url="https://store/grab", merchant="Store", price_usd=24, url_verified=True,
                     specs={"quantity": 2, "role": "primary"}, fit_note="Prices as of today. fits")
    return CartResult(job_id="j", ok=True, items=[q], subtotal_usd=48, within_budget=True, service_fee_usd="1.00")


def test_cart_card_shows_prices_without_buttons_or_store_links_before_paying():
    card = json.dumps(ensure_ascii=False, obj=cards.cart_card(cart(), 300, "$1.00", "https://checkout.stripe.com/c/pay/cs_test_1"))
    assert "Your cart · 1 product" in card and "$24.00 × 2" in card and "Within your $300.00 budget" in card
    assert "https://store/grab" not in card and "redirect" not in card and '"type": "button"' not in card


def test_receipt_card_lists_the_products_without_link_buttons():
    card = json.dumps(ensure_ascii=False, obj=cards.receipt_card("$1.00", "abc", cart()))
    assert "Order placed (demo)" in card and "Grab bar" in card and "redirect" not in card


def test_claim_package_card_has_downloads_and_totals():
    pkg = ClaimPackage(job_id="j", ok=True, inventory_xlsx_url="http://x/a.xlsx", inventory_csv_url="http://x/a.csv",
                       letter_pdf_url="http://x/a.pdf", total_usd=1234.5, item_count=3)
    priced = [Finding(id="a", kind="item", title="Sofa", value_usd=900, fix_summary="Living room · priced as sofa")]
    card = json.dumps(ensure_ascii=False, obj=cards.claim_package_card(pkg, priced, 2, "https://img"))
    assert "$1,234.50" in card and "2 to price by hand" in card and "redirect" not in card


# --- claim package flow ------------------------------------------------------------------------

def test_claim_package_prices_items_and_marks_the_rest(monkeypatch):
    findings = [Finding(id=f"claim_{i}", kind="item", title=f"Item {i}", fix_summary="Kitchen · priced as x",
                        product_query=ProductQuery(query=f"item {i} replacement price")) for i in range(3)]
    state = {"job_id": "j", "space_id": "sp", "result_id": "r", "frames": {"claim": "https://img"},
             "result": ModeResult(job_id="j", mode="claim", ok=True, summary="s", findings=findings).model_dump()}
    filed = []

    async def finder(req):
        quotes = [ProductQuote(title="x", url=f"https://s/{q.constraints['finding_id']}", merchant="S", price_usd=100,
                               url_verified=True, finding_id=q.constraints["finding_id"], specs={"role": "primary"})
                  for q in req.queries[:2]]  # the third item finds no price
        return FindProductsResult(job_id="j", ok=True, quotes=quotes)

    async def filer(req: ClaimRequest):
        filed.append(req)
        total = sum(f.value_usd or 0 for f in req.findings)
        return ClaimPackage(job_id="j", ok=True, inventory_xlsx_url="http://x/a.xlsx", total_usd=total,
                            item_count=len(req.findings))

    ctx = FakeCtx(agents={"product_finder": finder, "insurance_filer": filer})
    run(coord.build_claim(ctx, USER, state))
    assert ctx.last_card_title() == "Claim package · $200.00"
    assert [f.value_basis for f in filed[0].findings] == ["estimate", "estimate", "needs_price"]
    assert ctx.payments() == []  # no fee for a claim package


# --- sending order (shared/uagents_patch) ------------------------------------------------------

def test_messages_to_one_conversation_keep_their_order_while_others_run_in_parallel():
    from uagents.communication import Dispenser
    from shared import uagents_patch

    order, started = [], []

    class Env:
        def __init__(self, target, session, name):
            self.target, self.session, self.name = target, session, name

    async def process(self, env, endpoints, future, sync):
        started.append(env.name)
        await asyncio.sleep(0.05 if env.name == "a1" else 0.01)
        order.append(env.name)
        future.set_result("ok")

    async def main():
        d = Dispenser()
        d._process_envelope = process.__get__(d)
        task = asyncio.create_task(uagents_patch._run(d))
        loop = asyncio.get_running_loop()
        futures = []
        for name, target in [("a1", "A"), ("a2", "A"), ("b1", "B")]:
            fut = loop.create_future()
            futures.append(fut)
            d.add_envelope(Env(target, "s1", name), ["http://x"], fut)
        await asyncio.gather(*futures)
        task.cancel()

    run(main())
    assert order.index("a1") < order.index("a2")  # same conversation: in order
    assert order.index("b1") < order.index("a1")  # another conversation didn't wait behind a1


def test_approve_for_another_mode_is_a_mode_switch(fake_stripe):
    """Live chain bug: "And list everything for insurance, replacement cost, ZIP 10001" on baby results
    came back as approve_plan(mode=claim) and started shopping for the baby fixes."""
    runs = []

    async def fake_intake(ctx, sender, state, selection, intro=""):
        runs.append(selection.get("mode"))

    ctx = FakeCtx()
    state = {"job_id": "j", "space_id": "s", "result": {"mode": "baby", "findings": []}, "answers": {}}
    orig = coord.on_intake
    coord.on_intake = fake_intake
    try:
        run(coord.route(ctx, USER, state, [], {"action": "approve_plan", "mode": "claim",
                                               "policy_type": "replacement_cost", "zip_code": "10001"},
                        "And list everything for insurance, replacement cost, ZIP 10001."))
    finally:
        coord.on_intake = orig
    assert runs == ["claim"] and ctx.payments() == []


def test_results_and_cart_are_written_out_in_the_message(fake_stripe):
    from agents.actions.cart.logic import build_cart

    async def fake_run_mode(ctx, state, mode, profile):
        return result("elder")

    ctx = FakeCtx()
    state = {"job_id": "j", "space_id": "sp1", "rooms": [], "frames": {"elder": "https://img"}, "answers": {}}
    orig = coord.run_mode
    coord.run_mode = fake_run_mode
    try:
        run(coord.on_intake(ctx, USER, state, {"mode": "elder", "mobility_aid": "walker"}))
    finally:
        coord.run_mode = orig
    assert any("- **Thing** (serious): Room · fix it" in t for t in ctx.texts())  # the finding and its fix

    async def finder(req):
        return FindProductsResult(job_id="j", ok=True, quotes=[ProductQuote(
            title="Grab bar 18 in", url="https://s/g", merchant="Walmart", price_usd=21.5, url_verified=True,
            finding_id="f1", specs={"quantity": 2, "role": "primary"})])

    async def cart_agent(req):
        return build_cart(req)

    ctx.agents = {"product_finder": finder, "cart": cart_agent}
    run(coord.shop(ctx, USER, state))
    line = "- [Grab bar 18 in](https://s/g): $21.50 × 2 at Walmart"
    assert any(line in t for t in ctx.texts())  # products with their store links, before paying
    # The payment request lists them too: ASI:One shows it right above its Pay button.
    from uagents_core.contrib.protocols.payment import RequestPayment
    request = next(m for _, m in ctx.sent if isinstance(m, RequestPayment))
    assert line in request.metadata["content"] and "4242" in request.metadata["content"]


def test_uploads_signal_rides_on_the_first_reply():
    """One chat message on the first turn, not two: ASI:One takes seconds to accept each one."""
    from datetime import datetime, timezone
    from uuid import uuid4
    from uagents_core.contrib.protocols.chat import ChatMessage, MetadataContent, StartSessionContent, TextContent

    ctx = FakeCtx(session="new-chat")
    msg = ChatMessage(timestamp=datetime.now(timezone.utc), msg_id=uuid4(),
                      content=[StartSessionContent(type="start-session"), TextContent(type="text", text="hi")])

    async def quiet(text, card):
        return {"action": "other"}

    orig = coord.understand
    coord.understand = quiet
    try:
        run(coord.on_chat(ctx, USER, msg))
    finally:
        coord.understand = orig
    chats = ctx.chats()
    assert len(chats) == 1  # the reply carries the uploads flag; no separate message
    assert any(isinstance(c, MetadataContent) and c.metadata.get("attachments") == "true" for c in chats[0].content)


def test_a_message_that_mentions_a_video_without_the_link_asks_for_the_link(ctx):
    """Live: the planner relayed "see uploaded video" with no link; "not a web link" made it shop elsewhere."""
    from agents.coordinator import agent as coord

    state = {}
    run(coord.route(ctx, USER, state, [], {"action": "choose_mode", "mode": "transform"},
                    "Transform their office (see uploaded video) into a home office, budget $600."))
    assert "didn't come through" in ctx.texts()[-1] and "direct video link" in ctx.texts()[-1]
    run(coord.route(ctx, USER, {}, [], {"action": "choose_mode", "mode": "elder"}, "Check my dad's house for falls."))
    assert "Please attach a 30-second video" in ctx.texts()[-1] and "web link" not in ctx.texts()[-1]


def test_a_child_age_on_elder_results_runs_the_baby_check():
    """Live: "now check the same house for my 1 year old" was relayed as "do BOTH" with mode=elder,
    and the elder results were shown again."""
    runs = []

    async def fake_intake(ctx, sender, state, selection, intro=""):
        runs.append(selection.get("mode"))

    def ask(answers, selection):
        state = {"job_id": "j", "space_id": "s", "result": {"mode": "elder", "findings": []}, "answers": answers}
        run(coord.route(FakeCtx(), USER, state, [], selection, "Analyze the same video for BOTH needs now."))

    async def fake_results(ctx, sender, state, intro=""):
        runs.append("shown again")

    orig, orig_results = coord.on_intake, coord.show_results
    coord.on_intake, coord.show_results = fake_intake, fake_results
    try:
        elder = {"age": "79", "mobility_aid": "cane", "budget_usd": "200"}
        ask(dict(elder), {"action": "choose_mode", "mode": "elder", "mobility_aid": "cane", "budget_usd": "200",
                          "child_age_months": "12"})
        assert runs == ["baby"]
        # The same child age restated after baby-proofing was already done isn't a new request.
        ask({**elder, "child_age_months": "12"}, {"action": "choose_mode", "mode": "elder", "budget_usd": "200",
                                                  "child_age_months": "12"})
        assert runs == ["baby", "shown again"]
    finally:
        coord.on_intake, coord.show_results = orig, orig_results


def test_a_reply_that_fails_to_deliver_is_sent_again(monkeypatch):
    """Live, while Agentverse was slow: an address lookup raised, and a send hit the time cap but arrived."""
    from shared import uagents_patch
    from uagents_core.types import DeliveryStatus, MsgStatus

    real_sleep = asyncio.sleep
    monkeypatch.setattr(coord.asyncio, "sleep", lambda s: real_sleep(0))

    class FlakyCtx(FakeCtx):
        def __init__(self, *failures):
            super().__init__()
            self.failures = list(failures)

        async def send(self, to, msg):
            self.sent.append((to, msg))
            if self.failures:
                failure = self.failures.pop(0)
                if isinstance(failure, Exception):
                    raise failure
                return MsgStatus(status=DeliveryStatus.FAILED, detail=failure, destination=to, endpoint="",
                                 session=None)
            return MsgStatus(status=DeliveryStatus.DELIVERED, detail="ok", destination=to, endpoint="", session=None)

    # A lookup error, then a failed request: neither left, so the same message goes again.
    ctx = FlakyCtx(ValueError("Almanac contract not found for testnet."), "Message delivery failed")
    run(coord.send(ctx, USER, coord.text_message("Found 7 hazards.")))
    assert len(ctx.sent) == 3 and len({m.msg_id for _, m in ctx.sent}) == 1
    assert any("delivered on attempt 3" in l for l in ctx.logger.lines)

    # Stopped at the time cap: it may have arrived (it did, live), so it isn't sent twice.
    ctx = FlakyCtx(uagents_patch.TIMEOUT_DETAIL)
    run(coord.send(ctx, USER, coord.text_message("Found 7 hazards.")))
    assert len(ctx.sent) == 1 and any("not resending" in l for l in ctx.logger.lines)

    # Never more than SEND_ATTEMPTS tries.
    ctx = FlakyCtx(*["Message delivery failed"] * 5)
    run(coord.send(ctx, USER, coord.text_message("Found 7 hazards.")))
    assert len(ctx.sent) == coord.SEND_ATTEMPTS


def test_a_reworded_person_label_is_still_a_repeat():
    """Live: "an 84-year-old man" came back as person="elder" with every other answer the same, and the
    elder check ran again instead of shopping."""
    state = {"result": {"mode": "elder"}, "answers": {"person": "man", "age": "84", "mobility_aid": "walker",
                                                      "night_trips": "true", "budget_usd": "300"}}
    restated = {"action": "submit_intake", "mode": "elder", "person": "elder", "age": "84", "mobility_aid": "walker",
                "night_trips": "true", "budget_usd": "300"}
    assert coord.repeats_answers(state, restated)
    assert not coord.repeats_answers(state, {**restated, "budget_usd": "500"})  # a real change still counts


def test_the_live_restated_intake_with_a_new_person_label_goes_to_the_cart():
    """The exact live turn (08:00): elder results shown, then the planner restated every answer with
    person "elder" instead of "man" and asked for fixes "so I can find products for each fix"."""
    went = []

    async def fake_shop(ctx, sender, state):
        went.append("shop")

    async def fake_intake(ctx, sender, state, selection, intro=""):
        went.append("intake")

    state = {"job_id": "j", "space_id": "s", "result": {"mode": "elder", "findings": []},
             "answers": {"person": "man", "age": "84", "budget_usd": "300", "mobility_aid": "walker",
                         "night_trips": "true"}}
    selection = {"action": "submit_intake", "mode": "elder", "age": "84", "budget_usd": "300",
                 "mobility_aid": "walker", "night_trips": "true", "person": "elder",
                 "requirements": "full fall-hazard analysis and prioritized list of budget-friendly fixes"}
    text = ("Hi, following up on our earlier conversation: the resident is an 84-year-old man who uses a walker "
            "and walks to the bathroom at night. Include walker clearance, night-path lighting, rugs and grab bars "
            "so I can find products for each fix.")
    orig = coord.shop, coord.on_intake
    coord.shop, coord.on_intake = fake_shop, fake_intake
    try:
        run(coord.route(FakeCtx(), USER, state, [], selection, text))
    finally:
        coord.shop, coord.on_intake = orig
    assert went == ["shop"]


def office_results_state():
    findings = [{"id": "transform_item_0", "title": "Add: Monitor ×2"}, {"id": "transform_item_1", "title": "Add: Keyboard and mouse"},
                {"id": "transform_keep_desk", "title": "Keep the light wood desk with brass legs"}]
    return {"result": {"mode": "transform", "findings": findings},
            "answers": {"goal": "modern home office", "room_id": "office", "style": "modern", "budget_usd": "600",
                        "requirements": "two monitors, keyboard and mouse"}}


def test_a_reworded_office_request_on_shown_results_is_a_repeat():
    """Live (fix 1): after the plan was shown, the planner sent the same request reworded ("dual-monitor
    setup", "$600", "modern style") with "equipment budget"; Maestro planned again instead of shopping."""
    state = office_results_state()
    reworded = {"action": "choose_mode", "mode": "transform", "goal": "home office", "room_id": "room_office",
                "style": "modern style", "budget_usd": "$600", "requirements": "dual-monitor setup, keyboard, mouse"}
    assert coord.repeats_answers(state, reworded)
    assert coord.SHOP_WORDS.search("total equipment budget $600")


def test_real_changes_to_an_office_plan_still_make_a_new_plan():
    state = office_results_state()
    base = {"action": "choose_mode", "mode": "transform", "goal": "home office", "room_id": "office", "budget_usd": "600"}
    assert not coord.repeats_answers(state, {**base, "budget_usd": "900"})                 # new budget
    assert not coord.repeats_answers(state, {**base, "room_id": "bedroom"})               # another room
    assert not coord.repeats_answers(state, {**base, "goal": "home gym"})                 # another goal
    assert not coord.repeats_answers(state, {**base, "requirements": "add a bookshelf"})  # an item not in the plan
    other = office_results_state()
    other["answers"]["goal"] = "reading nook"
    assert not coord.repeats_answers(other, {**base, "goal": "music studio"})


def test_the_reworded_repeat_with_equipment_goes_to_the_cart():
    went = []

    async def fake_shop(ctx, sender, state):
        went.append("shop")

    async def fake_intake(ctx, sender, state, selection, intro=""):
        went.append("intake")

    state = {"job_id": "j", "space_id": "s", **office_results_state()}
    state["result"]["findings"] = []
    state["result"]["findings"] = office_results_state()["result"]["findings"]
    selection = {"action": "choose_mode", "mode": "transform", "goal": "modern home office", "room_id": "office",
                 "budget_usd": "600", "requirements": "dual-monitor setup, keyboard, mouse", "style": "modern"}
    text = ("The user wants to turn their office into a modern home office with a two-monitor setup, keyboard and "
            "mouse, total equipment budget $600. Here is the video of the room.")
    orig = coord.shop, coord.on_intake
    coord.shop, coord.on_intake = fake_shop, fake_intake
    try:
        run(coord.route(FakeCtx(), USER, state, [], selection, text))
    finally:
        coord.shop, coord.on_intake = orig
    assert went == ["shop"]
