"""See your cart in your home: cart items placed in the 3D model before you buy."""
import math

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
