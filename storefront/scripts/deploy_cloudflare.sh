#!/usr/bin/env bash
# Deploy the ShortForm Studio storefront to the Cloudflare Workers free tier.
#
# This script never fakes a deploy. With no $CLOUDFLARE_API_TOKEN or
# $CLOUDFLARE_ACCOUNT_ID it prints the human handover and exits 2. When the two
# Worker secrets are present in the environment they are pushed to the Worker
# over stdin (never echoed, never written to the repo), then wrangler deploys.
set -u

ASSET_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ASSET_DIR" || exit 1

if [ -z "${CLOUDFLARE_API_TOKEN:-}" ]; then
  echo 'HUMAN HANDOVER REQUIRED: create a Cloudflare API token with the "Edit Cloudflare Workers" template at https://dash.cloudflare.com/profile/api-tokens.'
  echo 'Set it in the environment variable CLOUDFLARE_API_TOKEN (platform secrets store; never commit it).'
  echo 'Then run: npx wrangler deploy --config wrangler.toml'
  exit 2
fi

if [ -z "${CLOUDFLARE_ACCOUNT_ID:-}" ]; then
  echo 'HUMAN HANDOVER REQUIRED: set CLOUDFLARE_ACCOUNT_ID (the account that owns the Worker).'
  exit 2
fi

POLAR_KEY="${POLAR_API_KEY:-${SANDBOX_POLAR_API_KEY_SHORTFORM_STUDIO:-}}"
if [ -n "$POLAR_KEY" ]; then
  printf '%s' "$POLAR_KEY" | npx wrangler secret put POLAR_API_KEY --config wrangler.toml >/dev/null
  echo 'SECRET_SET POLAR_API_KEY'
fi

if [ -n "${POLAR_WEBHOOK_SECRET:-}" ]; then
  printf '%s' "$POLAR_WEBHOOK_SECRET" | npx wrangler secret put POLAR_WEBHOOK_SECRET --config wrangler.toml >/dev/null
  echo 'SECRET_SET POLAR_WEBHOOK_SECRET'
fi

output="$(npx wrangler deploy --config wrangler.toml 2>&1)"
rc=$?
printf '%s\n' "$output"
if [ "$rc" -ne 0 ]; then
  echo "DEPLOY=FAIL exit=${rc}"
  exit "$rc"
fi
url="$(printf '%s\n' "$output" | grep -oE 'https://[^[:space:]]+\.workers\.dev[^[:space:]]*' | head -n 1)"
echo "DEPLOYED_URL=${url:-unknown}"
