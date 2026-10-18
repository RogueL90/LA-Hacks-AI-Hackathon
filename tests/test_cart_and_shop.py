"""Cart Builder rules and the coordinator's approve -> products -> cart -> fee flow."""
import asyncio

from agents.actions.cart.logic import build_cart, merge_duplicates
from agents.coordinator import agent as coord
from shared.models import (CartRequest, Finding, FindProductsRequest, FindProductsResult, ModeResult, ProductQuery,
                           ProductQuote)
from tests.conftest import FakeCtx, USER


def run(coro):
    return asyncio.run(coro)


def quote(fid, url, price, role="primary", qty=1, verified=True, title=None):
    return ProductQuote(title=title or f"Product {fid}", url=url, merchant="Store", price_usd=price,
                        url_verified=verified, finding_id=fid, specs={"quantity": qty, "role": role})


# --- Cart Builder ----------------------------------------------------------------------------

def test_same_product_for_two_findings_is_one_line_with_quantity_two():
    items = merge_duplicates([quote("a", "https://s/seat", 30), quote("b", "https://s/seat", 30), quote("c", "https://s/x", 10)])
    assert [(i.url, i.specs["quantity"]) for i in items] == [("https://s/seat", 2), ("https://s/x", 1)]


def test_cart_keeps_primary_drops_its_backup_and_unverified():
    cart = build_cart(CartRequest(job_id="j", quotes=[
        quote("a", "https://s/1", 20), quote("a", "https://s/2", 25, role="backup"),
        quote("b", "https://s/3", 15, verified=False)]))
    assert [i.url for i in cart.items] == ["https://s/1"]


def test_backup_is_used_when_the_primary_is_missing():
    cart = build_cart(CartRequest(job_id="j", quotes=[quote("a", "https://s/2", 25, role="backup")]))
    assert [i.url for i in cart.items] == ["https://s/2"]


def test_budget_drops_lowest_priority_items_and_fee_is_flat():
    cart = build_cart(CartRequest(job_id="j", budget_usd=50, quotes=[
        quote("a", "https://s/1", 30), quote("b", "https://s/2", 15), quote("c", "https://s/3", 40)]))
    assert cart.subtotal_usd <= 50 and cart.within_budget
    assert [i.finding_id for i in cart.items] == ["a", "b"]  # the last (lowest priority) item went
    assert cart.service_fee_usd == "1.00"


def test_empty_cart_has_no_fee():
    cart = build_cart(CartRequest(job_id="j", quotes=[]))
    assert cart.items == [] and cart.service_fee_usd == "0.00"


def test_quantity_counts_in_the_subtotal():
    cart = build_cart(CartRequest(job_id="j", quotes=[quote("a", "https://s/1", 10, qty=3)]))
    assert cart.subtotal_usd == 30


# --- approve -> products -> cart -> fee --------------------------------------------------------

def plan_state():
    findings = [
        Finding(id="elder_grab_1", kind="hazard", title="No grab bar", severity=4, fix_summary="Install a grab bar",
                product_query=ProductQuery(query="grab bar 18 in")),
        Finding(id="elder_rug_1", kind="hazard", title="Loose rug", severity=3, fix_summary="Rug pad",
                product_query=ProductQuery(query="rug pad 5x8")),
        Finding(id="elder_path_1", kind="hazard", title="Chair blocks the path", severity=5, fix_summary="Move it"),
    ]
    result = ModeResult(job_id="job1", mode="elder", ok=True, summary="3 hazards", findings=findings)
    return {"job_id": "job1", "space_id": "sp1", "mode": "elder", "result": result.model_dump(), "result_id": "r1",
            "profile": {"budget_usd": 100.0}, "frames": {"elder": "https://img"}}


def shop_agents(searches):
    async def finder(req: FindProductsRequest):
        searches.append([q.query for q in req.queries])
        quotes = [quote(q.constraints["finding_id"], f"https://s/{q.constraints['finding_id']}", 20)
                  for q in req.queries]
        return FindProductsResult(job_id=req.job_id, ok=True, quotes=quotes)

    async def cart(req: CartRequest):
        return build_cart(req)

    return {"product_finder": finder, "cart": cart}


