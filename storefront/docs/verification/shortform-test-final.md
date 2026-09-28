VERDICT: PASS

# U5c - FINAL FUNCTIONAL RE-TEST on fixed artifact (one-time video pack unlock)

Artifact: https://shortform-studio-storefront.omnistack.workers.dev (deployed version 30c6f35d-4911-4f38-a7b2-af5cde90845f)
Repo: nexuslbs/shortform-studio main e87ef9c67698496d9de6062836e4dc7a81d12173 (/var/lib/workstation/projects/shortform-studio/repo)
Run (UTC): 2026-09-28 19:21:03 -> 19:26:xx. Raw log: /var/lib/workstation/work/shortform-test-final.log
Real headful chromium via facade http://localhost:8080/api/tool/call (provider playwright, remote CDP http://browser:9222), session default.
Credential read in-process from /var/lib/workstation/.credentials.yaml ($SANDBOX_POLAR_API_KEY_SHORTFORM_STUDIO); value never printed; header User-Agent: curl/8.5.0. No repo writes, no docker lifecycle verb.

## G3 new objects - PASS
Browser payment for /product/video-pack-roman-concrete submitted (form POST /api/checkout, email sandbox-buyer@nexuslbs.org); real Stripe card in the Polar checkout: card 4242 4242 4242 4242, exp 12 / 34, CVC 123; cardholder Sandbox Buyer, 123 Sandbox St, San Francisco, 94107, US-CA, US. hCaptcha "Verify" challenge was present and Pay now accepted after the challenge. Confirmed by sandbox API poll (NOT the /success redirect).
```
GET /v1/checkouts/460ec794-1baf-4324-ab3f-262403b85e14 ->
{"id": "460ec794-1baf-4324-ab3f-262403b85e14", "status": "succeeded", "intent_status": null, "product_id": "805fafde-0825-4732-8817-21d0bd412502", "total_amount": 1900, "customer_email": "sandbox-buyer@nexuslbs.org", "payment_method_type": "card"}
GET /v1/orders/?limit=10 (matched checkout_id) ->
{"id": "42d0269b-b8d8-4ddd-b50c-a07f6f6a4572", "status": "paid", "paid": true, "product_id": "805fafde-0825-4732-8817-21d0bd412502", "checkout_id": "460ec794-1baf-4324-ab3f-262403b85e14", "total_amount": 1900, "customer_email": null, "subscription_id": null}
```
Checkout id 460ec794-1baf-4324-ab3f-262403b85e14, order id 42d0269b-b8d8-4ddd-b50c-a07f6f6a4572, product_id matches 805fafde-0825-4732-8817-21d0bd412502, no subscription_id (correct for one-time).

## G4 ledger - PASS
`curl -s https://shortform-studio-storefront.omnistack.workers.dev/ledger.jsonl` -> 200, SIZE 110102, saved to /var/lib/workstation/work/shortform-ledger-final.jsonl (21 rows). Exactly one row per event id:
```
G4 rows 21 unique_ids 21 dups {}
G4 types {"checkout.updated": 15, "subscription.created": 1, "subscription.active": 1, "order.created": 2, "order.paid": 2}
G4 tail:
   checkout.updated 6f2118c9-9cd4-4cd0-bc1e-4cd7ba4d0f3e 460ec794-1baf-4324-ab3f-262403b85e14 open
   checkout.updated f0624d18-ca36-4a31-85c7-7265547e2ffe 460ec794-1baf-4324-ab3f-262403b85e14 confirmed
   order.created 165c0f5a-0e20-4907-ba78-2f23c97f9eac 42d0269b-b8d8-4ddd-b50c-a07f6f6a4572 paid
   order.paid c5a7fe45-e379-448b-b4d8-4ec9b6581116 42d0269b-b8d8-4ddd-b50c-a07f6f6a4572 paid
   checkout.updated 715caca6-e9af-478b-bb21-cf84fb0526bf 460ec794-1baf-4324-ab3f-262403b85e14 succeeded
```
New ids present in the ledger: order.created 165c0f5a / order.paid c5a7fe45 both object_id 42d0269b (the new order), checkout.updated 715caca6 object_id 460ec794 status succeeded. No duplicate event ids.

## CORE VALUE (one-time unlock) - PASS
BEFORE payment (19:21:31, while checkout was still open):
```
curl -s -o /tmp/b4.txt -w '%{http_code}' <site>/download/video-pack-roman-concrete -> 403
{"error": "not_entitled"}
```
AFTER payment: `curl -s <site>/download/video-pack-roman-concrete` -> 200, full body:
```
{
  "slug": "video-pack-roman-concrete",
  "entitled": true,
  "name": "ShortForm Studio Video Pack: Roman Concrete",
  "product_id": "805fafde-0825-4732-8817-21d0bd412502",
  "price": {
    "amount": 1900,
    "currency": "usd",
    "recurring_interval": null,
    "display": "USD 19.00"
  },
  "amount": 1900,
  "currency": "usd",
  "recurring_interval": null,
  "artifacts": [
    {
      "path": "out/roman-concrete/video.mp4",
      "bytes": 2404763,
      "duration_s": 37.5,
      "resolution": "1080x1920",
      "qa": "17/17",
      "sha256": "9ce0e04ef5fe79fb27ec10fd2eb16efedc024b9dbe48d1c62827b45f8dfff206"
    }
  ],
  "manifest": {
    "path": "out/roman-concrete/video.mp4",
    "bytes": 2404763,
    "duration_s": 37.5,
    "resolution": "1080x1920",
    "qa": "17/17",
    "sha256": "9ce0e04ef5fe79fb27ec10fd2eb16efedc024b9dbe48d1c62827b45f8dfff206"
  }
}
```
All fields match the acceptance: path out/roman-concrete/video.mp4, bytes 2404763, duration_s 37.5, resolution 1080x1920, qa 17/17, sha256 9ce0e04ef5fe79fb27ec10fd2eb16efedc024b9dbe48d1c62827b45f8dfff206. The manifest defect from U5a is FIXED (both top-level manifest and artifacts populated).

