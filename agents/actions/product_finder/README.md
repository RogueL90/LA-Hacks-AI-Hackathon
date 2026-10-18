![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

# Home Product Finder

Finds real products online and checks every one: the store page has to load and show the product or its price before it's offered.

## Ask it directly (ASI:One, Agentverse chat)

- "Find two 27 inch monitors under $150 each, a wireless keyboard and mouse"
- "Grab bars for a bathroom, one 18 in and two 24 in"
- "A hardware-mounted baby gate for a 39 in wide stair"

It splits the request into product searches, searches stores (Walmart, Target, Home Depot, Amazon, Wayfair and more), checks each page and price, and replies with a best pick and a backup per item, with links. For products that fit a measured room and one checkout for the whole cart, send a home video to **Last Mile Home**.

## Inside Last Mile Home

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
