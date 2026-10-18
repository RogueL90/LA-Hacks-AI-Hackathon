"""Build a ready-to-send contents package. This does not file a claim."""

from __future__ import annotations

import csv
import os
from pathlib import Path

import httpx
from openpyxl import Workbook
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from shared.models import ClaimPackage, ClaimRequest, Finding

OUT_DIR = Path(__file__).resolve().parent / "out"

COLUMNS = [
    "room",
    "item",
    "description",
    "brand_model",
    "quantity",
    "age",
    "replacement_cost_usd",
    "value_basis",
    "evidence_link",
]

BASIS = {
    "receipt": "Receipt",
    "measured": "Measured",
    "user_confirmed": "Confirmed",
    "estimate": "Estimate",
}

ADVANCE_PARAGRAPH = (
    "If this loss is a covered total loss of a furnished primary dwelling caused by "
    "a California declared state of emergency, we request the advance contents payment "
    "described in California Insurance Code section 10103.7. For the policy form described "
    "in the Department of Insurance's 2025 guidance, that offer is at least 30 percent of "
    "the policy limit applicable to the covered dwelling structure, up to 250,000 dollars, "
    "without an itemized inventory. Later amendments may raise the percentage and the cap "
    "for policies issued or renewed after their effective date. Please confirm the "
    "percentage and cap that apply to this policy before paying the advance. "
    "This letter is a ready-to-send draft. It is not a claim filed with an insurer."
)


def _basis_label(value: str | None) -> str:
    if not value:
        return "Estimate"
    return BASIS.get(value, value.replace("_", " ").title())


def _constraint(finding: Finding, key: str, default: str = "") -> str:
    query = finding.product_query
    if query is None or not query.constraints:
        return default
    raw = query.constraints.get(key)
    return default if raw is None else str(raw)


def _room(finding: Finding) -> str:
    room = _constraint(finding, "room")
    if room:
        return room
    for evidence in finding.evidence:
        if evidence.note:
            return evidence.note
    return "Unassigned"


def _quantity(finding: Finding) -> int:
    query = finding.product_query
    if query is None:
        return 1
    return query.quantity if query.quantity > 0 else 1


def _rows(request: ClaimRequest) -> list[dict]:
    rows = []
    for finding in request.findings:
        if finding.kind != "item":
            continue
        brand = _constraint(finding, "brand")
        model = _constraint(finding, "model")
        brand_model = " ".join(part for part in (brand, model) if part).strip()
        age = _constraint(finding, "age_years")
        frame = next((item.frame_url for item in finding.evidence if item.frame_url), "")
        cost = round(float(finding.value_usd or 0) * _quantity(finding), 2)
        rows.append(
            {
                "room": _room(finding),
                "item": finding.title,
                "description": finding.fix_summary or finding.title,
                "brand_model": brand_model,
                "quantity": _quantity(finding),
                "age": age,
                "replacement_cost_usd": cost,
                "value_basis": _basis_label(finding.value_basis),
                "evidence_link": frame or "",
            }
        )
    rows.sort(key=lambda row: (row["room"], row["item"]))
    return rows


def _write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
        by_room: dict[str, float] = {}
        for row in rows:
            by_room[row["room"]] = round(by_room.get(row["room"], 0) + row["replacement_cost_usd"], 2)
        for room, total in by_room.items():
            writer.writerow(
                {
                    "room": room,
                    "item": "ROOM TOTAL",
                    "description": "",
                    "brand_model": "",
                    "quantity": "",
                    "age": "",
                    "replacement_cost_usd": total,
                    "value_basis": "",
                    "evidence_link": "",
                }
            )
        grand = round(sum(row["replacement_cost_usd"] for row in rows), 2)
        writer.writerow(
            {
                "room": "ALL",
                "item": "OVERALL TOTAL",
                "description": "",
                "brand_model": "",
                "quantity": "",
                "age": "",
                "replacement_cost_usd": grand,
                "value_basis": "",
                "evidence_link": "",
            }
        )


def _write_xlsx(path: Path, rows: list[dict]) -> None:
    book = Workbook()
    sheet = book.active
    sheet.title = "Contents inventory"
    sheet.append(COLUMNS)
    current_room = None
    room_total = 0.0
    for row in rows:
        if current_room is not None and row["room"] != current_room:
            sheet.append([current_room, "ROOM TOTAL", "", "", "", "", room_total, "", ""])
            room_total = 0.0
        current_room = row["room"]
        room_total = round(room_total + row["replacement_cost_usd"], 2)
        sheet.append([row[column] for column in COLUMNS])
    if current_room is not None:
        sheet.append([current_room, "ROOM TOTAL", "", "", "", "", room_total, "", ""])
    grand = round(sum(row["replacement_cost_usd"] for row in rows), 2)
    sheet.append(["ALL", "OVERALL TOTAL", "", "", "", "", grand, "", ""])
    book.save(path)


