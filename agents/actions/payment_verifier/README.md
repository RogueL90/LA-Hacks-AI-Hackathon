# payment_verifier

Charges `service_fee_usd` in Stripe test mode and checks the PaymentIntent.

**In:** `VerifyPaymentRequest` (`job_id`, `service_fee_usd`, `trace`)  
**Out:** `VerifyPaymentResult`

There is no transaction hash and no chain lookup. `shared/payments.py` does the work:

- `charge_test_fee(service_fee_usd)` creates a PaymentIntent in `usd` for the fee in cents and confirms it with `pm_card_visa` (dummy card `4242424242424242`).
- `verify_charge(...)` requires status `succeeded`, currency `usd`, and an amount that matches the fee.
- Keys that do not start with `sk_test_` or `pk_test_` are refused before any charge.

`verified=true` only when those checks pass. `detail` includes the PaymentIntent id and the words "Stripe test mode, not a real charge." The Coordinator receipt should use that same label.

`STRIPE_SECRET_KEY` stays on this agent. `STRIPE_PUBLISHABLE_KEY` is for Shresth's payment card. A `job_id` is the Stripe idempotency key so a retry does not create a second charge.

## Run

```bash
python agents/actions/payment_verifier/agent.py
python agents/actions/payment_verifier/test_local.py
```

Without a test secret key, the local test checks that a live-looking key is refused and that the agent returns `verified=false`. With `sk_test_...` in `.env`, the same test completes a real Stripe test-mode charge. Seed: `PAYMENT_VERIFIER_SEED` (port 8013).
