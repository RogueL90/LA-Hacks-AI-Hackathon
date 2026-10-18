"""See your cart in your home: cart items placed in the 3D model before you buy."""
import asyncio
import math

import pytest

from agents.coordinator import cart_preview as cp
from shared.models import CartResult, Door, Finding, ProductQuery, ProductQuote, Room, Space, SpaceObject


def home():
    rooms = [Room(id="bath", name="Bathroom", polygon=[[0, 0], [3, 0], [3, 2.5], [0, 2.5]]),
             Room(id="office", name="Office", polygon=[[3, 0], [7, 0], [7, 4], [3, 4]]),
             Room(id="stairs", name="Stairs", polygon=[[0, 3], [2, 3], [2, 7], [0, 7]])]
    objects = [
        SpaceObject(id="toilet", type="toilet", label="toilet", room_id="bath", position=[1.0, 0.38, 0.35],
                    size=[0.4, 0.75, 0.7]),
        SpaceObject(id="stair", type="stairs", label="stairs", room_id="stairs", position=[1.0, 1.3, 5.0],
                    size=[0.9, 2.6, 3.0]),
        SpaceObject(id="desk", type="desk", label="desk", room_id="office", position=[5.0, 0.375, 0.32],
                    size=[1.3, 0.75, 0.65]),
        SpaceObject(id="out1", type="outlet", label="outlet", room_id="office", position=[3.01, 0.3, 2.0],
                    size=[0.07, 0.11, 0.02], rotation_y=math.pi / 2),
    ]
    return Space(space_id="sp", source_type="video", rooms=rooms, doors=[Door(id="d", room_id="bath", position=[2.9, 1, 1.2], width_m=0.8)],
                 objects=objects, scale_method="prebuilt", scale_confidence=1, viewer_url="", snapshot_url="")


def finding(fid, query, objects=(), qty=1):
    return Finding(id=fid, kind="hazard", title=fid, object_ids=list(objects), fix_summary="Fix it",
                   product_query=ProductQuery(query=query, quantity=qty))


def quote(fid, title, qty=1):
    return ProductQuote(title=title, url=f"https://store.example/{fid}", merchant="Store", price_usd=25.0,
                        finding_id=fid, specs={"quantity": qty})


def place(findings, quotes, room=None):
    cart = CartResult(job_id="j", ok=True, items=quotes, subtotal_usd=0, checkout_links=[])
    return [g.data for g in cp.ghosts(home(), cart, findings, room)]


def test_kinds_come_from_the_search_words_first():
    assert cp.kind_of("toilet grab bar 18 in", "Moen bar")[0] == "grab_bar"
    assert cp.kind_of("bookshelf", "Wooden display shelves")[0] == "bookshelf"
    assert cp.kind_of("", "Logitech MK270 Wireless Keyboard and Mouse Combo")[0] == "keyboard_mouse"
    assert cp.kind_of("under desk cable management tray")[0] == "cable_tray"  # not a desk
    assert cp.kind_of("something nobody sells")[0] == "package"


def test_a_grab_bar_goes_on_the_wall_behind_the_toilet_at_rail_height():
    [g] = place([finding("f1", "toilet grab bar", ["toilet"])], [quote("f1", "Moen 18 in grab bar")])
    assert g["type"] == "grab_bar" and g["room_id"] == "bath" and g["position"][1] == 0.86
    assert g["position"][2] < 0.35  # behind the toilet (its back faces -z)
    assert g["image_url"] is None and g["title"] == "Moen 18 in grab bar" and g["fix"] == "Fix it"


def test_handrails_follow_the_stairs_slope_and_a_gate_sits_at_the_bottom_step():
    rails = place([finding("f1", "stair handrail kit", ["stair"], qty=2)], [quote("f1", "Handrail kit", qty=2)])
    assert len(rails) == 2 and all(r["type"] == "stair_rail" for r in rails)
    assert math.isclose(rails[0]["pitch"], math.atan2(2.6, 3.0), rel_tol=1e-3)
    [gate] = place([finding("f2", "baby gate for stairs", ["stair"])], [quote("f2", "Baby gate")])
    assert gate["type"] == "baby_gate" and gate["position"][2] > 5.0 + 1.5  # the bottom step is the +z end
    assert gate["size"][0] == 0.9  # as wide as the stairs


def test_office_items_land_on_the_desk_already_in_the_room():
    findings = [finding("m", "27 inch monitor", qty=2), finding("k", "wireless keyboard and mouse combo")]
    out = place(findings, [quote("m", "27 in monitor", qty=2), quote("k", "Logitech MK270")], room="office")
    monitors = [g for g in out if g["type"] == "monitor"]
    assert len(monitors) == 2 and all(abs(g["position"][1] - (0.75 + 0.23)) < 0.01 for g in monitors)  # on the desk top
    assert any(g["type"] == "keyboard_mouse" for g in out)


