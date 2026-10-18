"""Cross-process chain tests against the LIVE agents (run/start.sh must be running).

Test users run in their own process with a local endpoint, so every message goes over the
network: user -> Last Mile Home -> (Agentverse mailboxes) -> Space Builder / specialists ->
back. Afterwards the live logs are checked to confirm which specialist handled each job and
that no fallback path was used.

Run: .venv/bin/python -m scripts.chain_tests [case-number ...]
Never import agent modules here: an imported Agent registers with this process's dispatcher
and would swallow messages meant for the live agents.
"""
import asyncio
import json
import os
import secrets
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from shared import config, uagents_patch
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
    Funds,
    RequestPayment,
    payment_protocol_spec,
)

ADDR = json.loads((config.ROOT / "shared" / "addresses.json").read_text())
COORD = ADDR["coordinator"]
PORT = 8298
# A 32 s walkthrough of a two-floor home (12 rooms), served by the local Space Service.
# (The ASI:One test clip used before shows one room and a face, which can't exercise the checks.)
VIDEO = os.getenv("CHAIN_VIDEO", "http://127.0.0.1:8300/files/media/394e1fd9945b.mp4")
PHOTOS = [f"http://127.0.0.1:8300/files/media/{name}.jpg" for name in ("8f97ba84e891", "94694eb03dfb", "e382c96aa08f")]


@dataclass
class Reply:
    texts: list[str] = field(default_factory=list)
    cards: list[dict] = field(default_factory=list)
    payments: list[str] = field(default_factory=list)
    stripe_session: str | None = None
    seconds: float = 0.0

    @property
    def text(self) -> str:
        return " ".join(self.texts)

    def card(self, kind: str | None = None) -> dict | None:
        return next((c for c in self.cards if kind is None or c["kind"] == kind), None)

    def title(self) -> str:
        c = self.card()
        if not c:
            return ""
        p = c["payload"]
        return p.get("title") or (p.get("root") or {}).get("title") or ""

    def form_fields(self) -> list[str]:
        f = self.card("form")
        return [x["name"] for x in f["payload"]["fields"]] if f else []

    def picker(self) -> list[str]:
        c = self.card("custom")
        if not c:
            return []
        grid = next((n for n in c["payload"]["root"].get("children", []) if n.get("type") == "choice_grid"), None)
        return [ch["value"] for ch in grid["choices"]] if grid else []

    def describe(self) -> str:
        cards = ", ".join(f"{c['kind']}:{self.title()}" for c in self.cards) or "no card"
        pays = f" payments={self.payments}" if self.payments else ""
        return f"{self.seconds:4.1f}s [{cards}]{pays} {self.text[:150]!r}"


def chat(text: str = "", links: list[str] | None = None, start: bool = False, resource: str | None = None) -> ChatMessage:
    body = f"@{COORD} {text}".strip()
    for url in links or []:
        body += f"\n\n![upload]({url})"
    content = [StartSessionContent(type="start-session")] if start else []
    content.append(TextContent(type="text", text=body))
    if resource:
        content.append(ResourceContent(resource_id=uuid4(), resource=Resource(
            uri=resource, metadata={"mime_type": "video/quicktime", "description": "home.mov"})))
    return ChatMessage(timestamp=datetime.now(timezone.utc), msg_id=uuid4(), content=content)


def tap(**selection) -> ChatMessage:
    return chat(json.dumps(selection))


ELDER_WALKER = {"person": "Mom", "age": "81", "mobility_aid": "walker", "night_trips": True, "budget_usd": "250"}

