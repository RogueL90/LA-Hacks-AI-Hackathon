"""Local checks for the Stripe test-mode Payment Verifier."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from agents.actions.envload import load_env
from shared.models import VerifyPaymentRequest
from shared.payments import StripeKeyError, charge_test_fee, verify_charge

load_env()


def check_helpers() -> None:
    matched, detail = verify_charge(
        {"id": "pi_test_123", "status": "succeeded", "currency": "usd", "amount": 100},
        "1.00",
    )
    if not matched or "Stripe test mode" not in detail or "pi_test_123" not in detail:
        raise SystemExit(detail)
    short, _ = verify_charge(
        {"id": "pi_test_123", "status": "succeeded", "currency": "usd", "amount": 50},
        "1.00",
    )
    if short:
        raise SystemExit("a short charge was accepted")
    try:
        charge_test_fee("1.00", secret_key="sk_live_not_allowed")
    except StripeKeyError:
        pass
    else:
        raise SystemExit("a live key was accepted")
    try:
        charge_test_fee("1.00", secret_key="")
    except StripeKeyError:
        pass
    else:
        raise SystemExit("a missing key was accepted")
    print("payment helper rules ok")


def main() -> None:
    check_helpers()
    has_test_key = os.environ.get("STRIPE_SECRET_KEY", "").startswith("sk_test_")
    request = VerifyPaymentRequest(job_id="job_fee_local_v2", service_fee_usd="1.00")

    def check(msg) -> None:
        if has_test_key:
            if not msg.verified or "Stripe test mode" not in msg.detail:
                raise SystemExit(msg.detail)
            if "pi_" not in msg.detail:
                raise SystemExit(msg.detail)
            return
        if msg.verified or "sk_test_" not in msg.detail:
            raise SystemExit(msg.detail)

    from agent import agent
    from agents.actions.harness import run_bureau
    from shared.models import VerifyPaymentResult

    run_bureau(agent, request, VerifyPaymentResult, check, timeout_s=30)


if __name__ == "__main__":
    main()
