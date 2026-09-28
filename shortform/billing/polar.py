"""The ``polar`` billing provider, pointed at the POLAR SANDBOX.

* base URL comes from ``POLAR_API_BASE`` and DEFAULTS to
  ``https://sandbox-api.polar.sh/v1``; the live host ``api.polar.sh`` is
  REFUSED unless ``allow_live=True`` is passed explicitly, so a sandbox run can
  never move real money;
* stdlib only (``urllib``), no SDK, no third-party dependency;
* the API key is resolved on EVERY call (never cached, never logged, never
  written to a file):
  ``$POLAR_API_KEY`` -> ``$SANDBOX_POLAR_API_KEY_SHORTFORM_STUDIO``
  (the harness credential-store name ``${cred:...}`` materialises to that
  same-named env var).

Documented shapes (Polar API 2026-04, from the P1 blueprint
``asset-pipeline/assetpipeline/billing/polar.py``, checked 2026-09-28):
  POST /products/            prices are created INLINE in ``prices:[...]``
  POST /checkouts/           ``products`` is a list of product UUID strings
  GET  /checkouts/{id}       status: open|confirmed|succeeded|failed|expired
  POST /webhooks/endpoints   returns the ``whsec_...`` signing secret
Collection paths NEED a trailing slash (a bare path answers 307).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from .base import BillingError, Checkout, Product, iso_now

SANDBOX_BASE = "https://sandbox-api.polar.sh/v1"
LIVE_HOST = "api.polar.sh"
DEFAULT_TIMEOUT = 30

# Credential resolution order. The second name is the harness credential-store
# name (``${cred:SANDBOX_POLAR_API_KEY_SHORTFORM_STUDIO}``); the store maps it
# onto an env var of the same name. It is a NAME, never a value.
API_KEY_ENV = ("POLAR_API_KEY", "SANDBOX_POLAR_API_KEY_SHORTFORM_STUDIO")
CREDENTIAL_STORE_NAME = "SANDBOX_POLAR_API_KEY_SHORTFORM_STUDIO"

#: The ShortForm Studio catalog. At least one one-time video pack and at least
#: one recurring subscription; ``metadata.slug`` is the idempotency key.
CATALOG = (
    {
        "slug": "shortform-video-pack",
        "name": "ShortForm Studio Video Pack",
        "description": "One-time pack of policy-checked 9:16 short videos.",
        "price_cents": 900,
        "currency": "usd",
        "recurring_interval": None,
    },
    {
        "slug": "shortform-creator-monthly",
        "name": "ShortForm Studio Creator",
        "description": "Recurring monthly subscription for ongoing short-form output.",
        "price_cents": 2900,
        "currency": "usd",
        "recurring_interval": "month",
    },
)


def resolve_api_key() -> str:
    """Resolve the sandbox OAT at CALL time; ``""`` when no credential exists.

    Names only: the value is never logged or returned to a caller for display.
    """
    for name in API_KEY_ENV:
        value = os.environ.get(name)
        if value:
            return value
    return ""


def resolve_base_url() -> str:
    return (os.environ.get("POLAR_API_BASE") or SANDBOX_BASE).rstrip("/")


def assert_sandbox(base_url: str, allow_live: bool = False) -> str:
    host = urllib.parse.urlparse(base_url).hostname or ""
    if host == LIVE_HOST and not allow_live:
        raise BillingError(
            "refusing the LIVE polar host (api.polar.sh): this studio is "
            "sandbox-only; set POLAR_API_BASE to the sandbox base or pass "
            "allow_live=True explicitly"
        )
    if not host.endswith("polar.sh"):
        raise BillingError("unexpected polar base host: %s" % host)
    return base_url


def build_product_body(spec: dict) -> dict:
    """The exact ``POST /products/`` body for one catalog entry."""
    body = {
        "name": spec["name"],
        "description": spec.get("description") or None,
        "visibility": spec.get("visibility", "public"),
        "metadata": {"slug": spec["slug"], "source": "shortform-studio"},
        "prices": [{
            "amount_type": "fixed",
            "price_amount": int(spec.get("price_cents", 0)),
            "price_currency": spec.get("currency", "usd"),
        }],
    }
    if spec.get("recurring_interval"):
        body["recurring_interval"] = spec["recurring_interval"]
    return body


class PolarBilling:
    name = "polar"
    env = "sandbox"

    def __init__(self, api_key: str = None, base_url: str = None,
                 timeout: int = DEFAULT_TIMEOUT, allow_live: bool = False):
        # ``api_key`` is kept only as an explicit test/DI override; when omitted
        # the key is re-resolved on every request so a rotated credential is
        # picked up without re-instantiating the provider.
        self._explicit_key = api_key
        self.base_url = assert_sandbox(
            (base_url or resolve_base_url()).rstrip("/"), allow_live=allow_live)
        self.timeout = timeout
        self.allow_live = allow_live

    @property
    def api_key(self) -> str:
        return self._explicit_key or resolve_api_key()

    # ------------------------------------------------------------------ http
    def _request(self, method: str, path: str, body=None, params=None):
        api_key = self.api_key  # resolved at call time
        if not api_key:
            raise BillingError(
                "missing polar sandbox credential: export $POLAR_API_KEY (or "
                "the harness store name ${cred:%s}); the key is never read "
                "from a file in this repo" % CREDENTIAL_STORE_NAME,
                capability=path,
            )
        url = self.base_url + path
        if params:
            url = "%s?%s" % (url, urllib.parse.urlencode(params))
        data = None
        headers = {
            "Authorization": "Bearer %s" % api_key,
            "Accept": "application/json",
            "User-Agent": "curl/8.5.0",
        }
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = response.read().decode("utf-8") or "null"
                return response.status, json.loads(payload)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:800]
            raise BillingError(
                "polar %s %s failed: HTTP %s" % (method, path, exc.code),
                status=exc.code, body=detail, capability=path,
            )
        except urllib.error.URLError as exc:
            raise BillingError(
                "polar %s %s transport error: %s" % (method, path, exc.reason),
                capability=path,
            )

    # ------------------------------------------------------------- discovery
    def list_products(self, limit: int = 100) -> list:
        _, payload = self._request("GET", "/products/", params={"limit": limit})
        return [Product.from_dict(entry) for entry in (payload.get("items") or [])]

    def find_product_by_slug(self, slug: str):
        for product in self.list_products():
            if product.slug == slug:
                return product
        return None

    # -------------------------------------------------------------- products
    def create_product(self, spec: dict):
        status, payload = self._request("POST", "/products/", body=build_product_body(spec))
        return status, Product.from_dict(payload)

    def provision(self, dry_run: bool = False) -> list:
        """Create the catalog idempotently; returns one result dict per entry.

        With ``dry_run=True`` the intended bodies are returned and NO request
        is sent.
        """
        results = []
        existing = {}
        if not dry_run:
            existing = {p.slug: p for p in self.list_products()}
        for spec in CATALOG:
            body = build_product_body(spec)
            if dry_run:
                results.append({"slug": spec["slug"], "action": "dry-run",
                                "body": body, "id": None})
                continue
            if spec["slug"] in existing:
                product = existing[spec["slug"]]
                results.append({"slug": spec["slug"], "action": "skipped",
                                "body": body, "id": product.id})
                continue
            _, product = self.create_product(spec)
            results.append({"slug": spec["slug"], "action": "created",
                            "body": body, "id": product.id})
        return results

    # -------------------------------------------------------------- checkout
    def create_checkout(self, product_ids, success_url, customer_email=None,
                        metadata=None, return_url=None):
        if isinstance(product_ids, str):
            product_ids = [product_ids]
        body = {
            "products": [str(pid) for pid in product_ids],
            "success_url": success_url,
            "metadata": metadata or {},
        }
        if customer_email:
            body["customer_email"] = customer_email
        if return_url:
            body["return_url"] = return_url
        status, payload = self._request("POST", "/checkouts/", body=body)
        return status, Checkout.from_dict(payload)

    def get_checkout(self, checkout_id: str) -> Checkout:
        _, payload = self._request("GET", "/checkouts/%s" % checkout_id)
        return Checkout.from_dict(payload)

    # ----------------------------------------------------------------- misc
    def describe(self) -> dict:
        return {
            "provider": self.name,
            "env": self.env,
            "base_url": self.base_url,
            "checked_at": iso_now(),
            "api_key_present": bool(self.api_key),
            "api_key_env": [n for n in API_KEY_ENV if os.environ.get(n)] or None,
        }