## Success page - PASS
`curl -s '<site>/success?checkout_id=460ec794-1baf-4324-ab3f-262403b85e14'`:
```
<h2>Entitlement unlocked</h2>
<li>order 42d0269b-b8d8-4ddd-b50c-a07f6f6a4572 status paid (paid)</li>
checkout 460ec794-1baf-4324-ab3f-262403b85e14 status succeeded
Open the download manifest  -> href /download/video-pack-roman-concrete
buyer: sandbox-buyer@nexuslbs.org
SANDBOX / DEMO - no real payment
```
Entitlement is for the VIDEO PACK (link /download/video-pack-roman-concrete, order for product 805fafde), not the old subscription.

## G5 static routes - PASS
`curl -s -o /dev/null -w '%{http_code}'`:
```
/ -> 200 ; /product/video-pack-roman-concrete -> 200 ; /product/studio-monthly-4 -> 200 ; /catalog.json -> 200 ; /cancel -> 200 ; /healthz -> 200
```

## G7 palette (fixed) - PASS, 0 deployed hexes outside palette
Union of `/`, `/product/video-pack-roman-concrete`, `/product/studio-monthly-4`, `/cancel`:
```
#06b6d4 #0a0f1e #0d1321 #10b981 #111827 #3b82f6 #64748b #8b5cf6 #94a3b8 #a78bfa #f1f5f9 #f43f5e #f59e0b  (13)
```
Palette from grep -oE '#[0-9a-fA-F]{6}' /opt/workspace/omni-dashboard/src/style.css (38):
```
#06b6d4 #0a0f1e #0d1321 #10b981 #111827 #1a1a2e #22c55e #22d3ee #30363d #34d399 #3b82f6 #475569 #4ade80 #58a6ff #60a5fa #6366f1 #64748b #6ee7b7 #7c3aed #818cf8 #8b5cf6 #93c5fd #94a3b8 #a78bfa #a855f7 #c084fc #cbd5e1 #d2a8ff #e0e0e0 #e8b64c #ef4444 #f1f5f9 #f43f5e #f59e0b #f85149 #facc15 #fb7185 #fbbf24
```
`comm -23` deployed vs palette -> EMPTY (OUTSIDE_PALETTE: none). The orphan #0b1020 is gone.

## G8 sandbox notice + honesty - PASS
```
G8 / notice=2 forbidden=0
G8 /product/video-pack-roman-concrete notice=2 forbidden=0
G8 /product/studio-monthly-4 notice=2 forbidden=0
G8 /cancel notice=1 forbidden=0
```
`SANDBOX / DEMO - no real payment` present on each page; 0 matches for 127\.0\.0\.1:8799|MOCKCO_|placeholder checkout.

## G9 repo SHA - PASS
```
git -C /var/lib/workstation/projects/shortform-studio/repo rev-parse HEAD
e87ef9c67698496d9de6062836e4dc7a81d12173
git ls-remote origin refs/heads/main
e87ef9c67698496d9de6062836e4dc7a81d12173	refs/heads/main
```
(Note: a second stale clone /opt/workspace/shortform-studio sits at 11f951d3; the workstation project repo used for the artifact comparison is /var/lib/workstation/projects/shortform-studio/repo, which matches the deployed commit.)

## Sanity (subscription still works) - PASS
`curl -s <site>/download/studio-monthly-4` -> 200:
```
{"slug": "studio-monthly-4", "entitled": true, "name": "ShortForm Studio Monthly - 4 videos/month",
 "product_id": "a000e958-094a-4662-b79f-aeace122904a",
 "price": {"amount": 2900, "currency": "usd", "recurring_interval": "month", "display": "USD 29.00"},
 "amount": 2900, "currency": "usd", "recurring_interval": "month", "artifacts": [],
 "note": "No single downloadable artifact: ... recurring subscription ...",
 "subscription": {"id": "153e6e7a-24f4-48ea-b91d-500eeb7bbf8d", "status": "active", "current_period_end": "2026-10-28T19:08:54.174055Z"}}
```
product_id a000e958-094a-4662-b79f-aeace122904a and the subscription block present.

## NOT-VERIFIED / UNKNOWN
- G10 YouTube OAuth leg: still blocked (human step, no Google credential). Not attempted.
- G1/G2 credential + authenticated products list were part of U5a; this run read the credential in-process only and did not re-list products (G3 API responses prove the credential worked).

## my usage (raw)
```
sessionId	llmCalls	toolCalls	steps	turns	inputTokens	outputTokens	cacheReadTokens	cacheWriteTokens	totalTokens	wallSecs	firstTimeMs	lastTimeMs	events	badLines	log
session-cad92f12-873d-4a8c-89a1-c2c8a50d3d28	31	0	31	1	30056	16897	1114752	0	1161705	223.992	1790623261107	1790623485099	217	0	/opt/omni/data/workstation/dsh-home/sessions/--var-lib-workstation-projects-shortform-studio--/session-cad92f12-873d-4a8c-89a1-c2c8a50d3d28/session.v4.jsonl.zstd
```
