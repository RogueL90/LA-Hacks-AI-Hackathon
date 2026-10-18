"""Local checks for Cart."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from agents.actions.cart.logic import build_cart
from agents.actions.envload import load_env
from shared.models import CartRequest

load_env()
SAMPLES = ROOT / "evals" / "samples"


def check_samples() -> None:
    over = CartRequest.model_validate_json((SAMPLES / "cart_over_budget.json").read_text())
    result = build_cart(over)
    if [item.title for item in result.items] != ["18 in grab bar"]:
        raise SystemExit(f"budget trim failed: {[item.title for item in result.items]}")
    if result.subtotal_usd != 40 or not result.within_budget:
        raise SystemExit(f"subtotal {result.subtotal_usd} within {result.within_budget}")
    if result.service_fee_usd != "1.00":
        raise SystemExit(f"fee {result.service_fee_usd}")
    if result.checkout_links != ["https://example.com/grab-bar"]:
        raise SystemExit("checkout link was not the kept merchant URL")

    bad = CartRequest.model_validate_json((SAMPLES / "cart_bad_url.json").read_text())
    kept = build_cart(bad)
    if [item.title for item in kept.items] != ["Verified night light"]:
        raise SystemExit("unverified URL was kept")
    if kept.subtotal_usd != 12 or kept.service_fee_usd != "1.00":
        raise SystemExit("bad-url cart totals were wrong")
    print("cart rules ok")


def main() -> None:
    check_samples()
    request = CartRequest.model_validate_json((SAMPLES / "cart_over_budget.json").read_text())

    def check(msg) -> None:
        if not msg.ok or not msg.within_budget or msg.subtotal_usd != 40:
            raise SystemExit("bureau cart did not meet the budget")
        if msg.service_fee_usd != "1.00":
            raise SystemExit("bureau cart fee was not 1.00")

    from agent import agent
    from agents.actions.harness import run_bureau
    from shared.models import CartResult

    run_bureau(agent, request, CartResult, check)


if __name__ == "__main__":
    main()
