/*
 * shortform-studio storefront (Polar SANDBOX MVP)
 *
 * Cloudflare Worker, plain ES module, no build step.
 *
 * Routes
 *   GET  /                 storefront catalog
 *   GET  /product/<slug>   product page + buy form (real artifact listed)
 *   POST /api/checkout     server-side checkout session (never leaks the key)
 *   GET  /success          payment result + entitlement
 *   GET  /cancel           cancelled checkout
 *   POST /webhooks/polar   Standard-Webhooks HMAC-SHA256 receiver
 *   GET  /ledger           durable verified-event rows (human page)
 *   GET  /ledger.jsonl     the same rows as JSONL, one per event id
 *   GET  /catalog.json     canonical catalog
 *   GET  /download/<slug>  manifest JSON, gated on a paid entitlement
 *   GET  /healthz          liveness
 *
 * Bindings
 *   POLAR_API_KEY         secret, sandbox organization access token (never in the repo)
 *   POLAR_WEBHOOK_SECRET  secret, the whsec_ signing secret of the endpoint
 *   POLAR_API_BASE        plain var, defaults to the SANDBOX base
 *   LEDGER                KV namespace for durable webhook rows
 *
 * The sandbox base URL is pinned: a live host is refused, so this worker can
 * never take real money.
 */

const SANDBOX_BASE = "https://sandbox-api.polar.sh/v1";
const CATALOG_SOURCE = "shortform-studio-mvp-catalog";
const NOTICE = "SANDBOX / DEMO - no real payment";
const UA = "curl/8.5.0";
const SECURITY_HEADERS = {
  "Referrer-Policy": "no-referrer",
  "X-Frame-Options": "DENY",
  "X-Content-Type-Options": "nosniff",
};

/* The real rendered artifact delivered by the one-time video pack. */
const ROMAN_CONCRETE_ARTIFACT = {
  path: "out/roman-concrete/video.mp4",
  bytes: 2404763,
  duration_s: 37.5,
  resolution: "1080x1920",
  qa: "17/17",
  sha256: "9ce0e04ef5fe79fb27ec10fd2eb16efedc024b9dbe48d1c62827b45f8dfff206",
};

/* Canonical catalog. Slugs and prices MUST match storefront/catalog.json and
 * shortform/billing/polar.py CATALOG (PRODUCTS). */
const CATALOG = [
  {
    slug: "video-pack-roman-concrete",
    name: "ShortForm Studio Video Pack: Roman Concrete",
    description:
      "The rendered 9:16 short How Roman Concrete Survived 2000 Years: H.264 1080x1920 with AAC audio, burnt captions, plus SRT, description and metadata. Deterministic render, QA 17/17 PASS.",
    amount: 1900,
    currency: "usd",
    recurring_interval: null,
    product_id: "805fafde-0825-4732-8817-21d0bd412502",
    artifact: ROMAN_CONCRETE_ARTIFACT,
  },
  {
    slug: "shorts-bundle-3",
    name: "ShortForm Studio 3-Pack",
    description:
      "Three policy-checked 9:16 shorts rendered and QA-gated, each with captions, title, description and metadata.",
    amount: 2900,
    currency: "usd",
    recurring_interval: null,
    product_id: "d7c598b6-bb7c-4770-8db3-a894f488a1dc",
  },
  {
    slug: "caption-kit",
    name: "ShortForm Caption + Metadata Kit",
    description:
      "The caption, title, description and metadata kit for one short, ready to paste into the channel.",
    amount: 900,
    currency: "usd",
    recurring_interval: null,
    product_id: "a1db888e-5b82-435e-82c1-3e3a80a6acb2",
  },
  {
    slug: "studio-monthly-4",
    name: "ShortForm Studio Monthly - 4 videos/month",
    description:
      "Four policy-checked shorts per month with captions, metadata and the QA report for each render.",
    amount: 2900,
    currency: "usd",
    recurring_interval: "month",
    product_id: "a000e958-094a-4662-b79f-aeace122904a",
  },
];

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    try {
      if (url.pathname === "/healthz") {
        return json({
          ok: true,
          service: "shortform-studio-storefront",
          provider: "polar",
          provider_env: base(env).includes("sandbox") ? "sandbox" : "live",
          api_base: base(env),
          ledger_binding: Boolean(env.LEDGER),
        });
      }
      if (url.pathname === "/webhooks/polar" && request.method === "POST") {
        return await handleWebhook(request, env);
      }
      if (url.pathname === "/ledger") return await handleLedger(env);
      if (url.pathname === "/ledger.jsonl") return await handleLedgerJsonl(env);
      if (url.pathname === "/api/checkout" && request.method === "POST") {
        return await handleCheckout(request, env, url);
      }
      if (url.pathname === "/success") return await handleSuccess(env, url);
      if (url.pathname === "/cancel") {
        return htmlPage(
          "Checkout cancelled",
          `<div class="card"><h1>Checkout cancelled</h1>
           <p class="muted">No payment was taken. Nothing was charged.</p>
           <p><a class="btn" href="/">Back to the catalog</a></p></div>`,
          200
        );
      }
      if (url.pathname === "/" || url.pathname === "") return await handleCatalog(env);
      if (url.pathname === "/catalog.json") return await handleCatalogJson(env);
      if (url.pathname.startsWith("/a/")) {
        return await handleProduct(env, decodeURIComponent(url.pathname.slice(3)), url);
      }
      if (url.pathname.startsWith("/product/")) {
        return await handleProduct(env, decodeURIComponent(url.pathname.slice(9)), url);
      }
      if (url.pathname.startsWith("/download/")) {
        return await handleDownload(env, decodeURIComponent(url.pathname.slice(10)));
      }
      return htmlPage("Not found", `<div class="card"><h1>404</h1><p class="muted">No such page.</p><p><a class="btn" href="/">Catalog</a></p></div>`, 404);
    } catch (error) {
      return htmlPage(
        "Error",
        `<div class="card"><h1>Sandbox error</h1><pre>${esc(String(error && error.message ? error.message : error))}</pre></div>`,
        500
      );
    }
  },
};

