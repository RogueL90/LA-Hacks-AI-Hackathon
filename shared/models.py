"""Message contracts from MASTER.md section 5.

List and dict defaults use Field(default_factory=...) so the uagents
Pydantic v1 models can be constructed. Field names match the contract.
"""

from typing import Literal, Optional

from pydantic.v1 import Field
from uagents import Model

Mode = Literal["elder", "baby", "interior", "claim"]


class TraceCtx(Model):
    sentry_trace: Optional[str] = None
    baggage: Optional[str] = None


class Evidence(Model):
    frame_url: Optional[str] = None
    timestamp_s: Optional[float] = None
    note: Optional[str] = None


class SpaceObject(Model):
    id: str
    type: str
    label: str
    room_id: str
    position: list[float]
    size: list[float]
    rotation_y: float = 0.0
    color: Optional[str] = None
    material: Optional[str] = None
    attributes: dict = Field(default_factory=dict)
    confidence: float = 0.5
    evidence: list[Evidence] = Field(default_factory=list)


class Door(Model):
    id: str
    room_id: str
    position: list[float]
    width_m: float


class Room(Model):
    id: str
    name: str
    polygon: list[list[float]]
    height_m: float = 2.5


class Space(Model):
    space_id: str
    source_type: Literal["video", "photos"]
    rooms: list[Room]
    doors: list[Door] = Field(default_factory=list)
    objects: list[SpaceObject]
    scale_method: str
    scale_confidence: float
    viewer_url: str
    snapshot_url: str


class SpaceBuildRequest(Model):
    job_id: str
    media_urls: list[str]
    trace: TraceCtx = Field(default_factory=TraceCtx)


class SpaceBuildResult(Model):
    job_id: str
    ok: bool
    space: Optional[Space] = None
    error: Optional[str] = None


class Profile(Model):
    person: Optional[str] = None
    age: Optional[int] = None
    mobility_aid: Optional[str] = None
    night_trips: Optional[bool] = None
    child_age_months: Optional[int] = None
    style: Optional[str] = None
    budget_usd: Optional[float] = None
    policy_type: Optional[str] = None
    zip_code: Optional[str] = None


class Measurement(Model):
    name: str
    value: float
    unit: str
    required: Optional[float] = None
    passes: Optional[bool] = None


class ProductQuery(Model):
    query: str
    max_price_usd: Optional[float] = None
    constraints: dict = Field(default_factory=dict)
    quantity: int = 1


class Finding(Model):
    id: str
    kind: Literal["hazard", "suggestion", "item"]
    title: str
    severity: int = 3
    object_ids: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    measurements: list[Measurement] = Field(default_factory=list)
    fix_summary: Optional[str] = None
    product_query: Optional[ProductQuery] = None
    value_usd: Optional[float] = None
    value_basis: Optional[str] = None


class Overlay(Model):
    type: Literal["pin", "path", "ghost_object", "tag", "highlight", "camera"]
    data: dict = Field(default_factory=dict)


class ModeRequest(Model):
    job_id: str
    mode: Mode
    space_id: str
    profile: Profile
    trace: TraceCtx = Field(default_factory=TraceCtx)


class ModeResult(Model):
    job_id: str
    mode: Mode
    ok: bool
    summary: str
    findings: list[Finding] = Field(default_factory=list)
    overlay_set_id: Optional[str] = None
    viewer_url: Optional[str] = None
    snapshot_url: Optional[str] = None
    error: Optional[str] = None


class ProductQuote(Model):
    title: str
    url: str
    merchant: str
    price_usd: float
    image_url: Optional[str] = None
    specs: dict = Field(default_factory=dict)
    url_verified: bool = False
    fit_note: Optional[str] = None
    finding_id: Optional[str] = None


class FindProductsRequest(Model):
    job_id: str
    queries: list[ProductQuery]
    trace: TraceCtx = Field(default_factory=TraceCtx)


class FindProductsResult(Model):
    job_id: str
    ok: bool
    quotes: list[ProductQuote] = Field(default_factory=list)
    error: Optional[str] = None


class CartRequest(Model):
    job_id: str
    quotes: list[ProductQuote]
    budget_usd: Optional[float] = None
    trace: TraceCtx = Field(default_factory=TraceCtx)


class CartResult(Model):
    job_id: str
    ok: bool
    cart_id: str = ""
    items: list[ProductQuote] = Field(default_factory=list)
    subtotal_usd: float = 0.0
    within_budget: bool = True
    checkout_links: list[str] = Field(default_factory=list)
    service_fee_usd: str = "0"
    error: Optional[str] = None


class VerifyPaymentRequest(Model):
    job_id: str
    service_fee_usd: str
    trace: TraceCtx = Field(default_factory=TraceCtx)


class VerifyPaymentResult(Model):
    job_id: str
    ok: bool
    verified: bool = False
    detail: str = ""


class ClaimRequest(Model):
    job_id: str
    space_id: str
    findings: list[Finding]
    profile: Profile
    trace: TraceCtx = Field(default_factory=TraceCtx)


class ClaimPackage(Model):
    job_id: str
    ok: bool
    inventory_xlsx_url: Optional[str] = None
    inventory_csv_url: Optional[str] = None
    letter_pdf_url: Optional[str] = None
    total_usd: float = 0.0
    item_count: int = 0
    error: Optional[str] = None


class AgentError(Model):
    job_id: str
    agent: str
    step: str
    message: str
    retryable: bool
    sentry_event_id: Optional[str] = None
    retry_payload: dict = Field(default_factory=dict)


class RecoveryNotice(Model):
    job_id: str
    step: str
    outcome: Literal["recovered", "fallback_used", "failed"]
    user_message: str
    sentry_trace_url: Optional[str] = None
