"""Pydantic mirrors of the shared contracts (MASTER.md §5).

Shresth owns shared/models.py (uagents.Model). These are field-for-field copies
as plain pydantic models so the service does not depend on uagents. The wire
format (JSON) is identical. Units: meters, USD; x right, y up, z forward.
Keep this file Python 3.11 compatible.
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field

Mode = Literal["elder", "baby", "interior", "claim"]


class TraceCtx(BaseModel):
    sentry_trace: Optional[str] = None
    baggage: Optional[str] = None


class Evidence(BaseModel):
    frame_url: Optional[str] = None
    timestamp_s: Optional[float] = None
    note: Optional[str] = None


class SpaceObject(BaseModel):
    id: str
    type: str
    label: str
    room_id: str
    position: list[float]  # [x, y, z] center
    size: list[float]  # [w, h, d]
    rotation_y: float = 0.0
    color: Optional[str] = None
    material: Optional[str] = None
    attributes: dict = Field(default_factory=dict)
    confidence: float = 0.5
    evidence: list[Evidence] = Field(default_factory=list)


class Door(BaseModel):
    id: str
    room_id: str
    position: list[float]
    width_m: float


class Room(BaseModel):
    id: str
    name: str
    polygon: list[list[float]]  # floor outline [[x, z], ...]
    height_m: float = 2.5


class Space(BaseModel):
    space_id: str
    source_type: Literal["video", "photos"]
    rooms: list[Room]
    doors: list[Door] = Field(default_factory=list)
    objects: list[SpaceObject]
    scale_method: str
    scale_confidence: float
    viewer_url: str
    snapshot_url: str


class SpaceBuildRequest(BaseModel):
    job_id: str
    media_urls: list[str]
    trace: TraceCtx = Field(default_factory=TraceCtx)


class SpaceBuildResult(BaseModel):
    job_id: str
    ok: bool
    space: Optional[Space] = None
    error: Optional[str] = None


class Overlay(BaseModel):
    type: Literal["pin", "path", "ghost_object", "tag", "highlight", "camera"]
    data: dict


# --- Space Service HTTP bodies (ADITYA.md §2) ---

class OverlaySetCreate(BaseModel):
    mode: Mode
    overlays: list[Overlay]
    job_id: str


class OverlaySetCreated(BaseModel):
    overlay_set_id: str


class OverlaySet(BaseModel):
    mode: Mode
    overlays: list[Overlay]