/* --------------------------------------------------------------- provider */

function base(env) {
  const value = (env && env.POLAR_API_BASE) || SANDBOX_BASE;
  const trimmed = String(value).replace(/\/+$/, "");
  if (trimmed.includes("api.polar.sh") && !trimmed.includes("sandbox-api")) {
    throw new Error("refusing the live polar host: this storefront is sandbox-only");
  }
  return trimmed;
}

async function polar(env, method, path, body) {
  const key = env && env.POLAR_API_KEY;
  if (!key) throw new Error("POLAR_API_KEY secret is not set on this worker");
  const init = {
    method,
    headers: {
      Authorization: "Bearer " + key,
      Accept: "application/json",
      "User-Agent": UA,
    },
  };
  if (body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  const response = await fetch(base(env) + path, init);
  const text = await response.text();
  if (!response.ok) {
    throw new Error("polar " + method + " " + path + " failed: HTTP " + response.status + " " + text.slice(0, 400));
  }
  return text ? JSON.parse(text) : null;
}

async function catalogProducts(env) {
  const payload = await polar(env, "GET", "/products/?limit=100");
  return (payload.items || []).filter((item) => item.metadata && item.metadata.slug);
}

function firstPrice(product) {
  return (product.prices || [])[0] || null;
}

function money(amount, currency) {
  const code = String(currency || "usd").toUpperCase();
  return code + " " + (Number(amount || 0) / 100).toFixed(2);
}

function recurringLabel(interval) {
  if (!interval) return "one time";
  return "per " + interval;
}

/* The canonical catalog, enriched with live product ids when the sandbox API
 * answers. Rendering never depends on the API being reachable. */
async function loadCatalog(env) {
  let remote = [];
  let error = null;
  try {
    remote = await catalogProducts(env);
  } catch (err) {
    error = String(err && err.message ? err.message : err);
  }
  const bySlug = new Map(remote.map((product) => [product.metadata.slug, product]));
  const items = CATALOG.map((entry) => {
    const product = bySlug.get(entry.slug) || null;
    const price = product ? firstPrice(product) : null;
    return Object.assign({}, entry, {
      product_id: entry.product_id || (product ? product.id : null),
      price_id: price ? price.id : null,
      live: Boolean(product),
    });
  });
  return { items, error };
}

/* ---------------------------------------------------------------- handlers */

async function handleCatalog(env) {
  const { items, error } = await loadCatalog(env);
  const cards = items
    .map((item) => {
      const badge = item.recurring_interval ? "subscription" : "one time";
      return `<a class="card item" href="/product/${esc(item.slug)}">
        <div class="row"><h2>${esc(item.name)}</h2><span class="badge">${esc(badge)}</span></div>
        <p class="muted">${esc(item.description)}</p>
        <p class="price">${esc(money(item.amount, item.currency))} <span class="muted">${esc(recurringLabel(item.recurring_interval))}</span></p>
      </a>`;
    })
    .join("");
  const body = `
    <section class="hero">
      <h1>ShortForm Studio short-form packs</h1>
      <p class="muted">Policy-checked 9:16 shorts and kits from shortform-studio, bought through the Polar sandbox with a test card.</p>
      <p class="notice">${esc(NOTICE)}</p>
    </section>
    ${error ? `<div class="card error">catalog sync note: <pre>${esc(error)}</pre></div>` : ""}
    <section class="grid">${cards || '<div class="card muted">no catalog items yet</div>'}</section>`;
  return htmlPage("ShortForm Studio storefront", body, 200);
}

async function handleCatalogJson(env) {
  const { items } = await loadCatalog(env);
  const clean = items.map((item) => ({
    slug: item.slug,
    name: item.name,
    description: item.description,
    amount: item.amount,
    currency: item.currency,
    recurring_interval: item.recurring_interval,
    product_id: item.product_id,
    ...(item.artifact ? { artifact: item.artifact } : {}),
  }));
  return json({
    catalog_version: 1,
    pipeline: "shortform-studio",
    storefront: "shortform-studio-polar-sandbox",
    provider: "polar",
    provider_env: "sandbox",
    provider_api_base: base(env),
    notice: NOTICE,
    currency: "usd",
    metadata_source: CATALOG_SOURCE,
    count: clean.length,
    items: clean,
  });
}

async function handleProduct(env, slug, url) {
  const { items } = await loadCatalog(env);
  const item = items.find((entry) => entry.slug === slug);
  if (!item) {
    return htmlPage("Not found", `<div class="card"><h1>Unknown product</h1><p class="muted">${esc(slug)}</p><p><a class="btn" href="/">Catalog</a></p></div>`, 404);
  }
  const artifact = item.artifact
    ? `<h2>Delivers the real rendered short</h2>
       <table>
         <tbody>
           <tr><th>path</th><td><code>${esc(item.artifact.path)}</code></td></tr>
           <tr><th>bytes</th><td>${esc(item.artifact.bytes)}</td></tr>
           <tr><th>duration</th><td>${esc(item.artifact.duration_s)} s</td></tr>
           <tr><th>resolution</th><td>${esc(item.artifact.resolution)}</td></tr>
           <tr><th>QA</th><td>${esc(item.artifact.qa)} PASS</td></tr>
           <tr><th>sha256</th><td><code>${esc(item.artifact.sha256)}</code></td></tr>
         </tbody>
       </table>`
    : "";
  const body = `
    <div class="card">
      <div class="row"><h1>${esc(item.name)}</h1><span class="badge">${item.recurring_interval ? "subscription" : "one time"}</span></div>
      <p class="muted">${esc(item.description)}</p>
      <p class="price">${esc(money(item.amount, item.currency))} <span class="muted">${esc(recurringLabel(item.recurring_interval))}</span></p>
      ${artifact}
      <form method="POST" action="/api/checkout">
        <input type="hidden" name="slug" value="${esc(item.slug)}" />
        <label>email (optional, for the receipt preview)
          <input type="email" name="email" placeholder="sandbox-buyer@example.com" />
        </label>
        <button class="btn" type="submit">Buy in the Polar sandbox</button>
      </form>
      <p class="notice">${esc(NOTICE)} - test card 4242 4242 4242 4242, any future expiry, any CVC.</p>
      <p><a class="btn ghost" href="/download/${esc(item.slug)}">Manifest JSON</a></p>
      <p class="muted small">product_id ${esc(item.product_id || "pending provisioning")}</p>
    </div>`;
  return htmlPage(item.name, body, 200);
}

async function handleCheckout(request, env, url) {
  const contentType = request.headers.get("content-type") || "";
  let slug = "";
  let email = "";
  const wantsJson = contentType.includes("application/json");
  if (wantsJson) {
    const payload = await request.json();
    slug = String(payload.slug || "");
    email = String(payload.email || "");
  } else {
    const form = await request.formData();
    slug = String(form.get("slug") || "");
    email = String(form.get("email") || "");
  }
  const { items } = await loadCatalog(env);
  const item = items.find((entry) => entry.slug === slug);
  if (!item) {
    return wantsJson ? json({ error: "product_not_found", slug }, 404)
      : htmlPage("Unknown product", `<div class="card"><h1>Unknown product</h1><p class="muted">${esc(slug)}</p></div>`, 404);
  }
  let productId = item.product_id;
  if (!productId) {
    try {
      const products = await catalogProducts(env);
      const remote = products.find((product) => product.metadata.slug === slug);
      productId = remote ? remote.id : null;
    } catch (err) {
      productId = null;
    }
  }
  if (!productId) {
    return wantsJson ? json({ error: "product_not_provisioned", slug }, 409)
      : htmlPage("Not provisioned", `<div class="card"><h1>Product not provisioned</h1><p class="muted">Run the provisioning script first.</p></div>`, 409);
  }
  const body = {
    products: [productId],
    success_url: url.origin + "/success?checkout_id={CHECKOUT_ID}",
    return_url: url.origin + "/cancel",
    metadata: { slug, source: CATALOG_SOURCE },
  };
  if (email) body.customer_email = email;
  const checkout = await polar(env, "POST", "/checkouts/", body);
  if (wantsJson) {
    return json({
      checkout_id: checkout.id,
      url: checkout.url,
      status: checkout.status,
      product_id: productId,
      provider: "polar",
      provider_env: "sandbox",
    });
  }
  return Response.redirect(checkout.url, 302);
}

async function handleSuccess(env, url) {
  const checkoutId = url.searchParams.get("checkout_id") || "";
  if (!checkoutId) {
    return htmlPage("Missing checkout", `<div class="card"><h1>No checkout id</h1><p class="muted">Add ?checkout_id=...</p></div>`, 400);
  }
  const checkout = await polar(env, "GET", "/checkouts/" + encodeURIComponent(checkoutId));
  const status = String(checkout.status || "");
  if (status !== "succeeded") {
    const pending = status === "open" || status === "confirmed";
    return htmlPage(
      pending ? "Payment pending" : "Payment not completed",
      `<div class="card"><h1>${pending ? "Payment pending" : "Payment not completed"}</h1>
       <p class="muted">checkout ${esc(checkoutId)} status: <strong>${esc(status || "unknown")}</strong></p>
       ${pending ? '<p class="muted">The sandbox has not settled this checkout yet. Reload this page in a moment.</p>' : ""}
       <p><a class="btn" href="/success?checkout_id=${esc(checkoutId)}">Refresh</a> <a class="btn ghost" href="/">Catalog</a></p>
       <p class="notice">${esc(NOTICE)}</p></div>`,
      200
    );
  }
  const slug = (checkout.metadata && checkout.metadata.slug) || "";
  let entitlement = "";
  try {
    const orders = ((await polar(env, "GET", "/orders/?limit=100")).items || [])
      .filter((order) => order.checkout_id === checkoutId);
    const subs = ((await polar(env, "GET", "/subscriptions/?limit=100")).items || [])
      .filter((subscription) => subscription.checkout_id === checkoutId);
    const rows = [];
    for (const order of orders) {
      rows.push(`<li>order <code>${esc(order.id)}</code> status <strong>${esc(order.status)}</strong> ${order.paid ? "(paid)" : ""}</li>`);
    }
    for (const subscription of subs) {
      rows.push(`<li>subscription <code>${esc(subscription.id)}</code> status <strong>${esc(subscription.status)}</strong> until ${esc(subscription.current_period_end || "-")}</li>`);
    }
    entitlement = rows.length
      ? `<h2>Entitlement unlocked</h2><ul>${rows.join("")}</ul>`
      : `<h2>Entitlement pending</h2><p class="muted">The sandbox has not published the order yet. Reload in a moment.</p>`;
  } catch (err) {
    entitlement = `<h2>Entitlement check failed</h2><pre>${esc(String(err.message || err))}</pre>`;
  }
  const body = `
    <div class="card">
      <h1>Payment succeeded</h1>
      <p class="muted">checkout <code>${esc(checkoutId)}</code> status <strong>${esc(status)}</strong></p>
      ${entitlement}
      ${slug ? `<p><a class="btn" href="/download/${esc(slug)}">Open the download manifest</a></p>` : ""}
      <p class="muted small">buyer: ${esc(checkout.customer_email || "-")}</p>
      <p><a class="btn" href="/">Back to the catalog</a></p>
      <p class="notice">${esc(NOTICE)}</p>
    </div>`;
  return htmlPage("Payment succeeded", body, 200);
}

/* --------------------------------------------------------------- webhooks */

async function handleWebhook(request, env) {
  const raw = await request.text();
  const secret = env.POLAR_WEBHOOK_SECRET;
  if (!secret) return json({ error: "webhook_secret_not_configured" }, 500);
  const headers = {
    "webhook-id": request.headers.get("webhook-id"),
    "webhook-timestamp": request.headers.get("webhook-timestamp"),
    "webhook-signature": request.headers.get("webhook-signature"),
  };
  const valid = await verifySignature(raw, headers, secret);
  if (!valid) return json({ error: "invalid_signature" }, 401);
  let event;
  try {
    event = JSON.parse(raw);
  } catch (err) {
    return json({ error: "invalid_json" }, 400);
  }
  const data = event.data || {};
  const row = {
    id: headers["webhook-id"] || data.id || "",
    type: event.type || "",
    object_id: data.id || "",
    checkout_id: data.checkout_id || "",
    subscription_id: data.subscription_id || (String(event.type || "").startsWith("subscription.") ? data.id || "" : ""),
    customer_email: (data.customer && data.customer.email) || data.customer_email || "",
    status: data.status || "",
    product_id: data.product_id || (data.product && data.product.id) || "",
    current_period_end: data.current_period_end || "",
    amount_cents: data.total_amount || data.amount || 0,
    slug: (data.metadata && data.metadata.slug) || "",
    received_at: new Date().toISOString(),
    payload: data,
  };
  let persisted = false;
  let duplicate = false;
  if (env.LEDGER) {
    const key = "event:" + (row.id || row.object_id || Date.now());
    duplicate = Boolean(await env.LEDGER.get(key));
    if (!duplicate) {
      await env.LEDGER.put(key, JSON.stringify(row));
    }
    persisted = true;
  }
  return json({ received: true, id: row.id, type: row.type, persisted, duplicate });
}

async function ledgerRows(env) {
  if (!env.LEDGER) return [];
  const list = await env.LEDGER.list({ prefix: "event:", limit: 1000 });
  const rows = [];
  for (const key of list.keys) {
    const value = await env.LEDGER.get(key.name);
    if (value) rows.push(JSON.parse(value));
  }
  rows.sort((a, b) => String(a.received_at).localeCompare(String(b.received_at)));
  return rows;
}

async function handleLedger(env) {
  const rows = await ledgerRows(env);
  const body = `
    <div class="card">
      <h1>Verified webhook ledger</h1>
      <p class="muted">One durable row per verified Polar event id. Bad signatures are rejected and never written.</p>
      <p class="muted small">source: ${env.LEDGER ? "kv" : "no ledger binding"} - count ${rows.length}</p>
      <div class="tablewrap">
        <table>
          <thead><tr><th>received_at</th><th>type</th><th>slug</th><th>status</th><th>event id</th></tr></thead>
          <tbody>
            ${rows.map((row) => `<tr><td>${esc(row.received_at)}</td><td>${esc(row.type)}</td><td>${esc(row.slug)}</td><td>${esc(row.status)}</td><td><code>${esc(row.id)}</code></td></tr>`).join("") || '<tr><td colspan="5" class="muted">no rows yet</td></tr>'}
          </tbody>
        </table>
      </div>
      <p><a class="btn ghost" href="/ledger.jsonl">ledger.jsonl</a> <a class="btn ghost" href="/">Catalog</a></p>
    </div>`;
  return htmlPage("Ledger", body, 200);
}

async function handleLedgerJsonl(env) {
  const rows = await ledgerRows(env);
  const seen = new Set();
  const lines = [];
  for (const row of rows) {
    const id = row.id || row.object_id || "";
    if (seen.has(id)) continue;
    seen.add(id);
    lines.push(JSON.stringify(row));
  }
  return new Response(lines.join("\n") + (lines.length ? "\n" : ""), {
    status: 200,
    headers: Object.assign({
      "Content-Type": "application/x-ndjson; charset=utf-8",
      "Cache-Control": "no-store",
    }, SECURITY_HEADERS),
  });
}

/* ------------------------------------------------------------ entitlement */

/* The product id carried by a ledger row, from the top-level field (new rows)
 * or the raw webhook payload (rows written before the field existed). */
function rowProductId(row) {
  if (!row) return "";
  const payload = row.payload || {};
  const product = payload.product || {};
  return String(row.product_id || payload.product_id || product.id || "");
}

/* A row entitles a download when it is paid/active AND matches the requested
 * slug or the catalog product id of that slug. */
function rowEntitles(row, slug, productId) {
  if (!row) return false;
  const type = String(row.type || "");
  const status = String(row.status || "").toLowerCase();
  const paid = type === "order.paid" || status === "paid" || status === "succeeded" || status === "active";
  if (!paid) return false;
  const rowSlug = String(row.slug || "");
  const rowProduct = rowProductId(row);
  return Boolean((slug && rowSlug === slug) || (productId && rowProduct === productId));
}

/* Rank: a real subscription lifecycle event beats an order that only points at
 * a subscription, which beats a plain order. The download picks the top rank. */
function subscriptionRank(row) {
  if (!row) return 0;
  if (String(row.type || "").startsWith("subscription.")) return 2;
  if (row.subscription_id || (row.payload && row.payload.subscription_id)) return 1;
  return 0;
}

function isSubscriptionRow(row) {
  return subscriptionRank(row) > 0;
}

/* The `subscription` block, only when the entitling row is subscription-backed. */
function subscriptionForRow(row) {
  if (!isSubscriptionRow(row)) return null;
  const payload = (row && row.payload) || {};
  let id = row.subscription_id || payload.subscription_id || "";
  if (!id && String(row.type || "").startsWith("subscription.")) id = row.object_id || "";
  if (!id) return null;
  return {
    id: String(id),
    status: String(payload.status || row.status || ""),
    current_period_end: payload.current_period_end || row.current_period_end || null,
  };
}

/* Prefer the newest subscription-backed entitlement, else the newest paid row. */
async function findEntitlement(env, slug, productId) {
  const matched = (await ledgerRows(env)).filter((row) => rowEntitles(row, slug, productId));
  if (!matched.length) return null;
  matched.sort((a, b) => {
    const rankA = subscriptionRank(a);
    const rankB = subscriptionRank(b);
    if (rankA !== rankB) return rankA - rankB;
    return String(a.received_at).localeCompare(String(b.received_at));
  });
  return matched[matched.length - 1];
}

async function handleDownload(env, slug) {
  const requested = CATALOG.find((item) => item.slug === slug);
  if (!requested) {
    return json({ error: "unknown_product", slug }, 404);
  }
  const entitlement = await findEntitlement(env, slug, requested.product_id);
  if (!entitlement) {
    return json({ error: "not_entitled" }, 403);
  }
  const entitlingProductId = rowProductId(entitlement);
  /* Resolve by the product id carried by the entitlement row, then by slug. */
  const byProduct = entitlingProductId
    ? CATALOG.find((item) => item.product_id === entitlingProductId)
    : null;
  const entry = byProduct || requested;
  const productId = entry.product_id || entitlingProductId || requested.product_id || null;
  const artifact = entry.artifact || null;
  const body = {
    slug: entry.slug,
    entitled: true,
    name: entry.name,
    product_id: productId,
    price: {
      amount: entry.amount,
      currency: entry.currency,
      recurring_interval: entry.recurring_interval,
      display: money(entry.amount, entry.currency),
    },
    amount: entry.amount,
    currency: entry.currency,
    recurring_interval: entry.recurring_interval,
    artifacts: artifact ? [artifact] : [],
  };
  if (artifact) {
    body.manifest = artifact;
  } else {
    body.note = "No single downloadable artifact: " + entry.name
      + " is a recurring subscription that delivers per-render artifacts over time.";
  }
  const subscription = subscriptionForRow(entitlement);
  if (subscription) body.subscription = subscription;
  return json(body);
}

/* --------------------------------------------------------------- signature */

function b64ToBytes(value) {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function bytesToB64(bytes) {
  let binary = "";
  const view = new Uint8Array(bytes);
  for (let i = 0; i < view.length; i += 1) binary += String.fromCharCode(view[i]);
  return btoa(binary);
}

/* Constant-time string compare: equal length, then XOR-accumulate. */
function timingSafeEqual(a, b) {
  const left = String(a);
  const right = String(b);
  if (left.length !== right.length) return false;
  let diff = 0;
  for (let i = 0; i < left.length; i += 1) {
    diff |= left.charCodeAt(i) ^ right.charCodeAt(i);
  }
  return diff === 0;
}

async function hmacCandidate(keyBytes, baseString) {
  const key = await crypto.subtle.importKey("raw", keyBytes, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const digest = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(baseString));
  return bytesToB64(digest);
}

export async function verifySignature(raw, headers, secret, toleranceSeconds = 300) {
  const id = headers["webhook-id"];
  const timestamp = headers["webhook-timestamp"];
  const signatureHeader = headers["webhook-signature"];
  if (!id || !timestamp || !signatureHeader) return false;
  const age = Math.abs(Math.floor(Date.now() / 1000) - Number(timestamp));
  if (!Number.isFinite(age) || age > toleranceSeconds) return false;
  const baseString = id + "." + timestamp + "." + raw;
  const provided = String(signatureHeader)
    .split(" ")
    .map((part) => (part.includes(",") ? part.split(",")[1] : part))
    .filter(Boolean);
  const candidates = [];
  if (String(secret).startsWith("whsec_")) {
    try {
      candidates.push(b64ToBytes(String(secret).slice("whsec_".length)));
    } catch (err) {
      /* not base64: fall through to the legacy key */
    }
  }
  candidates.push(new TextEncoder().encode(String(secret)));
  for (const keyBytes of candidates) {
    const expected = await hmacCandidate(keyBytes, baseString);
    for (const candidate of provided) {
      if (timingSafeEqual(expected, candidate)) return true;
    }
  }
  return false;
}

/* ------------------------------------------------------------- rendering */

const PALETTE = `
  :root {
    --bg-primary: #0a0f1e;
    --bg-secondary: #111827;
    --bg-sidebar: #0d1321;
    --bg-card: rgba(255, 255, 255, 0.03);
    --bg-card-hover: rgba(255, 255, 255, 0.06);
    --text-primary: #f1f5f9;
    --text-secondary: #94a3b8;
    --text-muted: #64748b;
    --text-accent: #a78bfa;
    --accent: #8b5cf6;
    --accent-purple: #8b5cf6;
    --accent-cyan: #06b6d4;
    --accent-amber: #f59e0b;
    --accent-rose: #f43f5e;
    --accent-emerald: #10b981;
    --accent-blue: #3b82f6;
    --border-primary: rgba(255, 255, 255, 0.06);
    --border-accent: rgba(139, 92, 246, 0.3);
  }`;

const CSS = `
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; max-width: 100%; overflow-x: hidden; }
  body {
    background:
      radial-gradient(1100px 520px at 12% -12%, rgba(139, 92, 246, 0.22), transparent 60%),
      radial-gradient(900px 420px at 100% 0%, rgba(6, 182, 212, 0.16), transparent 55%),
      var(--bg-primary);
    color: var(--text-primary);
    font: 16px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    min-height: 100vh;
  }
  .wrap { width: 100%; max-width: 1080px; margin: 0 auto; padding: 20px 16px 64px; }
  header.top { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 8px 0 20px; flex-wrap: wrap; }
  header.top .brand { font-weight: 700; letter-spacing: 0.02em; }
  header.top .brand span { color: var(--text-accent); }
  header.top .pill { font-size: 12px; color: var(--accent-amber); border: 1px solid rgba(245, 158, 11, 0.35); border-radius: 999px; padding: 3px 10px; background: rgba(245, 158, 11, 0.1); }
  h1 { font-size: clamp(1.5rem, 4.2vw, 2.1rem); margin: 0 0 8px; }
  h2 { font-size: 1.05rem; margin: 0; }
  p { margin: 0 0 10px; }
  a { color: var(--text-accent); text-decoration: none; }
  img, video, svg, canvas { max-width: 100%; height: auto; }
  table { width: 100%; max-width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { text-align: left; padding: 7px 9px; border-bottom: 1px solid var(--border-primary); vertical-align: top; overflow-wrap: anywhere; }
  th { color: var(--text-secondary); font-weight: 600; }
  .tablewrap { width: 100%; max-width: 100%; overflow-x: auto; }
  .muted { color: var(--text-secondary); }
  .small { font-size: 12px; color: var(--text-muted); }
  .hero { padding: 8px 0 20px; max-width: 62ch; }
  .grid { display: grid; gap: 14px; grid-template-columns: repeat(auto-fill, minmax(min(280px, 100%), 1fr)); }
  .card {
    display: block; background: var(--bg-card); border: 1px solid var(--border-primary);
    border-radius: 14px; padding: 18px; margin-bottom: 14px;
    backdrop-filter: blur(6px); transition: border-color 0.15s ease, background 0.15s ease, transform 0.15s ease;
  }
  a.card:hover, .card:hover { background: var(--bg-card-hover); border-color: var(--border-accent); transform: translateY(-1px); }
  .card.error { border-color: rgba(244, 63, 94, 0.4); }
  .row { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
  .badge {
    font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em;
    color: var(--text-accent); border: 1px solid var(--border-accent);
    background: rgba(139, 92, 246, 0.15); border-radius: 999px; padding: 3px 9px;
  }
  .price { color: var(--accent-emerald); font-weight: 600; }
  .notice {
    font-size: 12.5px; color: var(--accent-amber); border: 1px dashed rgba(245, 158, 11, 0.4);
    background: rgba(245, 158, 11, 0.08); border-radius: 10px; padding: 8px 11px; display: inline-block;
    max-width: 100%; overflow-wrap: anywhere;
  }
  form { display: flex; flex-direction: column; gap: 10px; margin: 14px 0 10px; max-width: 420px; }
  label { font-size: 13px; color: var(--text-secondary); display: flex; flex-direction: column; gap: 6px; }
  input {
    background: var(--bg-secondary); border: 1px solid var(--border-primary); color: var(--text-primary);
    border-radius: 10px; padding: 10px 12px; font-size: 15px; width: 100%; max-width: 100%;
  }
  input:focus { outline: none; border-color: var(--border-accent); }
  .btn {
    display: inline-block; background: linear-gradient(135deg, var(--accent), var(--accent-cyan));
    color: #0d1321; font-weight: 700; border: 0; border-radius: 10px; padding: 11px 18px;
    cursor: pointer; font-size: 15px;
  }
  .btn.ghost { background: transparent; color: var(--text-accent); border: 1px solid var(--border-accent); }
  code { background: var(--bg-secondary); border-radius: 6px; padding: 1px 6px; font-size: 13px; color: var(--text-primary); overflow-wrap: anywhere; }
  pre { background: var(--bg-secondary); border: 1px solid var(--border-primary); border-radius: 10px; padding: 12px; overflow-x: auto; font-size: 12.5px; max-width: 100%; }
  ul { padding-left: 20px; }
  footer { margin-top: 28px; color: var(--text-muted); font-size: 12px; border-top: 1px solid var(--border-primary); padding-top: 14px; }
  @media (max-width: 640px) {
    .wrap { padding: 14px 12px 48px; }
    .grid { grid-template-columns: 1fr; }
    .card { padding: 15px; }
  }`;

function layout(title, body) {
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>${esc(title)} - ShortForm Studio storefront (sandbox)</title>
<style>${PALETTE}${CSS}</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <div class="brand">Short<span>Form</span> Studio</div>
    <div class="pill">${esc(NOTICE)}</div>
  </header>
  <main>${body}</main>
  <footer>
    Polar sandbox storefront for ShortForm Studio. Sandbox host only, test card only, no real charge, no payout, no end-user release.
  </footer>
</div>
</body>
</html>`;
}

function htmlPage(title, body, status) {
  return new Response(layout(title, body), {
    status: status || 200,
    headers: Object.assign({
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "no-store",
    }, SECURITY_HEADERS),
  });
}

function json(payload, status) {
  return new Response(JSON.stringify(payload, null, 2), {
    status: status || 200,
    headers: Object.assign({
      "Content-Type": "application/json",
      "Cache-Control": "no-store",
    }, SECURITY_HEADERS),
  });
}

function esc(value) {
  return String(value === undefined || value === null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