def test_outlet_covers_go_on_each_outlet_and_unknown_things_are_a_box_beside_the_object():
    out = place([finding("o", "outlet plug covers", ["out1"]), finding("x", "mystery gadget", ["toilet"])],
                [quote("o", "Outlet covers 36 pack"), quote("x", "Gadget")])
    cover = next(g for g in out if g["type"] == "outlet_cover")
    assert cover["object_id"] == "out1" and cover["position"][0] > 3.01  # just in front of the outlet
    box = next(g for g in out if g["type"] == "package")
    assert box["room_id"] == "bath" and box["position"][1] == 0.1


# --- the coordinator hook: never in the way of the cart or the payment ---------------------------

from agents.coordinator import agent as coord  # noqa: E402
from shared.models import Overlay  # noqa: E402
from tests.conftest import FakeCtx, USER  # noqa: E402


def run(coro):
    return asyncio.run(coro)


def cart_state(mode="elder"):
    f = finding("f1", "toilet grab bar", ["toilet"])
    cart = CartResult(job_id="job1", ok=True, items=[quote("f1", "Moen grab bar")], subtotal_usd=25.0,
                      checkout_links=[])
    return {"job_id": "job1", "space_id": "sp", "profile": {"budget_usd": 300},
            "result": {"mode": mode, "summary": "s", "findings": [f.model_dump()], "overlay_set_id": "ov_pins",
                       "job_id": "job1", "ok": True},
            "cart": cart.model_dump()}, cart


@pytest.fixture
def service(monkeypatch):
    calls = {"posted": None}

    async def get_space(space_id):
        return home()

    async def get_overlays(space_id, overlay_set_id):
        return [Overlay(type="pin", data={"object_id": "toilet", "finding_id": "f1"}),
                Overlay(type="ghost_object", data={"label": "desk", "wall": "back", "action": "add"})]

    async def post_overlays(space_id, mode, overlays, job_id):
        calls["posted"] = (mode, overlays, job_id)
        return {"overlay_set_id": "ov_cart", "viewer_url": "http://viewer/s/sp?mode=elder&o=ov_cart&live=1"}

    async def photos(urls):
        return {}

    monkeypatch.setattr(coord, "get_space", get_space)
    monkeypatch.setattr(coord, "get_overlays", get_overlays)
    monkeypatch.setattr(coord, "post_overlays", post_overlays)
    monkeypatch.setattr(cp, "photos", photos)
    return calls


@pytest.mark.cart_preview
def test_the_preview_keeps_the_pins_adds_the_cart_and_drops_wall_only_notes(service):
    state, cart = cart_state()
    url = run(coord.cart_preview_link(FakeCtx(), state, cart))
    assert url.endswith("o=ov_cart&live=1")
    mode, overlays, job = service["posted"]
    assert mode == "elder" and job == "job1"  # same conversation: an open 3D view follows it
    assert [o.type for o in overlays] == ["pin", "ghost_object"] and overlays[1].data["type"] == "grab_bar"


@pytest.mark.cart_preview
def test_no_preview_for_a_claim_or_without_a_home(service):
    state, cart = cart_state("claim")
    assert run(coord.cart_preview_link(FakeCtx(), state, cart)) is None
    state, cart = cart_state()
    state["space_id"] = None
    assert run(coord.cart_preview_link(FakeCtx(), state, cart)) is None
    assert service["posted"] is None


@pytest.mark.cart_preview
def test_a_failing_or_slow_service_never_holds_up_the_cart(service, monkeypatch):
    async def broken(space_id):
        raise RuntimeError("Space Service is down")

    monkeypatch.setattr(coord, "get_space", broken)
    state, cart = cart_state()
    ctx = FakeCtx()
    assert run(coord.cart_preview_link(ctx, state, cart)) is None
    assert any("cart preview skipped" in l for l in ctx.logger.lines)

    async def slow(space_id):
        await asyncio.sleep(5)

    monkeypatch.setattr(coord, "get_space", slow)
    monkeypatch.setattr(coord, "CART_PREVIEW_WAIT_S", 0.2)
    import time
    t0 = time.monotonic()
    assert run(coord.cart_preview_link(FakeCtx(), state, cart)) is None
    assert time.monotonic() - t0 < 1


@pytest.mark.cart_preview
def test_the_cart_message_links_the_preview_and_the_payment_request_goes_first(service, fake_stripe):
    state, cart = cart_state()
    ctx = FakeCtx()
    run(coord.request_fee(ctx, USER, state))
    kinds = [type(m).__name__ for _, m in ctx.sent]
    assert kinds.index("RequestPayment") < kinds.index("ChatMessage")
    assert any("[See your cart in your home](http://viewer/s/sp?mode=elder&o=ov_cart&live=1)" in t for t in ctx.texts())


@pytest.mark.cart_preview
def test_without_a_preview_the_cart_message_is_unchanged(service, fake_stripe, monkeypatch):
    async def broken(space_id):
        raise RuntimeError("down")

    monkeypatch.setattr(coord, "get_space", broken)
    state, cart = cart_state()
    ctx = FakeCtx()
    run(coord.request_fee(ctx, USER, state))
    text = next(t for t in ctx.texts() if "added it to your cart" in t or "added them to your cart" in t)
    assert "See your cart in your home" not in text and "Tap **Pay**" in text