# Each case: (title, expected specialists, steps). A step is (message or callable(prev_reply) -> message, check).
CASES = {
    1: ("Elder, walker, full answers up front (ResourceContent upload)", {"elder"}, [
        (chat("My mom is 81, uses a walker and gets up at night. Check her place for fall risks, budget $250.",
              start=True, resource=VIDEO),
         lambda r: (r.title().startswith("Elder safety"), "results straight away")),
    ]),
    2: ("Elder, wheelchair: wider clearance rules", {"elder"}, [
        (chat("Here's my grandfather's apartment.", [VIDEO], start=True),
         lambda r: (r.card("carousel") is not None, "mode menu")),
        (tap(action="choose_mode", mode="elder"), lambda r: ("mobility_aid" in r.form_fields(), "elder questions")),
        (tap(action="submit_intake", mode="elder", person="Grandpa", age="88", mobility_aid="wheelchair",
             night_trips=False, budget_usd="500"),
         lambda r: (r.title().startswith("Elder safety") and ("needs 36 in" in json.dumps(r.cards) or "needs 32 in" in json.dumps(r.cards)),
                    "wheelchair clearances applied (ADA: 32 in doors, 36 in paths)")),
    ]),
    3: ("Elder, no aid, no night trips: fewer findings", {"elder"}, [
        (chat("Check my aunt's flat for fall risks. She's 70, walks fine, sleeps through the night.", [VIDEO], start=True),
         lambda r: (r.title().startswith("Elder safety") or "mobility_aid" in r.form_fields(), "elder results or questions")),
        (tap(action="submit_intake", mode="elder", age="70", mobility_aid="none", night_trips=False),
         lambda r: (r.title().startswith("Elder safety") and "night lighting" not in json.dumps(r.cards).lower(),
                    "no night-light finding when there are no night trips")),
    ]),
    4: ("Baby, 3 months, via card taps", {"baby"}, [
        (chat("Baby-proofing for my newborn's home please.", [VIDEO], start=True),
         lambda r: ("child_age_months" in r.form_fields() or r.title().startswith("Baby-proofing"),
                    "baby questions, or results when \"newborn\" already gives the age")),
        (tap(action="submit_intake", mode="baby", child_age_months=3, budget_usd=200),
         lambda r: (r.title().startswith("Baby-proofing") and len(r.picker()) > 0, "baby results with fix picker")),
    ]),
    5: ("Baby, 18 months, three photos instead of a video", {"baby"}, [
        (chat("My toddler is 18 months. What should I baby-proof? Three photos attached.", PHOTOS, start=True),
         lambda r: (r.title().startswith("Baby-proofing"), "baby results from photos")),
    ]),
    6: ("Transformer: bedroom -> home office", {"transformer"}, [
        (chat("Turn the bedroom into a home office, warm modern, two monitors, budget $900.", [VIDEO], start=True),
         lambda r: (r.title().startswith("Space transformer"), "office plan")),
    ]),
    7: ("Transformer: living room -> home gym", {"transformer"}, [
        (chat("I want a home gym in the living room, budget about $600.", [VIDEO], start=True),
         lambda r: (r.title().startswith("Space transformer") and "gym" in r.text.lower(), "gym plan for the living room")),
    ]),
    8: ("Transformer: nursery, then a room that doesn't exist, then a real one", {"transformer"}, [
        (chat("Make a nursery in the attic please.", [VIDEO], start=True),
         lambda r: ("attic" in r.text.lower() and "room_id" in r.form_fields(), "asks for a real room")),
        (chat("OK, the bedroom then."),
         lambda r: (r.title().startswith("Space transformer") and "nursery" in r.text.lower(), "nursery plan for the bedroom")),
    ]),
    9: ("Claim: replacement cost", {"claim"}, [
        (chat("We had a burst pipe. I need an insurance inventory, replacement cost policy, ZIP 90024.", [VIDEO], start=True),
         lambda r: (r.title().startswith("Insurance claim"), "claim inventory")),
    ]),
    10: ("Claim in Spanish, actual cash value", {"claim"}, [
        (chat("Necesito un inventario para mi seguro. Póliza de valor real en efectivo, código postal 94110.", [VIDEO], start=True),
         lambda r: (r.title().startswith("Insurance claim") or "policy_type" in r.form_fields(), "claim inventory or questions")),
    ]),
    11: ("One home, three checks in a row (elder -> baby -> claim)", {"elder", "baby", "claim"}, [
        (chat("Here's our house.", [VIDEO], start=True), lambda r: (r.card("carousel") is not None, "mode menu")),
        (tap(action="submit_intake", mode="elder", mobility_aid="cane", night_trips=True),
         lambda r: (r.title().startswith("Elder safety"), "elder results")),
        (chat("Now check it for my 1-year-old too."),
         lambda r: (r.title().startswith("Baby-proofing") or "child_age_months" in r.form_fields(), "baby check")),
        (tap(action="submit_intake", mode="baby", child_age_months=12),
         lambda r: (r.title().startswith("Baby-proofing"), "baby results")),
        (chat("And list everything for insurance, replacement cost, ZIP 10001."),
         lambda r: (r.title().startswith("Insurance claim"), "claim inventory, same home")),
    ]),
    12: ("Pick fixes -> products -> cart -> pay link; forged and unpaid payments", {"elder", "product_finder", "cart"}, [
        (chat("Fall check for my dad: 79, walker, up at night.", [VIDEO], start=True),
         lambda r: (len(r.picker()) > 0, "results with fix picker")),
        (lambda prev: tap(action="approve_plan", fix_ids=prev.picker()[:2]),
         lambda r: ("RequestPayment" in r.payments and r.title().startswith("Your cart")
                    and "checkout.stripe.com" in json.dumps(r.cards), "products found -> cart + Stripe fee request")),
        ("commit:cs_test_forged_session_123", lambda r: ("CancelPayment" in r.payments, "forged session refused")),
        ("commit:REAL", lambda r: ("CancelPayment" in r.payments, "real but unpaid session refused")),
        (tap(action="check_payment"), lambda r: ("don't see the payment" in r.text.lower(), "I've paid without paying is caught")),
        (tap(action="show_results"), lambda r: (r.title().startswith("Elder safety"), "results can be reopened")),
        (tap(action="approve_plan"), lambda r: (r.title().startswith("Your cart") and "RequestPayment" not in r.payments,
                                                "approve again shows the same cart without a new search or charge")),
    ]),
    13: ("Hazard details and navigation", {"baby"}, [
        (chat("Baby check, she's 9 months.", [VIDEO], start=True), lambda r: (len(r.picker()) > 0, "baby results")),
        (lambda prev: tap(action="finding_detail", finding_id=prev.picker()[0]),
         lambda r: (r.card("detail") is not None, "detail card")),
        (tap(action="show_modes"), lambda r: (r.card("carousel") is not None, "back to the mode menu")),
    ]),
}
_seen: dict = {}  # case 15: whether the package came straight back or arrives later

