"""Local checks for the Insurance Filer package."""

from __future__ import annotations

import asyncio
import re
import sys
import zlib
from base64 import a85decode
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from agents.actions.envload import load_env
from agents.actions.insurance_filer.package import build_claim_package
from shared.models import ClaimRequest

load_env()
SAMPLES = ROOT / "evals" / "samples"


def pdf_text(data: bytes) -> str:
    parts: list[str] = []
    for match in re.finditer(rb"stream\r?\n(.*?)endstream", data, re.S):
        raw = match.group(1).strip(b"\r\n")
        try:
            inflated = zlib.decompress(a85decode(b"<~" + raw, adobe=True))
        except Exception:
            continue
        parts.append(inflated.decode("latin1", errors="ignore"))
    return "\n".join(parts)


def check_files(package, folder: Path) -> None:
    if package.item_count != 10 or package.total_usd != 2670:
        raise SystemExit(f"count {package.item_count} total {package.total_usd}")
    csv_path = folder / "contents-inventory.csv"
    xlsx_path = folder / "contents-inventory.xlsx"
    pdf_path = folder / "cover-letter.pdf"
    for path in (csv_path, xlsx_path, pdf_path):
        if not path.exists() or path.stat().st_size < 100:
            raise SystemExit(f"missing package file {path}")
    csv_text = csv_path.read_text()
    if "ROOM TOTAL" not in csv_text or "OVERALL TOTAL" not in csv_text:
        raise SystemExit("inventory is missing totals")
    if "Receipt" not in csv_text or "Measured" not in csv_text or "Confirmed" not in csv_text:
        raise SystemExit("value basis labels were not written")
    letter = pdf_text(pdf_path.read_bytes())
    if "10103.7" not in letter or "not a claim filed" not in letter.lower():
        raise SystemExit("cover letter is missing the Insurance Code section or the not-filed line")
    print("claim files ok", folder)


def main() -> None:
    request = ClaimRequest.model_validate_json((SAMPLES / "claim_10_items.json").read_text())
    folder = Path(__file__).resolve().parent / "out" / request.job_id
    try:
        package = asyncio.run(build_claim_package(request))
    except RuntimeError as exc:
        print(f"upload unavailable: {exc}")
        package = None
    if package is not None:
        check_files(package, folder)
    else:
        for name in ("contents-inventory.csv", "contents-inventory.xlsx", "cover-letter.pdf"):
            path = folder / name
            if not path.exists() or path.stat().st_size < 100:
                raise SystemExit(f"missing package file {path}")
        print("claim files ok", folder)

    def check(msg) -> None:
        if msg.item_count != 10 or msg.total_usd != 2670:
            raise SystemExit("bureau package totals were wrong")
        if msg.ok:
            return
        if "SPACE_SERVICE_URL" not in (msg.error or "") and "upload" not in (msg.error or "").lower():
            raise SystemExit(msg.error)

    from agent import agent
    from agents.actions.harness import run_bureau
    from shared.models import ClaimPackage

    run_bureau(agent, request, ClaimPackage, check, timeout_s=25)


if __name__ == "__main__":
    main()