def _write_pdf(path: Path, request: ClaimRequest, rows: list[dict], total: float) -> None:
    profile = request.profile
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(path), pagesize=letter, title="Contents claim package")
    story = [
        Paragraph("Contents claim package — ready to send", styles["Title"]),
        Spacer(1, 12),
        Paragraph(
            "This package is a draft for the policyholder to send. It has not been filed with an insurer.",
            styles["BodyText"],
        ),
        Spacer(1, 12),
        Paragraph(f"Claimant: {profile.person or '[name]'}", styles["BodyText"]),
        Paragraph(f"ZIP: {profile.zip_code or '[ZIP]'}", styles["BodyText"]),
        Paragraph(f"Policy type: {profile.policy_type or '[policy type]'}", styles["BodyText"]),
        Paragraph(f"Space: {request.space_id}", styles["BodyText"]),
        Paragraph(f"Job: {request.job_id}", styles["BodyText"]),
        Spacer(1, 12),
        Paragraph(
            f"Summary of loss: {len(rows)} contents items are listed from the home scan. "
            f"The replacement total in this draft is ${total:,.2f}.",
            styles["BodyText"],
        ),
        Spacer(1, 12),
        Paragraph("Attachments", styles["Heading2"]),
        Paragraph("1. Contents inventory spreadsheet (XLSX)", styles["BodyText"]),
        Paragraph("2. Contents inventory spreadsheet (CSV)", styles["BodyText"]),
        Paragraph("3. This cover letter (PDF)", styles["BodyText"]),
        Spacer(1, 12),
        Paragraph("Advance contents payment", styles["Heading2"]),
        Paragraph(ADVANCE_PARAGRAPH, styles["BodyText"]),
    ]
    doc.build(story)


def write_package_files(request: ClaimRequest) -> tuple[list[dict], Path, Path, Path]:
    rows = _rows(request)
    folder = OUT_DIR / request.job_id
    folder.mkdir(parents=True, exist_ok=True)
    csv_path = folder / "contents-inventory.csv"
    xlsx_path = folder / "contents-inventory.xlsx"
    pdf_path = folder / "cover-letter.pdf"
    _write_csv(csv_path, rows)
    _write_xlsx(xlsx_path, rows)
    total = round(sum(row["replacement_cost_usd"] for row in rows), 2)
    _write_pdf(pdf_path, request, rows, total)
    return rows, xlsx_path, csv_path, pdf_path


async def upload_file(client: httpx.AsyncClient, base: str, path: Path) -> str:
    mime = "application/octet-stream"
    if path.suffix == ".csv":
        mime = "text/csv"
    elif path.suffix == ".xlsx":
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif path.suffix == ".pdf":
        mime = "application/pdf"
    with path.open("rb") as handle:
        response = await client.post(
            f"{base.rstrip('/')}/media/upload",
            files={"file": (path.name, handle, mime)},
        )
    response.raise_for_status()
    body = response.json()
    url = body.get("url")
    if not url:
        raise RuntimeError("Space Service upload response did not include url")
    return str(url)


async def build_claim_package(request: ClaimRequest) -> ClaimPackage:
    rows, xlsx_path, csv_path, pdf_path = write_package_files(request)
    total = round(sum(row["replacement_cost_usd"] for row in rows), 2)
    base = os.environ.get("SPACE_SERVICE_URL", "").strip()
    if not base:
        return ClaimPackage(
            job_id=request.job_id,
            ok=False,
            total_usd=total,
            item_count=len(rows),
            error=(
                "SPACE_SERVICE_URL is not set. Ready-to-send files were written to "
                f"{xlsx_path.parent}. Upload did not run. This package was not filed."
            ),
        )
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            xlsx_url = await upload_file(client, base, xlsx_path)
            csv_url = await upload_file(client, base, csv_path)
            pdf_url = await upload_file(client, base, pdf_path)
    except Exception as exc:
        return ClaimPackage(
            job_id=request.job_id,
            ok=False,
            total_usd=total,
            item_count=len(rows),
            error=(
                "Space Service upload failed. Files remain at "
                f"{xlsx_path.parent}. {exc}"
            ),
        )
    return ClaimPackage(
        job_id=request.job_id,
        ok=True,
        inventory_xlsx_url=xlsx_url,
        inventory_csv_url=csv_url,
        letter_pdf_url=pdf_url,
        total_usd=total,
        item_count=len(rows),
    )
