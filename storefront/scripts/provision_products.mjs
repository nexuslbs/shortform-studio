#!/usr/bin/env node
// Provision the storefront/catalog.json items as Polar SANDBOX products.
//
// Idempotent by slug: it lists /v1/products/?limit=100, matches metadata.slug
// (and a top-level slug when present), and reuses an existing product instead
// of creating a duplicate. One-time products are created WITHOUT
// recurring_interval; the subscription is created WITH recurring_interval
// "month". The returned product ids are written back into catalog.json.
//
// Usage (the key is read from the environment and never printed):
//   POLAR_API_KEY=... node scripts/provision_products.mjs
//   SANDBOX_POLAR_API_KEY_SHORTFORM_STUDIO=... node scripts/provision_products.mjs
//
// Sandbox host only. There is no import of api.polar.sh.

import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const BASE = "https://sandbox-api.polar.sh/v1";
const SOURCE = "shortform-studio-mvp-catalog";
const here = dirname(fileURLToPath(import.meta.url));
const catalogPath = join(here, "..", "catalog.json");

if (!BASE.startsWith("https://sandbox-api.polar.sh")) {
  throw new Error("sandbox host only");
}

const key = process.env.POLAR_API_KEY || process.env.SANDBOX_POLAR_API_KEY_SHORTFORM_STUDIO;
if (!key) {
  console.error("POLAR_API_KEY (or SANDBOX_POLAR_API_KEY_SHORTFORM_STUDIO) is required");
  process.exit(2);
}

const catalog = JSON.parse(await readFile(catalogPath, "utf8"));

async function api(path, init = {}) {
  const response = await fetch(BASE + path, {
    ...init,
    headers: {
      Accept: "application/json",
      Authorization: "Bearer " + key,
      ...(init.headers || {}),
    },
  });
  const text = await response.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  return { response, data };
}

const existing = new Map();
let page = 1;
for (;;) {
  const { response, data } = await api("/products/?limit=100&page=" + page);
  if (!response.ok) {
    console.error("product list failed: HTTP " + response.status);
    process.exit(1);
  }
  const items = (data && data.items) || [];
  for (const product of items) {
    const slug = (product && product.metadata && product.metadata.slug) || (product && product.slug);
    if (slug) existing.set(slug, product);
  }
  if (items.length < 100) break;
  page += 1;
  if (page > 20) break;
}

let created = 0;
let skipped = 0;
const ids = {};
for (const item of catalog.items || []) {
  const found = existing.get(item.slug);
  if (found) {
    console.log("SKIP   " + item.slug + " -> " + found.id);
    ids[item.slug] = found.id;
    skipped += 1;
    continue;
  }
  const body = {
    name: item.name,
    description: item.description,
    visibility: "public",
    prices: [
      {
        amount_type: "fixed",
        price_amount: item.amount,
        price_currency: (item.currency || "usd").toLowerCase(),
      },
    ],
    metadata: { slug: item.slug, source: SOURCE },
  };
  if (item.recurring_interval) {
    body.recurring_interval = item.recurring_interval;
  }
  const { response, data } = await api("/products/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    console.error("CREATE FAIL " + item.slug + " HTTP " + response.status);
    process.exit(1);
  }
  console.log("CREATE " + item.slug + " -> " + data.id);
  ids[item.slug] = data.id;
  created += 1;
}

for (const item of catalog.items || []) {
  if (ids[item.slug]) item.product_id = ids[item.slug];
}
await writeFile(catalogPath, JSON.stringify(catalog, null, 2) + "\n", "utf8");

console.log("DONE created=" + created + " skipped=" + skipped + " catalog=" + catalogPath);