def test_approve_builds_a_cart_and_asks_for_the_fee_before_showing_it(fake_stripe):
    searches = []
    ctx = FakeCtx(agents=shop_agents(searches))
    state = plan_state()
    run(coord.shop(ctx, USER, state))
    assert searches == [["grab bar 18 in", "rug pad 5x8"]]  # only fixes that need buying, most severe first
    assert ctx.payments() == ["RequestPayment"]
    kinds = [type(m).__name__ for _, m in ctx.sent]
    assert kinds.index("RequestPayment") < kinds.index("ChatMessage")  # payment request first, then the card
    assert ctx.last_card_title().startswith("Your cart · 2 products")
    assert state["payment"]["fee"] == "1.00" and len(state["payment"]["stripe_sessions"]) == 1  # one checkout


def test_approve_uses_the_search_started_with_the_results(fake_stripe):
    searches = []
    ctx = FakeCtx(agents=shop_agents(searches))
    state = plan_state()

    async def flow():
        coord.prefetch(ctx, state)          # started when the results card was shown
        await coord.shop(ctx, USER, state)  # the user approves

    run(flow())
    assert len(searches) == 1  # no second search


def test_picked_fixes_only(fake_stripe):
    searches = []
    ctx = FakeCtx(agents=shop_agents(searches))
    state = {**plan_state(), "chosen_fixes": ["elder_rug_1"]}
    run(coord.shop(ctx, USER, state))
    assert searches == [["rug pad 5x8"]]


def test_approve_again_or_after_cancel_shows_the_same_cart_without_a_new_charge(fake_stripe):
    searches = []
    ctx = FakeCtx(agents=shop_agents(searches))
    state = plan_state()
    run(coord.shop(ctx, USER, state))
    for status in ("requested", "rejected"):
        state["payment"]["status"] = status
        run(coord.shop(ctx, USER, state))
        assert ctx.last_card_title().startswith("Your cart")
    assert fake_stripe["created"] == 1 and len(searches) == 1 and ctx.payments() == ["RequestPayment"]


def test_no_products_found_means_no_charge(fake_stripe):
    async def finder(req):
        return FindProductsResult(job_id=req.job_id, ok=True, quotes=[])

    async def cart(req):
        return build_cart(req)

    ctx = FakeCtx(agents={"product_finder": finder, "cart": cart})
    state = plan_state()
    run(coord.shop(ctx, USER, state))
    assert ctx.payments() == [] and fake_stripe["created"] == 0
    assert any("nothing to charge" in t for t in ctx.texts())


def test_cart_agent_down_uses_the_same_cart_rules_locally(fake_stripe):
    searches = []
    agents = shop_agents(searches)
    del agents["cart"]
    ctx = FakeCtx(agents=agents)
    state = plan_state()
    run(coord.shop(ctx, USER, state))
    assert ctx.last_card_title().startswith("Your cart · 2 products")


def test_no_plan_yet_means_no_charge(fake_stripe):
    ctx = FakeCtx()
    run(coord.shop(ctx, USER, {"job_id": "j"}))
    assert ctx.payments() == [] and fake_stripe["created"] == 0


def test_cart_says_what_it_left_out_for_budget_and_what_it_could_not_find(fake_stripe):
    async def finder(req):
        quotes = []
        for q in req.queries:
            fid = q.constraints["finding_id"]
            if fid == "elder_grab_1":
                quotes.append(quote(fid, "https://s/grab", 90))
            if fid == "elder_rug_1":
                quotes.append(quote(fid, "https://s/rug", 40))
        return FindProductsResult(job_id=req.job_id, ok=True, quotes=quotes)

    async def cart(req):
        return build_cart(req)

    ctx = FakeCtx(agents={"product_finder": finder, "cart": cart})
    state = {**plan_state(), "profile": {"budget_usd": 100.0}}
    run(coord.shop(ctx, USER, state))
    assert state["cart_notes"]["left_out"] == ["Rug pad"]  # $90 + $40 is over $100: the lower-priority fix went
    card = str(ctx.cards()[-1])
    assert "Left out to stay within budget: rug pad" in card


def test_price_cap_never_hides_a_real_product():
    """Live: monitors capped at $36 found nothing. A product over the cap is still offered, cheapest first."""
    from agents.actions.product_finder.search import choose_for_query
    from shared.models import ProductQuery
    q = ProductQuery(query="27 inch IPS monitor", max_price_usd=36, quantity=2, constraints={"finding_id": "m"})
    pool = [ProductQuote(title="Monitor A", url="https://s/a", merchant="S", price_usd=129.0, url_verified=True),
            ProductQuote(title="Monitor B", url="https://s/b", merchant="S", price_usd=99.0, url_verified=True)]
    chosen = choose_for_query(q, pool)
    assert [c.url for c in chosen] == ["https://s/b", "https://s/a"]
    assert "share of your budget" in chosen[0].fit_note
    under = choose_for_query(q.copy(update={"max_price_usd": 120}), pool)
    assert under[0].url == "https://s/b" and "share of your budget" not in under[0].fit_note


