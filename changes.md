# Pranay — action agents

Branch: `pranay`. These four agents are the steps every specialist can call. Shresth deploys them and routes to them from the Coordinator. They are not the chat the user talks to.

## What changed from the original brief

- Product search uses **Claude** (`ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`) with Anthropic web search. It does not use Gemini.
- The service fee is **Stripe test mode**, not a Fetch transaction and not a tx hash.
- `CartResult.service_fee_usd` replaces `service_fee_fet`.
- `VerifyPaymentRequest` is `job_id`, `service_fee_usd`, and `trace`. There is no `tx_hash`, recipient, or chain check.
- All product queries in one request run **at the same time**. Each query still stops at 30 seconds. A list of about 30 products takes on the order of 20 seconds, not 30 separate waits.
- A quote is returned only when its page loads and the title or price shows up. Amazon often fails that check, so some real products are left out on purpose.

## Agents

| Agent | Name | Port | Seed env | In | Out |
|---|---|---|---|---|---|
| Product Finder | `lmh-product-finder` | 8011 | `PRODUCT_FINDER_SEED` | `FindProductsRequest` | `FindProductsResult` |
| Cart | `lmh-cart` | 8012 | `CART_SEED` | `CartRequest` | `CartResult` |
| Payment Verifier | `lmh-payment-verifier` | 8013 | `PAYMENT_VERIFIER_SEED` | `VerifyPaymentRequest` | `VerifyPaymentResult` |
| Insurance Filer | `lmh-insurance-filer` | 8014 | `INSURANCE_FILER_SEED` | `ClaimRequest` | `ClaimPackage` |

Message types are in `shared/models.py`. `shared/addresses.json` has empty strings for these agents. Fill the real Agentverse addresses there. Do not hardcode them.

Handlers call Kenil's `@traced_agent` and `report_error` when `observability` is installed. Until then they log an `AgentError` and still return a result.

Local check, from the repo root:

```bash
.venv/bin/python agents/actions/cart/test_local.py
.venv/bin/python agents/actions/payment_verifier/test_local.py
.venv/bin/python agents/actions/insurance_filer/test_local.py
.venv/bin/python agents/actions/product_finder/test_local.py
```

## Shresth — wire the Coordinator

**Fix plan**

1. Send `FindProductsRequest` with one `ProductQuery` per fix. Put `finding_id` in `constraints` if the card should keep the link to the finding. `quantity` is on the query.
2. Send the returned quotes to `CartRequest`. List order is impact order: highest severity first. Cart drops unverified quotes. It also drops a `specs.role == "backup"` quote when the primary for that same `finding_id` or query is already in the cart.
3. Show `items`, `subtotal_usd`, `within_budget`, and `service_fee_usd`. `checkout_links` are merchant product URLs. The card must say this is a **handoff, not an order**.
4. On Approve, show the Stripe test card for `service_fee_usd` using `STRIPE_PUBLISHABLE_KEY`. Dummy card `4242424242424242`.
5. Send `VerifyPaymentRequest(job_id, service_fee_usd)`. On `verified=true`, show the receipt. `detail` already says **Stripe test mode, not a real charge** and includes the PaymentIntent id. Show the same handoff links again.

**Fee**

- Flat `"1.00"` USD per cart that has at least one item. `"0.00"` when the cart is empty.
- This is not the merchandise total. One plan is one dollar, no matter how many products were searched.
- Import helpers from `shared/payments.py`: `FLAT_SERVICE_FEE_USD`, `format_service_fee_usd`, `charge_test_fee`, `verify_charge`.
- The verifier charges with `STRIPE_SECRET_KEY`. Both keys must start with `sk_test_` / `pk_test_`. A live key is refused.
- `job_id` is the Stripe idempotency key, so a retry of the same job does not create a second charge.

**Claim package**

Send `ClaimRequest` with `kind="item"` findings (`value_usd`, `value_basis`, evidence frame URL). Put `room`, `brand`, `model`, and `age_years` on `product_query.constraints` when you have them. The card should show `item_count`, `total_usd`, and the three download URLs. The package is **ready to send**. It has not been filed with an insurer.

## Aditya — upload

Insurance Filer `POST`s each file to `{SPACE_SERVICE_URL}/media/upload` as multipart field `file` and reads `{"url": "..."}`.

Files written locally at `agents/actions/insurance_filer/out/<job_id>/`:

- `contents-inventory.xlsx`
- `contents-inventory.csv`
- `cover-letter.pdf` (includes the California Insurance Code §10103.7 advance-contents paragraph)

If the service is down, `ok=false`, `total_usd` and `item_count` are still set, and `error` names that folder. There are no download URLs until upload succeeds.

## Kenil — tracing and the chaos flag

`CHAOS_PRODUCT_FINDER=1` makes Product Finder fail the first call in that process (`retryable=true`, `retry_payload` is the request). The next call runs normally. Use that for the Recovery demo.

Product Finder also calls `report_error` on a real failure. Pass `trace` through on every request so the Sentry trace stays one job.

## Env added on this branch

Already present in `.env.example`:

- `STRIPE_SECRET_KEY`
- `STRIPE_PUBLISHABLE_KEY`
- `CHAOS_PRODUCT_FINDER`

`ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL` were already on `main`. Product Finder uses whatever `ANTHROPIC_MODEL` is set to. `requirements.txt` keeps `anthropic==1.15.0` from `main` and adds `stripe`, `openpyxl`, `reportlab`, and `sentry-sdk`.

## Known limits

- A fresh product search can still return nothing when the store page does not contain the title or price. The result is `ok=true` with fewer quotes and a note in `error`.
- Repeating the exact same query string is instant. Results are cached in `agents/actions/product_finder/cache/queries.json` (gitignored).
- `shared/models.py` on this branch matches the contract field names. List and dict defaults use Pydantic v1 `Field(default_factory=...)` because `uagents.Model` is Pydantic v1. Shresth owns that file. If `main` already has a copy, keep the field names and drop this one.
