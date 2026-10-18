"""Object catalog: every SpaceObject.type the extractor may emit, and how layout treats it.

One row per type: (type, group, placement, wall_snap, collides, movable)
  group      shown to Claude as a heading so it scans the frames room by room
  placement  floor   bottom on the floor
             wall    keeps its height, always pushed flat against the nearest wall
             ceiling top at the ceiling
             any     keeps the height Claude measured (things on tables, counters, shelves)
  wall_snap  floor/any objects within WALL_SNAP_M of a wall get pushed against it
  collides   solid footprint that layout de-overlaps; False for flat, mounted or on-top things
  movable    attributes.is_movable (elder / transformer move these around)

The viewer keeps a default size for every type in viewer/src/lib/defaults.ts; add
new types there too. Shresth's specialists match on these exact strings, notably
"light", "outlet", "cord", "rug", "toilet", "bathtub", "window" and the
tip-over set (bookshelf, dresser, tv, tv_stand, wardrobe).
"""

_ROWS = [
    # --- Living room ---
    ("sofa", "living room", "floor", True, True, True),
    ("sectional_sofa", "living room", "floor", True, True, True),
    ("armchair", "living room", "floor", True, True, True),
    ("recliner", "living room", "floor", True, True, True),
    ("ottoman", "living room", "floor", False, True, True),
    ("coffee_table", "living room", "floor", False, True, True),
    ("side_table", "living room", "floor", False, True, True),
    ("console_table", "living room", "floor", True, True, True),
    ("tv", "living room", "any", True, True, True),
    ("tv_stand", "living room", "floor", True, True, True),
    ("bookshelf", "living room", "floor", True, True, True),
    ("shelf", "living room", "wall", True, False, False),
    ("cabinet", "living room", "floor", True, True, True),
    ("bench", "living room", "floor", True, True, True),
    ("fireplace", "living room", "floor", True, True, False),
    ("piano", "living room", "floor", True, True, True),
    # --- Bedroom / nursery ---
    ("bed", "bedroom", "floor", True, True, True),
    ("crib", "bedroom", "floor", True, True, True),
    ("nightstand", "bedroom", "floor", True, True, True),
    ("dresser", "bedroom", "floor", True, True, True),
    ("wardrobe", "bedroom", "floor", True, True, True),
    ("vanity", "bedroom", "floor", True, True, True),
    ("changing_table", "bedroom", "floor", True, True, True),
    ("toy_box", "bedroom", "floor", True, True, True),
    ("toys", "bedroom", "floor", False, False, True),
    # --- Dining / office ---
    ("dining_table", "dining and office", "floor", False, True, True),
    ("chair", "dining and office", "floor", False, True, True),
    ("high_chair", "dining and office", "floor", False, True, True),
    ("stool", "dining and office", "floor", False, True, True),
    ("desk", "dining and office", "floor", True, True, True),
    ("office_chair", "dining and office", "floor", False, True, True),
    # --- Kitchen ---
    ("counter", "kitchen", "floor", True, True, False),
    ("kitchen_island", "kitchen", "floor", False, True, False),
    ("refrigerator", "kitchen", "floor", True, True, False),
    ("stove", "kitchen", "floor", True, True, False),
    ("oven", "kitchen", "floor", True, True, False),
    ("microwave", "kitchen", "any", False, False, True),
    ("dishwasher", "kitchen", "floor", True, True, False),
    ("sink", "kitchen", "floor", True, True, False),
    ("range_hood", "kitchen", "wall", True, False, False),
    ("small_appliance", "kitchen", "any", False, False, True),
    ("trash_can", "kitchen", "floor", True, True, True),
    # --- Laundry / utility ---
    ("washer", "laundry and utility", "floor", True, True, False),
    ("dryer", "laundry and utility", "floor", True, True, False),
    ("water_heater", "laundry and utility", "floor", True, True, False),
    ("laundry_basket", "laundry and utility", "floor", False, False, True),
    ("ironing_board", "laundry and utility", "floor", False, True, True),
    # --- Bathroom ---
    ("toilet", "bathroom", "floor", True, True, False),
    ("bathtub", "bathroom", "floor", True, True, False),
    ("shower", "bathroom", "floor", True, True, False),
    ("bath_mat", "bathroom", "floor", False, False, True),
    ("towel_rack", "bathroom", "wall", True, False, False),
    ("grab_bar", "bathroom", "wall", True, False, False),
    ("shower_seat", "bathroom", "floor", False, True, True),
    # --- Lighting ---
    ("light", "lighting", "any", False, False, False),  # fixed fixture: ceiling, wall or plug-in night light
    ("lamp_floor", "lighting", "floor", True, True, True),
    ("lamp_table", "lighting", "any", False, False, True),
    # --- Decor ---
    ("rug", "decor", "floor", False, False, True),
    ("plant", "decor", "any", True, True, True),
    ("painting", "decor", "wall", True, False, True),
    ("mirror", "decor", "wall", True, False, True),
    ("curtain", "decor", "wall", True, False, True),
    ("clock", "decor", "wall", True, False, True),
    ("decor", "decor", "any", False, False, True),
    # --- Electronics ---
    ("laptop", "electronics", "any", False, False, True),
    ("monitor", "electronics", "any", False, False, True),
    ("computer", "electronics", "any", False, False, True),
    ("game_console", "electronics", "any", False, False, True),
    ("speaker", "electronics", "any", False, False, True),
    ("printer", "electronics", "any", False, False, True),
    ("router", "electronics", "any", False, False, True),
    ("fan", "electronics", "floor", False, True, True),
    ("space_heater", "electronics", "floor", False, True, True),
    ("air_conditioner", "electronics", "wall", True, False, False),
    # --- Building parts and fixtures ---
    ("window", "building", "wall", True, False, False),
    ("door", "building", "wall", True, False, False),  # doors are returned separately, never as objects
    ("stairs", "building", "floor", True, True, False),
    ("step", "building", "floor", False, False, False),
    ("handrail", "building", "wall", True, False, False),
    ("radiator", "building", "wall", True, True, False),
    ("outlet", "building", "wall", True, False, False),
    ("light_switch", "building", "wall", True, False, False),
    ("thermostat", "building", "wall", True, False, False),
    ("smoke_detector", "building", "ceiling", False, False, False),
    # --- Safety and mobility ---
    ("stair_gate", "safety and mobility", "floor", True, False, True),
    ("walker", "safety and mobility", "floor", False, True, True),
    ("wheelchair", "safety and mobility", "floor", False, True, True),
    # --- Storage and misc ---
    ("box", "storage and misc", "floor", False, True, True),
    ("shoe_rack", "storage and misc", "floor", True, True, True),
    ("coat_rack", "storage and misc", "floor", True, True, True),
    ("pet_bed", "storage and misc", "floor", False, False, True),
    ("bicycle", "storage and misc", "floor", True, True, True),
    ("exercise_equipment", "storage and misc", "floor", False, True, True),
    ("cord", "storage and misc", "floor", False, False, True),
    ("clutter", "storage and misc", "floor", False, False, True),
    ("other", "storage and misc", "any", False, True, True),
]

OBJECT_TYPES = tuple(row[0] for row in _ROWS)
EXTRACTABLE_TYPES = tuple(t for t in OBJECT_TYPES if t != "door")

GROUPS: dict[str, list[str]] = {}
for _type, _group, *_ in _ROWS:
    if _type != "door":
        GROUPS.setdefault(_group, []).append(_type)

FLOOR_TYPES = {r[0] for r in _ROWS if r[2] == "floor"}
WALL_MOUNTED = {r[0] for r in _ROWS if r[2] == "wall"}
CEILING_TYPES = {r[0] for r in _ROWS if r[2] == "ceiling"}
NO_WALL_SNAP = {r[0] for r in _ROWS if not r[3]}
NO_COLLIDE = {r[0] for r in _ROWS if not r[4]}
MOVABLE = {r[0] for r in _ROWS if r[5]}
