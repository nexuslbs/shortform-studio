#!/usr/bin/env node
// Local smoke test for the storefront Worker. No deploy, no network, no key.
//
// It imports the Worker fetch with a stub env (in-memory KV plus a stubbed
// global fetch for the Polar API) and asserts the routes, the entitlement
// gate, the webhook signature, the visible notice and the palette.

import { createHmac } from "node:crypto";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const worker = (await import(pathToFileURL(join(here, "..", "worker", "worker.js")).href)).default;

const ORIGIN = "https://shop.example";
const NOTICE = "SANDBOX / DEMO - no real payment";
const PALETTE = [
  "#0a0f1e", "#111827", "#0d1321",
  "#f1f5f9", "#94a3b8", "#64748b",
  "#8b5cf6", "#a78bfa", "#06b6d4",
  "#f59e0b", "#f43f5e", "#10b981", "#3b82f6",
];

let passed = 0;
let failed = 0;
const out = [];
function check(name, condition, detail = "") {
  if (condition) {
    passed += 1;
    out.push("  PASS  " + name + (detail ? "  [" + detail + "]" : ""));
  } else {
    failed += 1;
    out.push("  FAIL  " + name + (detail ? "  [" + detail + "]" : ""));
  }
}

/* ------------------------------------------------------------- stub env */

function makeKV() {
  const store = new Map();
  return {
    store,
    async get(key) {
      return store.has(key) ? store.get(key) : null;
    },
    async put(key, value) {
      store.set(key, value);
    },
    async list({ prefix = "", limit = 1000 } = {}) {
      const keys = [...store.keys()]
        .filter((name) => name.startsWith(prefix))
        .slice(0, limit)
        .map((name) => ({ name }));
      return { keys, list_complete: true };
    },
  };
}

const REMOTE = [
  { slug: "video-pack-roman-concrete", name: "ShortForm Studio Video Pack: Roman Concrete", amount: 1900, interval: null },
  { slug: "shorts-bundle-3", name: "ShortForm Studio 3-Pack", amount: 2900, interval: null },
  { slug: "caption-kit", name: "ShortForm Caption + Metadata Kit", amount: 900, interval: null },
  { slug: "studio-monthly-4", name: "ShortForm Studio Monthly - 4 videos/month", amount: 2900, interval: "month" },
];

function remoteProducts() {
  return REMOTE.map((item, index) => ({
    id: "prod_" + index,
    name: item.name,
    description: item.name + " (stub)",
    is_recurring: Boolean(item.interval),
    recurring_interval: item.interval,
    prices: [{ id: "price_" + index, price_amount: item.amount, price_currency: "usd" }],
    metadata: { slug: item.slug, source: "shortform-studio-mvp-catalog" },
  }));
}

function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

globalThis.fetch = async (input, init = {}) => {
  const target = typeof input === "string" ? input : input.url;
  const method = String(init.method || "GET").toUpperCase();
  if (target.includes("/products/?limit=100")) return jsonResponse({ items: remoteProducts() });
  if (target.includes("/orders/?limit=100")) return jsonResponse({ items: [] });
  if (target.includes("/subscriptions/?limit=100")) return jsonResponse({ items: [] });
  if (target.includes("/checkouts/") && method === "POST") {
    const body = JSON.parse(init.body || "{}");
    return jsonResponse({ id: "chk_smoke", url: "https://sandbox.polar.sh/checkout/chk_smoke", status: "open", ...body }, 201);
  }
  return jsonResponse({ error: "unexpected_url", target }, 404);
};

const secret = "whsec_" + Buffer.from("shortform-smoke-signing-key").toString("base64");
const env = {
  POLAR_API_BASE: "https://sandbox-api.polar.sh/v1",
  POLAR_API_KEY: "test_key",
  POLAR_WEBHOOK_SECRET: secret,
  LEDGER: makeKV(),
};

function get(path) {
  return worker.fetch(new Request(ORIGIN + path), env);
}

function sign(body, id = "msg_smoke", timestamp = String(Math.floor(Date.now() / 1000))) {
  const key = Buffer.from(secret.slice("whsec_".length), "base64");
  const digest = createHmac("sha256", key).update(id + "." + timestamp + "." + body).digest("base64");
  return { id, timestamp, signature: "v1," + digest };
}

function postWebhook(body, headers) {
  return worker.fetch(new Request(ORIGIN + "/webhooks/polar", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "webhook-id": headers.id,
      "webhook-timestamp": headers.timestamp,
      "webhook-signature": headers.signature,
    },
    body,
  }), env);
}

function fixedWidths(html) {
  const re = /(?<![-\w])width\s*:\s*(\d+)px/g;
  const found = [];
  let match;
  while ((match = re.exec(html)) !== null) found.push(Number(match[1]));
  return found;
}

