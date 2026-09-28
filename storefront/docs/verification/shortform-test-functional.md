# U5a End-to-end sandbox payment test - functional

VERDICT: PASS (G1,G2,G3,G4,G5,G8,G9); ONE DEFECT reported (not patched): /download/<slug> returns `"manifest": null` and `"product_id": null`. G10 BLOCKED by design. One-time `video-pack-roman-concrete` buy was NOT run (NOT-VERIFIED).

Artifact: https://shortform-studio-storefront.omnistack.workers.dev @ repo nexuslbs/shortform-studio main e49b0ad428922f85a13a6e1c9dd60a1701823c86
Run (UTC): 2026-09-28 19:04:47 -> 19:09:22. Raw log: /var/lib/workstation/work/shortform-test-functional.log. Ledger saved: /var/lib/workstation/work/shortform-ledger.jsonl

## G1 credential (PASS)
SANDBOX_POLAR_API_KEY_SHORTFORM_STUDIO present in /var/lib/workstation/.credentials.yaml, length=53; used in-process only, header User-Agent: curl/8.5.0. Value never printed.

## G2 authenticated products (PASS)
GET https://sandbox-api.polar.sh/v1/products?limit=100 -> 200, items=4:
- a000e958-094a-4662-b79f-aeace122904a ShortForm Studio Monthly - 4 videos/month
- a1db888e-5b82-435e-82c1-3e3a80a6acb2 ShortForm Caption + Metadata Kit
- d7c598b6-bb7c-4770-8db3-a894f488a1dc ShortForm Studio 3-Pack
- 805fafde-0825-4732-8817-21d0bd412502 ShortForm Studio Video Pack: Roman Concrete

## G5 static routes (PASS)
curl -s -o /dev/null -w '%{http_code} %{size_download}':
- / -> 200 7665
- /product/video-pack-roman-concrete -> 200 7382
- /product/studio-monthly-4 -> 200 6750
- /catalog.json -> 200 2194
- /cancel -> 200 5904
- /healthz -> 200 187

## G8 sandbox notice + honesty grep (PASS)
grep -cE '127\.0\.0\.1:8799|MOCKCO_|placeholder checkout' on / HTML = 0 (forbidden_matches=0); page contains `SANDBOX / DEMO - no real payment`.

## G3 end-to-end sandbox payment (PASS)
Real headful chromium via facade http://localhost:8080/api/tool/call (session default).
1. NAV https://shortform-studio-storefront.omnistack.workers.dev/product/studio-monthly-4 -> 200, form: `<form action=/api/checkout>` with hidden slug=studio-monthly-4 and email input.
2. Filled email sandbox-buyer@nexuslbs.org, submitted form via JS requestSubmit(); POST /api/checkout -> 302 (opaqueredirect) to Polar.
3. Polar checkout page loaded (js.stripe.com Elements assets). Filled Stripe iframe fields via act frameId=pw:4: Card number `4242424242424242`, Expiration `12 / 34`, Security code `123`; main frame: Cardholder name `Sandbox Buyer`, line1 `123 Sandbox St`, postal `94107`, city `San Francisco`, State `US-CA`, Country `US`. Clicked `Subscribe now`; page showed "Waiting confirmation from ShortForm Studio".
4. API poll (raw):
   - GET /v1/checkouts/cc879d19-c02a-4ae1-8ef7-3be3affb7ad6 -> 200 status=succeeded
   - GET /v1/orders/?limit=10 -> 200, order id 3ebdac24-5360-47e5-b6fb-3e0e2ccf6615 `"status":"paid","paid":true,"total_amount":2900,"product_id":"a000e958-094a-4662-b79f-aeace122904a","subscription_id":"153e6e7a-24f4-48ea-b91d-500eeb7bbf8d","checkout_id":"cc879d19-c02a-4ae1-8ef7-3be3affb7ad6"`
   - GET /v1/subscriptions/?limit=10 -> 200, id 153e6e7a-24f4-48ea-b91d-500eeb7bbf8d `"status":"active"`, period 2026-09-28 -> 2026-10-28, checkout_id cc879d19-c02a-4ae1-8ef7-3be3affb7ad6
   - checkout raw: `"status":"succeeded"`, `"intent_status":"succeeded"`, payment_method_type card, product a000e958...

## G4 ledger (PASS)
GET <site>/ledger.jsonl -> saved 13 rows. Duplicate event ids: NONE (every one of 13 ids count=1).
Types: checkout.updated=9, subscription.created=1, subscription.active=1, order.created=1, order.paid=1.
Ledger tail includes:
- order.paid id 851a819d-aed2-4159-a19e-ef9263d80ad8 object_id 3ebdac24-... status paid subscription_id 153e6e7a-...
- checkout.updated id c23f546f-cc16-4e43-8ec8-54f66ff7afe9 object_id cc879d19-... status succeeded
Bad-signature POST <site>/webhooks/polar (header `webhook-signature: v1,bogus`) -> 401 `{"error":"invalid_signature"}`; ledger lines before=13 after=13 (no new row).

## Entitlement flip (PASS on flip; DEFECT on manifest)
BEFORE: /download/studio-monthly-4 -> 403 125 ; /download/video-pack-roman-concrete -> 403 134.
AFTER: /download/studio-monthly-4 -> 200 149 body:
```
{ "slug": "studio-monthly-4", "entitled": true, "name": "ShortForm Studio Monthly - 4 videos/month", "product_id": null, "manifest": null }
```
/download/video-pack-roman-concrete STILL 403 (correct, not purchased).
`/success?checkout_id=cc879d19-c02a-4ae1-8ef7-3be3affb7ad6` text: `<h2>Entitlement unlocked</h2><ul><li>order 3ebdac24-... status paid</li><li>subscription 153e6e7a-... status active until 2026-10-28T19:08:54Z</li></ul>` + link `/download/studio-monthly-4`.
DEFECT: the entitled response has `"manifest": null` and `"product_id": null` although the page's "Manifest JSON" link points at /download/studio-monthly-4. Acceptance asked for the manifest JSON; the entitlement flag flips but the manifest payload is absent.

## G9 repo SHA (PASS)
git rev-parse HEAD = e49b0ad428922f85a13a6e1c9dd60a1701823c86 ; git ls-remote origin refs/heads/main = e49b0ad428922f85a13a6e1c9dd60a1701823c86. Match.

## G10 YouTube leg (UNCHANGED / BLOCKED)
No Google credential in /var/lib/workstation/.credentials.yaml; OAuth handover is a human step. Not attempted.

## NOT-VERIFIED
- One-time `video-pack-roman-concrete` buy + its ledger row + entitlement: NOT RUN (wall clock). The subscription flow is fully verified; the one-time flow is not.
- Manifest JSON payload content: NOT-VERIFIED (route returns null).
