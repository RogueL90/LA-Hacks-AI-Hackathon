"""Shared fakes for the fast tests: no network, no Agentverse, no real Stripe.

FakeCtx stands in for a uagents Context. It records everything the coordinator sends and
answers send_and_receive by calling the real logic of the agent being asked (Pranay's cart
and payment verifier code), so a test can run a whole flow in-process.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shared import config  # noqa: E402  (loads .env and the CA bundle first)
from uagents_core.contrib.protocols.chat import ChatMessage, MetadataContent, TextContent  # noqa: E402
from uagents_core.types import DeliveryStatus, MsgStatus  # noqa: E402

ADDRESSES = json.loads((ROOT / "shared" / "addresses.json").read_text())
USER = "agent1qtestuser000000000000000000000000000000000000000000000000000"


class FakeStorage:
    def __init__(self):
        self.data = {}

    def get(self, key):
        return json.loads(json.dumps(self.data.get(key))) if key in self.data else None

    def set(self, key, value):
        self.data[key] = json.loads(json.dumps(value))


class FakeLogger:
    def __init__(self):
        self.lines = []

    def _log(self, *args, **_):
        self.lines.append(" ".join(str(a) for a in args))

    info = warning = error = debug = exception = _log


class FakeCtx:
    """Records sent messages; `agents` maps an address key (e.g. "cart") to an async handler."""

    def __init__(self, agents=None, session="test-session"):
        self.storage = FakeStorage()
        self.logger = FakeLogger()
        self.session = session
        self.sent = []          # (to, message)
        self.asked = []         # (agent key, request)
        self.agents = agents or {}

    async def send(self, to, msg):
        self.sent.append((to, msg))
        return MsgStatus(status=DeliveryStatus.DELIVERED, detail="ok", destination=to, endpoint="", session=None)

    async def send_and_receive(self, to, request, response_type, timeout=30):
        key = next((k for k, v in ADDRESSES.items() if v == to), to)
        self.asked.append((key, request))
        handler = self.agents.get(key)
        failed = MsgStatus(status=DeliveryStatus.FAILED, detail="no answer", destination=to, endpoint="", session=None)
        if handler is None:
            return None, failed
        return await handler(request), MsgStatus(status=DeliveryStatus.DELIVERED, detail="ok", destination=to,
                                                  endpoint="", session=None)

    # What the user saw
    def chats(self):
        return [m for _, m in self.sent if isinstance(m, ChatMessage)]

    def texts(self):
        return [c.text for m in self.chats() for c in m.content if isinstance(c, TextContent)]

    def cards(self):
        out = []
        for m in self.chats():
            for c in m.content:
                if isinstance(c, MetadataContent) and "card_kind" in c.metadata:
                    out.append({"kind": c.metadata["card_kind"], "payload": json.loads(c.metadata["card_payload"])})
        return out

    def last_card_title(self):
        cards = self.cards()
        if not cards:
            return ""
        p = cards[-1]["payload"]
        return p.get("title") or (p.get("root") or {}).get("title") or ""

    def payments(self):
        return [type(m).__name__ for _, m in self.sent if not isinstance(m, ChatMessage)]


@pytest.fixture
def ctx():
    return FakeCtx()


@pytest.fixture
def fake_stripe(monkeypatch):
    """Stripe test-mode stand-in: checkouts get fake ids; `paid` decides which are paid."""
    from shared import stripe_pay

    state = {"paid": set(), "created": 0, "lookups": [], "fail_lookup": False}

    async def create_checkout(reference, description, amount_usd="1.00"):
        state["created"] += 1
        n = state["created"]
        return {
            "embedded": {"ui_mode": "embedded", "publishable_key": "pk_test_x", "client_secret": f"cs_secret_{n}",
                         "checkout_session_id": f"cs_test_embedded_{n}", "currency": "usd",
                         "amount_cents": str(round(float(amount_usd) * 100))},
            "embedded_id": f"cs_test_embedded_{n}",
            "hosted_id": f"cs_test_hosted_{n}",
            "hosted_url": f"https://checkout.stripe.com/c/pay/cs_test_hosted_{n}",
        }

    async def is_paid(session_id, expected_usd=None):
        state["lookups"].append(session_id)
        if state["fail_lookup"]:
            raise RuntimeError("Stripe is unreachable")
        return session_id in state["paid"]

    monkeypatch.setattr(stripe_pay, "create_checkout", create_checkout)
    monkeypatch.setattr(stripe_pay, "is_paid", is_paid)
    monkeypatch.setattr(stripe_pay, "enabled", lambda: True)
    return state


@pytest.fixture(autouse=True)
def fresh_payment_memory():
    """The coordinator remembers confirmed payments per conversation; each test starts clean."""
    from agents.coordinator import agent as coord

    coord.CONFIRMED.clear()
    coord.RECEIPTS.clear()
    coord.VERIFY_LOCKS.clear()
    yield