function assertPage(name, html) {
  check(name + " has the sandbox notice", html.includes(NOTICE));
  const missing = PALETTE.filter((hex) => !html.includes(hex));
  check(name + " uses every palette hex", missing.length === 0, missing.join(","));
  check(name + " has the responsive viewport meta",
    html.includes('name="viewport" content="width=device-width, initial-scale=1"'));
  const widths = fixedWidths(html);
  check(name + " has no fixed px width above 375", widths.every((w) => w <= 375),
    widths.length ? "widths=" + widths.join(",") : "no fixed px widths");
}

/* ---------------------------------------------------------------- routes */

const home = await get("/");
const homeHtml = await home.text();
check("GET / = 200", home.status === 200, "status=" + home.status);
assertPage("home", homeHtml);

const product = await get("/product/video-pack-roman-concrete");
const productHtml = await product.text();
check("GET /product/video-pack-roman-concrete = 200", product.status === 200, "status=" + product.status);
assertPage("product page", productHtml);
check("product page lists the real artifact bytes", productHtml.includes("2404763"));
check("product page lists the real duration", productHtml.includes("37.5"));
check("product page lists the real resolution", productHtml.includes("1080x1920"));
check("product page lists the QA 17/17", productHtml.includes("17/17"));
check("product page lists the real sha256",
  productHtml.includes("9ce0e04ef5fe79fb27ec10fd2eb16efedc024b9dbe48d1c62827b45f8dfff206"));

const catalog = await get("/catalog.json");
const catalogJson = await catalog.json();
check("GET /catalog.json = 200", catalog.status === 200, "status=" + catalog.status);
check("catalog.json has 4 items", catalogJson.items.length === 4, "count=" + catalogJson.items.length);
const slugs = catalogJson.items.map((item) => item.slug).sort().join(",");
check("catalog.json slugs are canonical",
  slugs === ["caption-kit", "shorts-bundle-3", "studio-monthly-4", "video-pack-roman-concrete"].sort().join(","), slugs);
const amounts = catalogJson.items.map((item) => item.amount).join(",");
check("catalog.json amounts are canonical", amounts === "1900,2900,900,2900", amounts);
check("catalog.json marks the monthly item recurring",
  catalogJson.items.find((item) => item.slug === "studio-monthly-4").recurring_interval === "month");

const cancel = await get("/cancel");
const cancelHtml = await cancel.text();
check("GET /cancel = 200", cancel.status === 200, "status=" + cancel.status);
assertPage("cancel page", cancelHtml);

const health = await get("/healthz");
const healthJson = await health.json();
check("GET /healthz = 200", health.status === 200, "status=" + health.status);
check("healthz reports sandbox", healthJson.provider_env === "sandbox", JSON.stringify(healthJson));

const missing = await get("/product/not-a-real-slug");
check("unknown slug = 404", missing.status === 404, "status=" + missing.status);

/* ----------------------------------------------------------- entitlement */

const denied = await get("/download/video-pack-roman-concrete");
const deniedJson = await denied.json();
check("/download without entitlement = 403", denied.status === 403, "status=" + denied.status);
check("denied download explains why", deniedJson.error === "not_entitled", JSON.stringify(deniedJson));

/* -------------------------------------------------------------- webhook */

const badBody = JSON.stringify({ type: "order.paid", data: { id: "ord_bad", status: "paid" } });
const bad = await postWebhook(badBody, { id: "msg_bad", timestamp: String(Math.floor(Date.now() / 1000)), signature: "v1,AAAA" });
check("bad signature = 401", bad.status === 401, "status=" + bad.status);
check("bad signature writes NO ledger row", env.LEDGER.store.size === 0, "rows=" + env.LEDGER.store.size);

const paidBody = JSON.stringify({
  type: "order.paid",
  data: { id: "ord_smoke", status: "paid", total_amount: 1900, metadata: { slug: "video-pack-roman-concrete" } },
});
const good = await postWebhook(paidBody, sign(paidBody));
const goodJson = await good.json();
check("good signature = 200", good.status === 200, "status=" + good.status);
check("good signature persists a row", goodJson.persisted === true && goodJson.duplicate === false, JSON.stringify(goodJson));
check("ledger holds exactly one row", env.LEDGER.store.size === 1, "rows=" + env.LEDGER.store.size);

const replay = await postWebhook(paidBody, sign(paidBody));
const replayJson = await replay.json();
check("replayed event is idempotent", replayJson.duplicate === true, JSON.stringify(replayJson));
check("ledger still holds one row after replay", env.LEDGER.store.size === 1, "rows=" + env.LEDGER.store.size);

const allowed = await get("/download/video-pack-roman-concrete");
const allowedJson = await allowed.json();
check("/download with entitlement = 200", allowed.status === 200, "status=" + allowed.status);
check("entitled download returns the real manifest",
  allowedJson.entitled === true && allowedJson.manifest && allowedJson.manifest.bytes === 2404763,
  JSON.stringify(allowedJson.manifest));
check("entitled manifest carries the sha256",
  allowedJson.manifest.sha256 === "9ce0e04ef5fe79fb27ec10fd2eb16efedc024b9dbe48d1c62827b45f8dfff206");
