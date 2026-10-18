# product_finder

Finds real products for any specialist mode. A quote is returned only after its page loads and the title or price shows up there.

**In:** `FindProductsRequest`  
**Out:** `FindProductsResult`

For each query the agent asks Claude (`ANTHROPIC_MODEL`, default `claude-sonnet-4-5`) to search the web for 3–5 candidates, fetches each URL with a 10 second timeout, and keeps `url_verified=true` only when the page matches. Numeric constraints are maximums (`length_in: 18` means the product is at most 18 inches). The cheapest verified fit is `specs.role = "primary"`. The next cheapest fit is `specs.role = "backup"`. Prices are stamped `specs.price_as_of`.

Every search in one request runs at the same time, and each one stops at 30 seconds. Partial results come back as `ok=true` with a note in `error`. If nothing verified, `ok=true`, `quotes=[]`, and `error` names the query.

Results are cached by the query string in `cache/queries.json` so a demo repeat does not search again. Set `CHAOS_PRODUCT_FINDER=1` to fail the first call once (`retryable`, payload is the request). The next call in that process runs normally.

## Run

From the repo root, with Python 3.11:

```bash
python agents/actions/product_finder/agent.py
python agents/actions/product_finder/test_local.py
```

`ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL` come from `.env`. Without a key, the agent returns `ok=false` and does not invent products. Seed: `PRODUCT_FINDER_SEED` (port 8011).
