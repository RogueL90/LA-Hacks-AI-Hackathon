# cart

Turns verified product quotes into a plan, a subtotal, and the service fee.

**In:** `CartRequest`  
**Out:** `CartResult`

Line total is `price_usd * specs.quantity` (quantity defaults to 1). Quote order is impact order: the specialist puts the highest-severity fix first. If the subtotal is over `budget_usd`, items are removed from the end until it fits. `within_budget` describes the cart that is returned.

Quotes with `url_verified=false` are left out. A `specs.role` of `backup` is left out when the primary for that same `finding_id` (or query) is already in the cart.

`checkout_links` are merchant product URLs. They are a handoff, not a placed order. The Coordinator card must say that.

## Service fee

`service_fee_usd` is the flat string `"1.00"` when the cart has at least one item, and `"0.00"` when it does not. This is the Stripe test-mode fee for the plan. It is not a Fetch transaction and not a charge for the merchandise. Shresth shows `"1.00"` on the Stripe test card. The Payment Verifier charges it with `charge_test_fee`.

## Run

```bash
python agents/actions/cart/agent.py
python agents/actions/cart/test_local.py
```

Seed: `CART_SEED` (port 8012).
