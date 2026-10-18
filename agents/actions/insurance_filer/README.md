![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

# Insurance Claim Filer

Builds a contents package the household can send to an insurer. It does not file the claim.

**In:** `ClaimRequest`  
**Out:** `ClaimPackage`

Files, written under `out/<job_id>/`:

- `contents-inventory.xlsx` and `contents-inventory.csv` — room, item, description, brand/model, quantity, age, replacement cost, value basis (Receipt, Measured, Confirmed, or Estimate), evidence link. Each room has a total, and the sheet has an overall total.
- `cover-letter.pdf` — claimant placeholders, loss summary, totals, attachment list, and a California advance-contents paragraph citing Insurance Code section 10103.7. The letter says to confirm the percentage and cap that apply to the policy.

Room, brand, model, and age are read from `product_query.constraints` when the claim agent sends them.

When `SPACE_SERVICE_URL` is set, each file is posted to `POST /media/upload` and the returned URLs are placed on `ClaimPackage`. If that upload fails, the agent reports a retryable error and leaves the files on disk. If the URL is unset, `ok=false` and `error` points at the local folder. `total_usd` and `item_count` are still filled.

## Run

```bash
python agents/actions/insurance_filer/agent.py
python agents/actions/insurance_filer/test_local.py
```

Seed: `INSURANCE_FILER_SEED` (port 8014).