CASES.update({
    15: ("Claim: inventory -> prices -> claim package", {"claim", "product_finder", "insurance_filer"}, [
        (chat("Water damage claim. Replacement cost policy, ZIP 90024. Inventory everything.", [VIDEO], start=True),
         lambda r: (r.title().startswith("Insurance claim"), "claim inventory")),
        (tap(action="approve_plan"),
         lambda r: (_seen.__setitem__("pkg", r.title().startswith("Claim package")) or
                    ((_seen["pkg"] or "pricing" in r.text.lower()) and not r.payments), "package (or pricing note), no fee")),
        ("wait", lambda r: (_seen["pkg"] or (r.title().startswith("Claim package") and "redirect" in json.dumps(r.cards)),
                            "claim package card with download links")),
        (chat("Can I get the claim package again?"), lambda r: (r.title().startswith("Claim package"), "package can be reopened")),
    ]),
    16: ("Transformer: shop for the new room within budget", {"transformer", "product_finder", "cart"}, [
        (chat("Turn the bedroom into a home office, modern, budget $600.", [VIDEO], start=True),
         lambda r: (r.title().startswith("Space transformer"), "transformer plan")),
        (lambda prev: tap(action="approve_plan", fix_ids=prev.picker()),
         lambda r: ((r.title().startswith("Your cart") and "RequestPayment" in r.payments)
                    or "couldn't confirm a product page" in r.text, "cart with fee, or an honest no-result")),
    ]),
})
# 14: three users at once, each in a different mode (concurrency + isolation).
PARALLEL = {
    14: [("Parallel elder", "elder", "Fall check, she's 85 with a walker.", lambda r: r.title().startswith("Elder safety")),
         ("Parallel transformer", "transformer", "Turn the bedroom into a guest room, budget $700.",
          lambda r: r.title().startswith("Space transformer")),
         ("Parallel claim", "claim", "Insurance inventory please, replacement cost, ZIP 60601.",
          lambda r: r.title().startswith("Insurance claim"))],
}

results: dict[str, list] = {}
EXPECTED: dict[str, set] = {}