check("entitled manifest sha256 is 64 hex chars",
  /^[0-9a-f]{64}$/.test(String(allowedJson.manifest.sha256)), String(allowedJson.manifest.sha256).length + " chars");
check("entitled manifest carries the resolution", allowedJson.manifest.resolution === "1080x1920");
check("entitled manifest carries the duration", allowedJson.manifest.duration_s === 37.5);
check("video-pack download carries the real product_id",
  allowedJson.product_id === "805fafde-0825-4732-8817-21d0bd412502", "product_id=" + allowedJson.product_id);
check("video-pack download carries the price",
  allowedJson.price && allowedJson.price.amount === 1900 && allowedJson.price.currency === "usd",
  JSON.stringify(allowedJson.price));
check("video-pack download lists one artifact",
  Array.isArray(allowedJson.artifacts) && allowedJson.artifacts.length === 1,
  JSON.stringify(allowedJson.artifacts));

const ledger = await get("/ledger");
const ledgerHtml = await ledger.text();
check("GET /ledger = 200 human page", ledger.status === 200 && ledgerHtml.includes("<table"), "status=" + ledger.status);
assertPage("ledger page", ledgerHtml);

const ledgerJsonl = await get("/ledger.jsonl");
const ledgerText = await ledgerJsonl.text();
const ledgerLines = ledgerText.trim().split("\n").filter(Boolean);
check("GET /ledger.jsonl = 200", ledgerJsonl.status === 200, "status=" + ledgerJsonl.status);
check("ledger.jsonl has one line per event id", ledgerLines.length === 1, "lines=" + ledgerLines.length);
check("ledger.jsonl row keeps the slug", JSON.parse(ledgerLines[0]).slug === "video-pack-roman-concrete");

/* ------------------------------------------------ subscription entitlement */

const subscriptionBody = JSON.stringify({
  type: "subscription.active",
  data: {
    id: "153e6e7a-24f4-48ea-b91d-500eeb7bbf8d",
    status: "active",
    current_period_end: "2026-10-28T19:08:54.174055Z",
    product_id: "a000e958-094a-4662-b79f-aeace122904a",
    metadata: { slug: "studio-monthly-4" },
  },
});
const subscriptionWebhook = await postWebhook(subscriptionBody, sign(subscriptionBody, "msg_monthly"));
check("subscription webhook = 200", subscriptionWebhook.status === 200, "status=" + subscriptionWebhook.status);

const monthly = await get("/download/studio-monthly-4");
const monthlyJson = await monthly.json();
check("/download studio-monthly-4 = 200", monthly.status === 200, "status=" + monthly.status);
check("monthly download carries product_id (not null)",
  monthlyJson.product_id === "a000e958-094a-4662-b79f-aeace122904a", "product_id=" + monthlyJson.product_id);
check("monthly download carries the price",
  monthlyJson.price && monthlyJson.price.amount === 2900 && monthlyJson.price.currency === "usd",
  JSON.stringify(monthlyJson.price));
check("monthly download has no single manifest but an empty artifacts array",
  monthlyJson.manifest === undefined && Array.isArray(monthlyJson.artifacts) && monthlyJson.artifacts.length === 0,
  "manifest=" + JSON.stringify(monthlyJson.manifest) + " artifacts=" + JSON.stringify(monthlyJson.artifacts));
check("monthly download carries an explicit note",
  typeof monthlyJson.note === "string" && monthlyJson.note.length > 10, monthlyJson.note);
check("monthly download carries the subscription block",
  monthlyJson.subscription
    && monthlyJson.subscription.id === "153e6e7a-24f4-48ea-b91d-500eeb7bbf8d"
    && monthlyJson.subscription.status === "active"
    && monthlyJson.subscription.current_period_end === "2026-10-28T19:08:54.174055Z",
  JSON.stringify(monthlyJson.subscription));

const unentitled = await get("/download/caption-kit");
const unentitledJson = await unentitled.json();
check("unentitled slug stays 403", unentitled.status === 403, "status=" + unentitled.status);
check("unentitled body is exactly not_entitled",
  JSON.stringify(unentitledJson) === JSON.stringify({ error: "not_entitled" }), JSON.stringify(unentitledJson));

/* --------------------------------------------------------------- checkout */

const checkout = await worker.fetch(new Request(ORIGIN + "/api/checkout", {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({ slug: "caption-kit" }),
}), env);
const checkoutJson = await checkout.json();
check("POST /api/checkout = 200 JSON", checkout.status === 200, "status=" + checkout.status);
check("checkout returns a sandbox url", String(checkoutJson.url).includes("sandbox.polar.sh"), JSON.stringify(checkoutJson));

/* ---------------------------------------------------------------- report */

console.log("shortform-studio storefront smoke");
console.log(out.join("\n"));
console.log("");
console.log("assertions: " + (passed + failed) + "  pass: " + passed + "  fail: " + failed);
if (failed > 0) {
  process.exit(1);
}
