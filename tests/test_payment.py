"""Payment Verifier and the coordinator's "I've paid" check, including the bugs seen live:
- the verifier was asked about both checkouts at once and both answers were the first reply,
  so a paid Pay-link checkout read as unpaid;
- cancelling ASI:One's payment popup dropped the checkouts, so a later Pay-link payment
  couldn't be verified.
"""
import asyncio

import pytest

from agents.actions.payment_verifier import verify as verifier
from agents.coordinator import agent as coord
from shared import payments
from shared.models import CartResult, ProductQuote, VerifyPaymentRequest
from tests.conftest import FakeCtx, USER


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def verifier_agent(monkeypatch, fake_stripe):
    """Pranay's real verify_payment, with Stripe's Checkout Session lookup faked."""
    def check(session_id, fee):
        paid = session_id in fake_stripe["paid"]
        return paid, f"Stripe test mode, not a real charge. Checkout Session {session_id}. paid={paid}"

    monkeypatch.setattr(verifier, "verify_checkout_session", check)
    calls = []

    async def handle(req: VerifyPaymentRequest):
        calls.append(req.transaction_id)
        return await verifier.verify_payment(req)

    handle.calls = calls
    return handle


def cart_state(ctx, fake_stripe, status="requested"):
    """A conversation that has a cart and two open checkouts (in ASI:One and the Pay link)."""
    quote = ProductQuote(title="Grab bar", url="https://store.example/grab-bar", merchant="Store", price_usd=24.0,
                         url_verified=True, finding_id="elder_grab_1", specs={"quantity": 1, "role": "primary"})
    cart = CartResult(job_id="job1", ok=True, items=[quote], subtotal_usd=24.0, service_fee_usd="1.00",
                      checkout_links=[quote.url])
    state = {"job_id": "job1", "cart": cart.model_dump(), "payment": {
        "status": status, "fee": "1.00", "reference": "job1",
        "stripe_sessions": ["cs_test_embedded_1", "cs_test_hosted_1"],
        "checkout_url": "https://checkout.stripe.com/c/pay/cs_test_hosted_1"}}
    return state


# --- Pranay's verifier ---------------------------------------------------------------------

def test_verifier_checks_the_checkout_session_the_user_paid(verifier_agent, fake_stripe):
    fake_stripe["paid"].add("cs_test_hosted_1")
    res = run(verifier.verify_payment(VerifyPaymentRequest(job_id="j", service_fee_usd="1.00",
                                                           transaction_id="cs_test_hosted_1")))
    assert res.ok and res.verified


def test_verifier_says_unpaid_for_an_open_checkout(verifier_agent, fake_stripe):
    res = run(verifier.verify_payment(VerifyPaymentRequest(job_id="j", service_fee_usd="1.00",
                                                           transaction_id="cs_test_embedded_1")))
    assert res.ok and not res.verified


def test_verifier_without_a_session_charges_the_test_card(monkeypatch):
    intent = {"id": "pi_1", "status": "succeeded", "currency": "usd", "amount": 100}
    monkeypatch.setattr(verifier, "charge_test_fee", lambda fee, job_id=None: intent)
    res = run(verifier.verify_payment(VerifyPaymentRequest(job_id="j", service_fee_usd="1.00")))
    assert res.verified and "pi_1" in res.detail