def make_user(name: str, steps: list, delay: float = 30) -> Agent:
    user = Agent(name=f"chain-{name[:20]}", seed=f"lmh-chain-{secrets.token_hex(8)}")
    inbox: asyncio.Queue = asyncio.Queue()
    chat_proto = Protocol(spec=chat_protocol_spec)
    pay = Protocol(spec=payment_protocol_spec, role="buyer")
    state = {"session": None}

    @chat_proto.on_message(ChatMessage)
    async def on_chat(ctx: Context, sender: str, m: ChatMessage):
        await ctx.send(sender, ChatAcknowledgement(timestamp=datetime.now(timezone.utc), acknowledged_msg_id=m.msg_id))
        await inbox.put(m)

    @chat_proto.on_message(ChatAcknowledgement)
    async def on_ack(ctx: Context, sender: str, m: ChatAcknowledgement):
        pass

    for model in (RequestPayment, CompletePayment, CancelPayment):
        @pay.on_message(model)
        async def on_pay(ctx: Context, sender: str, m, _model=model):
            await inbox.put(m)

    async def collect(timeout: float = 120, quiet: float = 3.0) -> Reply:
        reply, t0 = Reply(), time.time()

        def meaningful(m) -> bool:
            # Skip signals like {"attachments": "true"}: no text, no card, not a payment message.
            if not isinstance(m, ChatMessage):
                return True
            return any(isinstance(c, TextContent) or (isinstance(c, MetadataContent) and "card_kind" in c.metadata)
                       for c in m.content)

        while True:
            remaining = timeout - (time.time() - t0)
            try:
                first = await asyncio.wait_for(inbox.get(), max(remaining, 0.1))
            except asyncio.TimeoutError:
                reply.seconds = time.time() - t0
                return reply
            if meaningful(first):
                break
        pending = [first]
        reply.seconds = time.time() - t0
        while True:
            for m in pending:
                if isinstance(m, ChatMessage):
                    for c in m.content:
                        if isinstance(c, TextContent):
                            reply.texts.append(c.text)
                        elif isinstance(c, MetadataContent) and "card_kind" in c.metadata:
                            reply.cards.append({"kind": c.metadata["card_kind"], "payload": json.loads(c.metadata["card_payload"])})
                else:
                    reply.payments.append(type(m).__name__)
                    if isinstance(m, RequestPayment):
                        reply.stripe_session = ((m.metadata or {}).get("stripe") or {}).get("checkout_session_id")
            try:
                nxt = await asyncio.wait_for(inbox.get(), quiet)
                pending = [nxt] if meaningful(nxt) else []
            except asyncio.TimeoutError:
                return reply

    @user.on_event("startup")
    async def run(ctx: Context):
        async def scenario():
            await asyncio.sleep(delay)  # let this test user's Almanac registration land, and stagger starts
            outcome, prev, stripe_session = [], Reply(), None
            for i, (message, check) in enumerate(steps, 1):
                if isinstance(message, str) and message.startswith("commit:"):
                    tx = message.split(":", 1)[1]
                    tx = (stripe_session or "missing") if tx == "REAL" else tx
                    await ctx.send(COORD, CommitPayment(funds=Funds(currency="USD", amount="1.00", payment_method="stripe"),
                                                        recipient=COORD, transaction_id=tx))
                elif message == "wait":
                    pass  # nothing to send: the reply to the previous step arrives later
                else:
                    try:
                        outgoing = message(prev) if callable(message) else message
                    except Exception as exc:
                        outcome.append((i, False, f"could not build step from previous reply: {exc!r}", prev.describe()))
                        break
                    await ctx.send(COORD, outgoing)
                reply = await collect()
                stripe_session = reply.stripe_session or stripe_session
                try:
                    ok, note = check(reply)
                except Exception as exc:
                    ok, note = False, f"check crashed: {exc!r}"
                outcome.append((i, ok, note, reply.describe()))
                prev = reply if reply.cards else prev
            results[name] = outcome
        asyncio.get_running_loop().create_task(scenario())

    user.include(chat_proto)
    user.include(pay)
    return user


def main():
    wanted = [int(a) for a in sys.argv[1:]] or sorted({**CASES, **PARALLEL})
    users = []
    for n in wanted:
        if n in CASES:
            title, expected, steps = CASES[n]
            key = f"{n:02d} {title}"
            EXPECTED[key] = expected
            users.append(make_user(key, steps, delay=30 + 8 * len(users)))  # ~4 builds at a time, not 16
        for name, mode, text, ok in PARALLEL.get(n, []):
            key = f"{n:02d} {name}"
            EXPECTED[key] = {mode}
            # Under load a build can outlast the 50 s ASI:One wait: the agent says "Still mapping" and
            # posts the results when they're ready, so the second step listens for that delivery.
            seen = {}
            users.append(make_user(key, [
                (chat(text, [VIDEO], start=True),
                 lambda r, ok=ok, mode=mode, seen=seen: (seen.__setitem__("done", ok(r)) or
                                                         seen["done"] or "still mapping" in r.text.lower(),
                                                         f"{mode} results, or a promise to post them")),
                ("wait", lambda r, ok=ok, mode=mode, seen=seen: (seen["done"] or ok(r), f"{mode} results delivered")),
            ], delay=30 + 8 * len(CASES)))  # the three parallel users start together
    started = time.strftime("%H:%M:%S")
    bureau = Bureau(port=PORT, endpoint=[f"http://127.0.0.1:{PORT}/submit"])
    for u in users:
        bureau.add(u)

    async def reporter():
        deadline = time.time() + 15 * 60
        while len(results) < len(users) and time.time() < deadline:
            await asyncio.sleep(1)
        for key in EXPECTED:
            results.setdefault(key, [(0, False, "did not finish before the deadline", "")])
        total = passed = 0
        for key in sorted(results):
            print(f"\n### {key}   (expects: {', '.join(sorted(EXPECTED[key]))})")
            for i, ok, note, seen in results[key]:
                total += 1
                passed += ok
                print(f"  {'PASS' if ok else 'FAIL'} step {i}: {note}\n        {seen}")
        print(f"\nCHAIN TESTS DONE: {passed}/{total} steps passed (started {started})", flush=True)
        os._exit(0 if passed == total else 1)  # the Bureau never stops on its own

    bureau._loop.create_task(reporter())
    bureau.run()


if __name__ == "__main__":
    uagents_patch.apply()
    main()
