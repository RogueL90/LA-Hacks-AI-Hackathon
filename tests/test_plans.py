"""Specialist plans: the Space Transformer's shopping list and budget, and the noise rules."""
from agents.specialists.baby.logic import analyze as baby
from agents.specialists.elder.logic import analyze as elder
from agents.specialists.transformer.logic import analyze as transformer, requested_items
from shared.demo_space import demo_space
from shared.models import Profile, Space, SpaceObject


def office_space():
    return demo_space()


def items(findings):
    return {f.title: f.product_query for f in findings if f.product_query}


# --- Space Transformer (the live "$469 chair and nothing else" report) -----------------------

def test_requirements_become_items_with_counts():
    got = {i["title"]: i["qty"] for i in requested_items("two monitors keyboard adn mouse")}
    assert got == {"Monitor": 2, "Keyboard and mouse": 1}
    got = {i["title"]: i["qty"] for i in requested_items("3 monitors, a standing desk and a webcam for video calls")}
    assert got == {"Monitor": 3, "Standing desk": 1, "Webcam": 1}


def test_budget_is_split_so_no_item_can_take_it_all():
    s = office_space()
    bedroom = next(r.id for r in s.rooms if "bed" in r.id)
    _, f, _ = transformer(s, Profile(mode="transform", goal="home office", room_id=bedroom,
                                     requirements="two monitors keyboard adn mouse", style="Japandi", budget_usd=500))
    plan = items(f)
    assert "Add: Monitor ×2" in plan and "Add: Keyboard and mouse" in plan
    assert all(q.max_price_usd < 200 for q in plan.values())  # no single item gets the whole $500


def test_small_budget_still_searches_for_real_products_and_ranks_what_was_asked_for():
    """Live: $200 for an office with two monitors made "up to $36" monitors that don't exist."""
    s = office_space()
    bedroom = next(r.id for r in s.rooms if "bed" in r.id)
    _, f, _ = transformer(s, Profile(mode="transform", goal="home office", room_id=bedroom,
                                     requirements="two monitors", budget_usd=200))
    plan = {x.title: x for x in f if x.product_query}
    assert plan["Add: Monitor ×2"].product_query.max_price_usd >= 90  # a real monitor price
    assert plan["Add: Monitor ×2"].severity > plan["Add: Desk lamp"].severity  # asked for beats nice-to-have
    assert plan["Add: Desk"].severity >= plan["Add: Monitor ×2"].severity  # essentials first


def test_style_goes_on_furniture_not_on_the_chair_or_electronics():
    s = office_space()
    bedroom = next(r.id for r in s.rooms if "bed" in r.id)
    _, f, _ = transformer(s, Profile(mode="transform", goal="home office", room_id=bedroom,
                                     requirements="two monitors", style="Japandi", budget_usd=500))
    plan = items(f)
    assert "Japandi" in plan["Add: Desk"].query
    assert "Japandi" not in plan["Add: Ergonomic office chair"].query
    assert "Japandi" not in plan["Add: Monitor ×2"].query


def test_big_budget_still_has_sensible_ceilings():
    s = office_space()
    bedroom = next(r.id for r in s.rooms if "bed" in r.id)
    _, f, _ = transformer(s, Profile(mode="transform", goal="home office", room_id=bedroom, budget_usd=5000))
    plan = items(f)
    assert plan["Add: Cable management tray"].max_price_usd <= 60
    assert plan["Add: Ergonomic office chair"].max_price_usd <= 450


def test_standing_desk_replaces_the_desk():
    s = office_space()
    bedroom = next(r.id for r in s.rooms if "bed" in r.id)
    _, f, _ = transformer(s, Profile(mode="transform", goal="home office", room_id=bedroom,
                                     requirements="a standing desk", budget_usd=800))
    titles = set(items(f))
    assert "Add: Standing desk" in titles and "Add: Desk" not in titles


def test_desk_width_fits_the_wall():
    s = office_space()
    bedroom = next(r.id for r in s.rooms if "bed" in r.id)
    _, f, _ = transformer(s, Profile(mode="transform", goal="home office", room_id=bedroom, budget_usd=500))
    desk = items(f)["Add: Desk"]
    assert desk.constraints["width_in"] > 0 and "under" in desk.query


# --- noise rules ----------------------------------------------------------------------------

def with_objects(extra):
    s = demo_space()
    data = s.model_dump()
    data["objects"] += [o.model_dump() for o in extra]
    return Space(**data)


def obj(i, type_, label, room, h=0.0, **attrs):
    return SpaceObject(id=f"t{i}", type=type_, label=label, room_id=room, position=[1, 0, 1], size=[0.4, 0.3, 0.4],
                       confidence=0.7, attributes={"height_from_floor": h, **attrs})


