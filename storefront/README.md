# ShortForm Studio storefront (Polar SANDBOX)

A deployable Cloudflare Worker that sells the canonical ShortForm Studio
catalog through the **Polar sandbox**. It adapts the P1 asset-pipeline
storefront.

> **SANDBOX / DEMO - no real payment.** The Worker pins
> `https://sandbox-api.polar.sh/v1`, refuses the live host `api.polar.sh`, and
> only ever uses Polar sandbox test cards. No live key is stored in this repo.

## Catalog

| slug | name | amount | kind |
| --- | --- | --- | --- |
| `video-pack-roman-concrete` | ShortForm Studio Video Pack: Roman Concrete | USD 1900 cents | one time |
| `shorts-bundle-3` | ShortForm Studio 3-Pack | USD 2900 cents | one time |
| `caption-kit` | ShortForm Caption + Metadata Kit | USD 900 cents | one time |
| `studio-monthly-4` | ShortForm Studio Monthly - 4 videos/month | USD 2900 cents | subscription, month |

The same slugs/prices live in `storefront/catalog.json`, the Worker catalog
constant, and `shortform/billing/polar.py` `CATALOG` / `PRODUCTS`.

## Files

- `worker/worker.js` - the Worker (routes: `/`, `/product/<slug>`,
  `/api/checkout`, `/success`, `/cancel`, `/webhooks/polar`, `/ledger`,
  `/ledger.jsonl`, `/catalog.json`, `/download/<slug>`, `/healthz`).
- `wrangler.toml` - Worker name, sandbox var, `LEDGER` KV binding.
- `catalog.json` - canonical catalog; `product_id` is `null` until provisioning.
- `scripts/provision_products.mjs` - idempotent Polar product provisioning.
- `scripts/deploy_cloudflare.sh` - secret put + `wrangler deploy`.
- `scripts/smoke.mjs` - local assertions, no network, no key.

## Runbook (sandbox only)

All commands run from `storefront/`. The Polar key is read from the environment
and never printed or written to the repo. The harness credential name is
`SANDBOX_POLAR_API_KEY_SHORTFORM_STUDIO`; it materialises as an env var of the
same name.

```sh
# 1. Provision the 4 products into the sandbox (idempotent by slug) and write
#    the returned product ids back into catalog.json.
POLAR_API_KEY="$SANDBOX_POLAR_API_KEY_SHORTFORM_STUDIO" \
  node scripts/provision_products.mjs

# 2. Create the durable ledger KV namespace, then paste its id over
#    REPLACE_WITH_LEDGER_KV_ID in wrangler.toml.
npx wrangler kv namespace create LEDGER

# 3. Push the Worker secrets (stdin only, never echoed).
printf '%s' "$SANDBOX_POLAR_API_KEY_SHORTFORM_STUDIO" | \
  npx wrangler secret put POLAR_API_KEY --config wrangler.toml
printf '%s' "$POLAR_WEBHOOK_SECRET" | \
  npx wrangler secret put POLAR_WEBHOOK_SECRET --config wrangler.toml

# 4. Deploy.
npx wrangler deploy --config wrangler.toml
# or, with both Cloudflare vars set:
CLOUDFLARE_API_TOKEN=... CLOUDFLARE_ACCOUNT_ID=... bash scripts/deploy_cloudflare.sh

# 5. Webhook endpoint to register in the Polar sandbox dashboard:
#    https://<worker>.workers.dev/webhooks/polar
#    Copy the endpoint's whsec_ secret into POLAR_WEBHOOK_SECRET (step 3).
```

## Deployed endpoints (SANDBOX, UNLISTED - do not promote)

- Worker URL: https://shortform-studio-storefront.omnistack.workers.dev
- Ledger KV namespace: `SHORTFORM_LEDGER` id
  `29bc2131cefe46c2a4125c199d83197a` (binding `LEDGER`, see `wrangler.toml`).
- Polar sandbox webhook endpoint: `3d934b6a-6f86-4088-9a52-7a568e0a2d26`
  -> `POST /webhooks/polar` (`format: raw`, `uses_standard_webhook_signature: true`).
- Pinned to `https://sandbox-api.polar.sh/v1`; no live key.
- Verified 2026-09-28: `/`, `/product/video-pack-roman-concrete`, `/catalog.json`,
  `/cancel`, `/healthz` all HTTP 200; `/healthz` reports `ledger_binding: true`;
  every page carries `SANDBOX / DEMO - no real payment`.
- This route is intentionally unlisted: no promotion, no release, no outreach.

## Local verification

```sh
node --check worker/worker.js
node scripts/smoke.mjs
```

`smoke.mjs` imports the Worker `fetch` with a stub env (in-memory KV and a stub
global `fetch` for the Polar API). It performs no deploy and no real Polar API
call, and it needs no credential.

## Palette

The UI uses only the omni-dashboard palette tokens:
`#0a0f1e`, `#111827`, `#0d1321`, `#f1f5f9`, `#94a3b8`, `#64748b`, `#8b5cf6`,
`#a78bfa`, `#06b6d4`, `#f59e0b`, `#f43f5e`, `#10b981`, `#3b82f6`.
Every page shows `SANDBOX / DEMO - no real payment`.
