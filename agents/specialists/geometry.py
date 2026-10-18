"""Small geometry helpers shared by the specialists (meters, floor plane = x/z)."""
from shared.models import Room, SpaceObject

M_TO_IN = 39.37


def inches(m: float) -> float:
    return round(m * M_TO_IN)


def footprint(obj: SpaceObject) -> tuple[float, float, float, float]:
    """Axis-aligned floor footprint (min_x, max_x, min_z, max_z), ignoring rotation."""
    x, _, z = obj.position
    w, _, d = obj.size
    return x - w / 2, x + w / 2, z - d / 2, z + d / 2


def bounds(room: Room) -> tuple[float, float, float, float]:
    xs = [p[0] for p in room.polygon]
    zs = [p[1] for p in room.polygon]
    return min(xs), max(xs), min(zs), max(zs)


def gap_x(a: SpaceObject, b: SpaceObject) -> float:
    """Clear floor distance between two objects along x (0 if they overlap)."""
    a0, a1, _, _ = footprint(a)
    b0, b1, _, _ = footprint(b)
    return max(0.0, max(b0 - a1, a0 - b1))
