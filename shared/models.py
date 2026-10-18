"""Shared message contracts for every Last Mile Home agent and service.

Owned by Shresth: tell him before changing anything here. Build against these types only.
Units: meters, USD. Coordinates: x right, y up, z forward; origin = room corner.
"""
from typing import Literal, Optional

from uagents import Model

Mode = Literal["elder", "baby", "transform", "claim"]


class TraceCtx(Model):                    # Kenil: used to stitch one trace across agents
    sentry_trace: Optional[str] = None
    baggage: Optional[str] = None


class Evidence(Model):
    frame_url: Optional[str] = None       # image of the frame the object/hazard was seen in
    timestamp_s: Optional[float] = None   # seconds into the video
    note: Optional[str] = None


class SpaceObject(Model):
    id: str                               # "obj_rug_01"
    type: str                             # from the 30-type catalog (see Aditya.md)
    label: str                            # "Living room rug"
    room_id: str
    position: list[float]                 # [x, y, z] center, meters
    size: list[float]                     # [w, h, d] meters
    rotation_y: float = 0.0               # radians
    color: Optional[str] = None           # "#a3825f"
    material: Optional[str] = None
    attributes: dict = {}                 # brand_guess, model_guess, height_from_floor, is_loose, ...
    confidence: float = 0.5
    evidence: list[Evidence] = []


class Door(Model):
    id: str
    room_id: str
    position: list[float]
    width_m: float


class Room(Model):
    id: str
    name: str                             # "Hallway"
    polygon: list[list[float]]            # floor outline [[x,z], ...]
    height_m: float = 2.5


class Space(Model):
    space_id: str
    source_type: Literal["video", "photos"]
    rooms: list[Room]
    doors: list[Door] = []
    objects: list[SpaceObject]
    scale_method: str                     # "door_reference" | "depth_pro" | "user_confirmed" | "prebuilt"
    scale_confidence: float
    viewer_url: str                       # https://viewer.../s/{space_id}
    snapshot_url: str                     # PNG for cards


class SpaceBuildRequest(Model):
    job_id: str
    media_urls: list[str]                 # ASI:One attachments arrive as public URLs (ResourceContent.uri)
    trace: TraceCtx = TraceCtx()


class SpaceBuildResult(Model):
    job_id: str
    ok: bool
    space: Optional[Space] = None
    error: Optional[str] = None


class Profile(Model):                     # filled from the intake card; each mode uses what it needs
    person: Optional[str] = None          # "Mom"
    age: Optional[int] = None
    mobility_aid: Optional[str] = None    # "walker" | "cane" | "wheelchair" | None
    night_trips: Optional[bool] = None
    child_age_months: Optional[int] = None
    goal: Optional[str] = None            # transform: what the room becomes, "home office"
    room_id: Optional[str] = None         # transform: which room to change
    keep_object_ids: list[str] = []       # transform: objects that must stay
    requirements: Optional[str] = None    # transform: "two monitors, video calls, door must close"
    style: Optional[str] = None           # transform: "japandi", "warm modern"...
    budget_usd: Optional[float] = None
    policy_type: Optional[str] = None     # claim: "replacement_cost" | "actual_cash_value"
    zip_code: Optional[str] = None


class Measurement(Model):
    name: str                             # "walkway_clearance"
    value: float
    unit: str                             # "in" | "m" | "lux_est"
    required: Optional[float] = None
    passes: Optional[bool] = None


class ProductQuery(Model):
    query: str                            # "adhesive non-slip rug gripper 5x7"
    max_price_usd: Optional[float] = None
    constraints: dict = {}                # {"length_in": 18, "toilet_shape": "elongated"}
    quantity: int = 1


class Finding(Model):
    id: str
    kind: Literal["hazard", "suggestion", "item"]
    title: str                            # "Loose rug in hallway"
    severity: int = 3                     # 1 low … 5 critical (hazards only)
    object_ids: list[str] = []
    evidence: list[Evidence] = []
    measurements: list[Measurement] = []
    fix_summary: Optional[str] = None
    product_query: Optional[ProductQuery] = None
    value_usd: Optional[float] = None     # claim mode
    value_basis: Optional[str] = None     # "receipt" | "measured" | "user_confirmed" | "estimate"


class Overlay(Model):                     # what the viewer draws
    type: Literal["pin", "path", "ghost_object", "tag", "highlight", "camera"]
    data: dict                            # see Aditya.md for each type's fields


class ModeRequest(Model):
    job_id: str
    mode: Mode
    space_id: str
    profile: Profile
    trace: TraceCtx = TraceCtx()


class ModeResult(Model):
    job_id: str
    mode: Mode
    ok: bool
    summary: str
    findings: list[Finding] = []
    overlay_set_id: Optional[str] = None  # stored in Space Service; viewer loads it
    viewer_url: Optional[str] = None      # deep link: /s/{space_id}?mode=elder&o={overlay_set_id}
    snapshot_url: Optional[str] = None
    error: Optional[str] = None


class ProductQuote(Model):
    title: str
    url: str
    merchant: str
    price_usd: float
    image_url: Optional[str] = None
    specs: dict = {}
    url_verified: bool = False            # we actually fetched the page and saw the product
    fit_note: Optional[str] = None        # "18 in bar fits 22 in wall stud span"
    finding_id: Optional[str] = None


class FindProductsRequest(Model):
    job_id: str
    queries: list[ProductQuery]
    trace: TraceCtx = TraceCtx()


class FindProductsResult(Model):
    job_id: str
    ok: bool
    quotes: list[ProductQuote] = []
    error: Optional[str] = None


class CartRequest(Model):
    job_id: str
    quotes: list[ProductQuote]
    budget_usd: Optional[float] = None
    trace: TraceCtx = TraceCtx()


class CartResult(Model):
    job_id: str
    ok: bool
    cart_id: str = ""
    items: list[ProductQuote] = []
    subtotal_usd: float = 0.0
    within_budget: bool = True
    checkout_links: list[str] = []        # merchant handoff — NOT a placed order (label it)
    service_fee_fet: str = "0"            # what the Coordinator will charge via Payment Protocol
    error: Optional[str] = None


class VerifyPaymentRequest(Model):
    job_id: str
    tx_hash: str
    expected_amount_fet: str
    recipient: str
    trace: TraceCtx = TraceCtx()


class VerifyPaymentResult(Model):
    job_id: str
    ok: bool
    verified: bool = False
    detail: str = ""


class ClaimRequest(Model):
    job_id: str
    space_id: str
    findings: list[Finding]               # kind="item" with value_usd + value_basis
    profile: Profile
    trace: TraceCtx = TraceCtx()


class ClaimPackage(Model):
    job_id: str
    ok: bool
    inventory_xlsx_url: Optional[str] = None
    inventory_csv_url: Optional[str] = None
    letter_pdf_url: Optional[str] = None  # cover letter / advance-payment request draft
    total_usd: float = 0.0
    item_count: int = 0
    error: Optional[str] = None


class AgentError(Model):                  # any agent → Recovery agent
    job_id: str
    agent: str
    step: str
    message: str
    retryable: bool
    sentry_event_id: Optional[str] = None
    retry_payload: dict = {}              # enough to redo the step


class RecoveryNotice(Model):              # Recovery → Coordinator (shown to user as a card)
    job_id: str
    step: str
    outcome: Literal["recovered", "fallback_used", "failed"]
    user_message: str                     # "Pricing service was slow — switched to backup. All good."
    sentry_trace_url: Optional[str] = None
