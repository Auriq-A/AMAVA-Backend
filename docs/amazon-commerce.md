# Amazon eligibility and profit endpoints

The current stack is `amava_api` + `amava_agent` + `amava_db`. Start it with:

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn amava_api.app:app --host 0.0.0.0 --port 51483 --reload
```

The updated `run_everything.ps1` starts this API and the current ADK agent.

## Connect SP-API

Save credentials for the signed-in user. `seller_id` is required for listing
restriction checks.

```http
POST /api/credentials/spapi
X-API-Key: amava_sk_...
Content-Type: application/json

{
  "client_id": "...",
  "client_secret": "...",
  "refresh_token": "...",
  "seller_id": "...",
  "marketplace": "US"
}
```

## Gated/ungated checks

`POST /check-products` accepts ASINs, UPCs/EANs, or titles. If `values` is
omitted, the endpoint checks the user's values previously saved to
`POST /search-key`. `/check-ungated` is an alias.

```json
{
  "values": ["012345678905", "B000TEST01"],
  "unit": "search_key",
  "condition_type": "new_new"
}
```

Results are returned and stored in `/checkeddata`. Progress is available from
`GET /amazon-checking-status`. Each item includes `productASIN`, `eligibility`,
`approval_required`, Amazon reason codes/messages, and the legacy `status`.

## FBA calculator

If `price` is omitted, the calculator selects the lowest New
Amazon-fulfilled offer.

```http
POST /fba-profit-calculator

{"asin":"B000TEST01","cost":10.00}
```

`POST /revcalall` is the FBA-only Check All route. It uses stored scraped data
and ASIN matches from `/checkeddata`.

## Manual FBM calculator

FBM is single-product only. If `price` is omitted, it selects the lowest New
merchant-fulfilled offer; otherwise the supplied selling price is used.

```http
POST /fbm-profit-calculator

{
  "asin": "B000TEST01",
  "cost": 10.00,
  "price": 40.00,
  "customer_shipping": 5.00,
  "shipping_cost": 7.00,
  "other_costs": 0.00,
  "currency_code": "USD"
}
```

`customer_shipping` is paid by the buyer and counts as revenue.
`shipping_cost` is the seller's actual carrier/inbound shipping expense.

Both calculators retrieve the seller's Amazon fee estimate and return total
fees, fulfillment fee, fee breakdown, profit, margin, and ROI. Amazon fee
responses are estimates and actual fees can differ.

## Offline tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