def test_cart_keeps_the_most_important_item_even_over_budget():
    cart = build_cart(CartRequest(job_id="j", budget_usd=50, quotes=[quote("a", "https://s/1", 90), quote("b", "https://s/2", 20)]))
    assert [i.finding_id for i in cart.items] == ["a"] and not cart.within_budget


def test_paying_without_tapping_anything_posts_the_receipt(fake_stripe, monkeypatch):
    """No "I've paid" button: the agent watches Stripe after the cart goes out."""
    monkeypatch.setattr(coord, "PAYMENT_POLL_FAST_S", 0.01)
    searches = []

    async def verifier(req):
        from agents.actions.payment_verifier.verify import VerifyPaymentResult
        return VerifyPaymentResult(job_id=req.job_id, ok=True, verified=req.transaction_id in fake_stripe["paid"],
                                   detail="test")

    agents = {**shop_agents(searches), "payment_verifier": verifier}
    ctx = FakeCtx(agents=agents)
    state = plan_state()

    async def flow():
        await coord.shop(ctx, USER, state)
        coord.save(ctx, USER, state)           # what on_chat does after each message
        assert ctx.last_card_title().startswith("Your cart")
        fake_stripe["paid"].add("cs_test_embedded_1")  # the user pays in the checkout; taps nothing else
        for _ in range(100):
            await asyncio.sleep(0.01)
            if ctx.last_card_title() == "Order placed (demo)":
                break

    run(flow())
    assert ctx.last_card_title() == "Order placed (demo)"
    assert coord.load(ctx, USER)["payment"]["status"] == "paid"


def test_the_cart_is_checked_out_as_an_itemized_demo_order(fake_stripe):
    searches = []
    ctx = FakeCtx(agents=shop_agents(searches))
    state = plan_state()
    run(coord.shop(ctx, USER, state))
    lines = fake_stripe["last_items"]
    assert [l["name"] for l in lines] == ["Product elder_grab_1", "Product elder_rug_1", "Maestro service fee"]
    assert fake_stripe["last_amount"] == "41.00"  # $20 + $20 products + $1 fee
    request = next(m for _, m in ctx.sent if type(m).__name__ == "RequestPayment")
    assert request.accepted_funds[0].amount == "41.00"
    assert state["payment"]["amount"] == "41.00" and state["payment"]["fee"] == "1.00"
    assert any("added them to your cart" in t and "**$41.00**" in t for t in ctx.texts())


def test_after_the_order_the_wrap_up_has_summary_orders_next_steps_and_the_3d_link(fake_stripe, monkeypatch):
    monkeypatch.setattr(coord, "PAYMENT_POLL_FAST_S", 0.01)

    async def verifier(req):
        from shared.models import VerifyPaymentResult
        return VerifyPaymentResult(job_id=req.job_id, ok=True, verified=req.transaction_id in fake_stripe["paid"], detail="t")

    ctx = FakeCtx(agents={**shop_agents([]), "payment_verifier": verifier})
    state = plan_state()
    state["result"]["viewer_url"] = "http://127.0.0.1:5173/s/sp1?mode=elder&o=ov1&live=1"

    async def flow():
        await coord.shop(ctx, USER, state)
        coord.save(ctx, USER, state)
        fake_stripe["paid"].add("cs_test_embedded_1")
        for _ in range(100):
            await asyncio.sleep(0.01)
            if ctx.last_card_title() == "Order placed (demo)":
                break

    run(flow())
    text = ctx.texts()[-1]
    assert "**Order placed (demo):** 2 products, $41.00 paid" in text
    assert "**Summary:** 3 hazards" in text
    assert "[Product elder_grab_1](https://s/elder_grab_1)" in text      # what was ordered, linked
    assert "**Next steps:**" in text and "No purchase needed: move it" in text  # the fix without a product
    assert "[Open your home in 3D](http://127.0.0.1:5173/s/sp1" in text