def test_verifier_refuses_live_keys(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_not_allowed")
    with pytest.raises(payments.StripeKeyError):
        payments.require_test_secret()


def test_checkout_session_check_needs_paid_usd_and_the_exact_fee(monkeypatch):
    class Session:
        def __init__(self, status, currency, amount):
            self.payment_status, self.currency, self.amount_total = status, currency, amount

    class Client:
        session = None

        def __init__(self, key):
            self.v1 = self
            self.checkout = self
            self.sessions = self

        def retrieve(self, sid):
            return Client.session

    import stripe
    monkeypatch.setattr(stripe, "StripeClient", Client)
    for session, expected in [(Session("paid", "usd", 100), True), (Session("unpaid", "usd", 100), False),
                              (Session("paid", "usd", 50), False), (Session("paid", "eur", 100), False)]:
        Client.session = session
        assert payments.verify_checkout_session("cs_test_x", "1.00", secret_key="sk_test_x")[0] is expected


# --- the coordinator's "I've paid" ---------------------------------------------------------

def test_paid_pay_link_is_found_and_confirmed_once(verifier_agent, fake_stripe):
    """The live bug: the Pay-link checkout was paid, the one inside ASI:One wasn't."""
    ctx = FakeCtx(agents={"payment_verifier": verifier_agent})
    state = cart_state(ctx, fake_stripe)
    fake_stripe["paid"].add("cs_test_hosted_1")
    run(coord.check_payment(ctx, USER, state))
    assert state["payment"]["status"] == "paid"
    assert ctx.last_card_title() == "Payment received"
    assert verifier_agent.calls == ["cs_test_hosted_1"]  # one request, for the paid checkout
    assert "https://store.example/grab-bar" in str(ctx.cards()[-1])  # the receipt has the store link


def test_nothing_paid_means_no_receipt_and_no_verifier_call(verifier_agent, fake_stripe):
    ctx = FakeCtx(agents={"payment_verifier": verifier_agent})
    state = cart_state(ctx, fake_stripe)
    run(coord.check_payment(ctx, USER, state))
    assert state["payment"]["status"] == "requested"
    assert any("don't see the payment" in t for t in ctx.texts()) or "One step left" in ctx.last_card_title()
    assert verifier_agent.calls == []


def test_stripe_unreachable_falls_back_to_the_verifier_for_each_checkout(verifier_agent, fake_stripe):
    ctx = FakeCtx(agents={"payment_verifier": verifier_agent})
    state = cart_state(ctx, fake_stripe)
    fake_stripe["paid"].add("cs_test_hosted_1")
    fake_stripe["fail_lookup"] = True
    run(coord.check_payment(ctx, USER, state))
    assert state["payment"]["status"] == "paid"
    assert verifier_agent.calls == ["cs_test_embedded_1", "cs_test_hosted_1"]  # one after the other


def test_verifier_down_trusts_stripe(fake_stripe):
    ctx = FakeCtx(agents={})  # Payment Verifier doesn't answer
    state = cart_state(ctx, fake_stripe)
    fake_stripe["paid"].add("cs_test_embedded_1")
    run(coord.check_payment(ctx, USER, state))
    assert state["payment"]["status"] == "paid"


def test_forged_session_is_refused(verifier_agent, fake_stripe):
    ctx = FakeCtx(agents={"payment_verifier": verifier_agent})
    state = cart_state(ctx, fake_stripe)
    fake_stripe["paid"].add("cs_test_someone_else")
    assert run(coord.verify_paid(ctx, state, "cs_test_someone_else")) is False
    assert verifier_agent.calls == []


def test_cancelled_popup_keeps_checkouts_so_the_pay_link_still_works(verifier_agent, fake_stripe):
    """The live bug: RejectPayment ("user-denied") wiped the checkouts."""
    from uagents_core.contrib.protocols.payment import RejectPayment

    ctx = FakeCtx(agents={"payment_verifier": verifier_agent})
    state = cart_state(ctx, fake_stripe)
    coord.save(ctx, USER, state)
    run(coord.on_reject(ctx, USER, RejectPayment(reason="user-denied")))
    after = coord.load(ctx, USER)
    assert after["payment"]["status"] == "rejected"
    assert after["payment"]["stripe_sessions"] == ["cs_test_embedded_1", "cs_test_hosted_1"]
    fake_stripe["paid"].add("cs_test_hosted_1")
    run(coord.check_payment(ctx, USER, after))
    assert after["payment"]["status"] == "paid"


def test_commit_payment_from_asi_one_completes_only_when_paid(verifier_agent, fake_stripe):
    from uagents_core.contrib.protocols.payment import CommitPayment, Funds

    ctx = FakeCtx(agents={"payment_verifier": verifier_agent})
    state = cart_state(ctx, fake_stripe)
    commit = CommitPayment(funds=Funds(currency="USD", amount="1.00", payment_method="stripe"),
                           recipient="me", transaction_id="cs_test_embedded_1")
    run(coord.settle_commit(ctx, USER, state, commit))
    assert ctx.payments() == ["CancelPayment"]
    fake_stripe["paid"].add("cs_test_embedded_1")
    run(coord.settle_commit(ctx, USER, state, commit))
    assert ctx.payments()[-1] == "CompletePayment" and state["payment"]["status"] == "paid"