def test_clutter_is_one_finding_per_room_and_only_on_the_floor():
    s = demo_space()
    bedroom = next(r.id for r in s.rooms if "bed" in r.id)
    space = with_objects([obj(1, "clutter", "shoes", bedroom), obj(2, "clutter", "laundry basket", bedroom),
                          obj(3, "clutter", "mail on a shelf", bedroom, h=0.9)])
    _, f, _ = elder(space, Profile(mode="elder", mobility_aid="walker", night_trips=True))
    clutter = [x for x in f if "lutter" in x.title]
    assert len(clutter) == 1 and set(clutter[0].object_ids) == {"t1", "t2"}


def test_cane_user_is_not_warned_about_standard_doors():
    s = demo_space()
    _, cane, _ = elder(s, Profile(mode="elder", mobility_aid="cane", night_trips=True))
    _, walker, _ = elder(s, Profile(mode="elder", mobility_aid="walker", night_trips=True))
    assert not [x for x in cane if x.title.lower().startswith("narrow")]
    assert [x for x in walker if x.title.lower().startswith("narrow")]  # the demo's 28 in bathroom door


def test_baby_corners_and_plants_are_grouped():
    s = demo_space()
    living = next(r.id for r in s.rooms if "living" in r.id)
    space = with_objects([obj(i, "coffee_table", f"table {i}", living, sharp_corners=True) for i in range(1, 4)]
                         + [obj(i, "plant", f"plant {i}", living) for i in range(4, 7)])
    _, f, ov = baby(space, Profile(mode="baby", child_age_months=14))
    assert len([x for x in f if x.title.startswith("Sharp corners")]) <= 1
    assert len([x for x in f if "plant" in x.title.lower()]) <= 1
    pinned = {o.data.get("object_id") for o in ov if o.type == "pin" and o.data.get("title") == "Floor plant"}
    assert {"t4", "t5", "t6"} <= pinned  # a pin on every plant


def test_identical_objects_to_move_are_one_line_with_a_pin_each():
    s = demo_space()
    bedroom = next(r.id for r in s.rooms if "bed" in r.id)
    space = with_objects([obj(1, "stool", "black bar stool", bedroom), obj(2, "stool", "black bar stool", bedroom)])
    _, f, ov = transformer(space, Profile(mode="transform", goal="home office", room_id=bedroom, budget_usd=500))
    moves = [x for x in f if "stool" in x.title]
    assert [x.title for x in moves] == ["Move the 2 black bar stools out"]
    assert {o.data.get("object_id") for o in ov if o.type == "pin" and "stool" in o.data.get("title", "")} == {"t1", "t2"}


def test_open_plan_sides_are_not_doors_and_doorways_are_named():
    s = demo_space()
    data = s.model_dump()
    bath = next(d for d in data["doors"] if d["room_id"] == "bathroom")
    data["doors"].append({**bath, "id": "door_open", "kind": "open", "width_m": 0.5})
    bath["kind"] = "doorway"
    _, f, _ = elder(Space(**data), Profile(mode="elder", mobility_aid="walker", night_trips=True))
    titles = [x.title for x in f if x.title.lower().startswith("narrow")]
    assert titles == ["Narrow bathroom doorway"]  # the open side isn't counted, the doorway is named


def test_fixtures_are_not_insurance_contents():
    from agents.specialists.claim.logic import analyze as claim
    s = demo_space()
    living = next(r.id for r in s.rooms if "living" in r.id)
    space = with_objects([obj(1, "vanity", "bathroom vanity", living), obj(2, "range_hood", "range hood", living),
                          obj(3, "sofa", "grey sofa", living)])
    _, f, _ = claim(space, Profile(mode="claim"))
    listed = {x.title for x in f}
    assert "grey sofa" in listed and "bathroom vanity" not in listed and "range hood" not in listed


def test_pins_say_why_and_how_to_fix():
    s = demo_space()
    _, f, ov = elder(s, Profile(mode="elder", mobility_aid="walker", night_trips=True))
    pins = [o.data for o in ov if o.type == "pin"]
    blocked = next(p for p in pins if "blocks the path" in p["title"])
    assert blocked["fix"] and blocked["severity_label"] == "Critical"
    assert any("needs 32 in" in w for w in blocked["why"])  # the measurement behind the finding


def test_no_free_wall_means_no_zero_inch_desk():
    s = demo_space()
    bedroom = next(r.id for r in s.rooms if "bed" in r.id)
    from agents.specialists import transformer as t_pkg  # noqa: F401
    import agents.specialists.transformer.logic as tl
    orig = tl._free_walls
    tl._free_walls = lambda space, room_id: [{"name": "back", "free": 0.2, "window": False}]
    try:
        _, f, _ = transformer(s, Profile(mode="transform", goal="home office", room_id=bedroom, budget_usd=500))
    finally:
        tl._free_walls = orig
    desk = items(f)["Add: Desk"]
    assert "under 0 in" not in desk.query and not desk.constraints
