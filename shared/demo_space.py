"""A hand-checked demo home, used when the Space Service is unavailable (MASTER section 12).

A small apartment: bedroom -> hallway -> bathroom, plus a living room. Meters; x right,
y up, z forward; origin at the bedroom's back-left corner. It is built to contain the
hazards the demo shows: a chair narrowing the bedside path, a loose hallway rug and a
cord on the night path, a narrow bathroom door, a low toilet with no grab bar, an
uncovered outlet, a sharp-cornered glass table and an unanchored bookshelf.
"""
from shared.models import Door, Room, Space, SpaceObject

DEMO_SPACE_ID = "demo-apartment"


def _obj(id, type, label, room_id, position, size, **attributes):
    color = attributes.pop("color", None)
    material = attributes.pop("material", None)
    return SpaceObject(
        id=id, type=type, label=label, room_id=room_id, position=position, size=size,
        color=color, material=material, attributes=attributes, confidence=0.9,
    )


def demo_space(snapshot_url: str = "", viewer_url: str = "") -> Space:
    rooms = [
        Room(id="bedroom", name="Bedroom", polygon=[[0, 0], [4, 0], [4, 3.5], [0, 3.5]]),
        Room(id="hallway", name="Hallway", polygon=[[4, 1.2], [7, 1.2], [7, 2.3], [4, 2.3]]),
        Room(id="bathroom", name="Bathroom", polygon=[[7, 0], [9.5, 0], [9.5, 2.5], [7, 2.5]]),
        Room(id="living", name="Living room", polygon=[[4, 2.3], [9.5, 2.3], [9.5, 7], [4, 7]]),
    ]
    doors = [
        Door(id="door_bed_hall", room_id="bedroom", position=[4, 1, 1.75], width_m=0.81),
        Door(id="door_hall_bath", room_id="bathroom", position=[7, 1, 1.75], width_m=0.71),
        Door(id="door_hall_living", room_id="living", position=[5.5, 1, 2.3], width_m=0.9),
    ]
    objects = [
        # Bedroom
        _obj("obj_bed_01", "bed", "Queen bed", "bedroom", [2.0, 0.3, 1.5], [1.5, 0.6, 2.0],
             color="#d8cfc4", height_from_floor=0.0, model_guess="queen platform bed"),
        _obj("obj_nightstand_01", "nightstand", "Nightstand", "bedroom", [0.9, 0.3, 0.3], [0.45, 0.6, 0.4],
             color="#8a6a4f", material="wood", height_from_floor=0.0),
        _obj("obj_chair_01", "chair", "Armchair by the door", "bedroom", [3.4, 0.4, 1.9], [0.6, 0.8, 0.6],
             color="#5b6b7a", height_from_floor=0.0, is_movable=True),
        _obj("obj_dresser_01", "dresser", "Dresser", "bedroom", [1.2, 0.45, 3.2], [1.2, 0.9, 0.5],
             color="#8a6a4f", material="wood", height_from_floor=0.0, anchored=False),
        _obj("obj_outlet_01", "outlet", "Wall outlet (uncovered)", "bedroom", [0.02, 0.3, 2.6], [0.07, 0.11, 0.01],
             height_from_floor=0.3, covered=False),
        _obj("obj_window_01", "window", "Bedroom window", "bedroom", [2.0, 1.4, 3.5], [1.6, 1.2, 0.05],
             height_from_floor=0.8),
        # Hallway (the 2 am path)
        _obj("obj_rug_01", "rug", "Hallway runner rug", "hallway", [5.5, 0.005, 1.75], [1.8, 0.01, 0.7],
             color="#a3825f", height_from_floor=0.0, is_loose=True, has_backing=False),
        _obj("obj_cord_01", "cord", "Lamp cord across hallway", "hallway", [6.3, 0.0, 1.75], [0.03, 0.01, 1.1],
             height_from_floor=0.0),
        _obj("obj_light_hall_01", "light", "Hallway ceiling light (switch at living room end)", "hallway",
             [5.5, 2.45, 1.75], [0.3, 0.05, 0.3], height_from_floor=2.45, night_light=False),
        # Bathroom
        _obj("obj_toilet_01", "toilet", "Toilet", "bathroom", [8.9, 0.19, 0.45], [0.4, 0.38, 0.7],
             color="#ffffff", height_from_floor=0.0, seat_height_m=0.38, toilet_shape="round"),
        _obj("obj_tub_01", "bathtub", "Bathtub", "bathroom", [8.25, 0.27, 2.1], [1.5, 0.55, 0.75],
             color="#ffffff", height_from_floor=0.0, grab_bar=False),
        # Living room
        _obj("obj_sofa_01", "sofa", "Sofa", "living", [6.5, 0.42, 6.4], [2.1, 0.85, 0.9],
             color="#7d8b6a", height_from_floor=0.0, model_guess="3-seat fabric sofa"),
        _obj("obj_table_01", "coffee_table", "Glass coffee table", "living", [6.5, 0.22, 5.3], [1.1, 0.45, 0.6],
             material="glass", height_from_floor=0.0, sharp_corners=True),
        _obj("obj_shelf_01", "bookshelf", "Tall bookshelf", "living", [9.3, 0.9, 4.5], [0.8, 1.8, 0.3],
             color="#3e3a36", height_from_floor=0.0, anchored=False),
        _obj("obj_tvstand_01", "tv_stand", "TV stand", "living", [4.3, 0.25, 4.6], [0.4, 0.5, 1.4],
             color="#3e3a36", height_from_floor=0.0),
        _obj("obj_tv_01", "tv", "55 in TV", "living", [4.3, 0.86, 4.6], [0.08, 0.72, 1.23],
             height_from_floor=0.5, model_guess="55 in LED TV", anchored=False),
        _obj("obj_outlet_02", "outlet", "Wall outlet behind TV stand", "living", [4.02, 0.3, 5.5], [0.07, 0.11, 0.01],
             height_from_floor=0.3, covered=False),
        _obj("obj_plant_01", "plant", "Potted plant", "living", [9.1, 0.4, 2.8], [0.4, 0.8, 0.4],
             height_from_floor=0.0),
    ]
    return Space(
        space_id=DEMO_SPACE_ID,
        source_type="video",
        rooms=rooms,
        doors=doors,
        objects=objects,
        scale_method="prebuilt",
        scale_confidence=1.0,
        viewer_url=viewer_url,
        snapshot_url=snapshot_url,
    )
