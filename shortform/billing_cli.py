"""CLI verbs for the provider-agnostic billing module.

Wired into ``python3 -m shortform`` as ``billing <verb>``:
``provision`` (idempotent products), ``checkout``, ``verify`` and ``webhook``
(the local handler the deployed site mirrors).
"""

from __future__ import annotations

import json
import os
import sys

from . import billing
from .billing import get_billing
from .billing import catalog as catalog_mod
from .billing import ledger as ledger_mod
from .billing import webhook as webhook_mod
from .billing.polar import SANDBOX_BASE

DEFAULT_STOREFRONT_URL = "https://shortform.studio/success?checkout_id={CHECKOUT_ID}"


def add_billing_subparser(sub) -> None:
    parser = sub.add_parser("billing", help="polar sandbox billing (provider-agnostic)")
    billing_sub = parser.add_subparsers(dest="billing_command", required=True)

    p_provision = billing_sub.add_parser(
        "provision", help="create the ShortForm Studio products/prices idempotently")
    p_provision.add_argument("--dry-run", action="store_true",
                             help="print the intended request bodies and call nothing")
    p_provision.set_defaults(func=cmd_provision)

    p_checkout = billing_sub.add_parser(
        "checkout", help="create a hosted checkout session for a product slug")
    p_checkout.add_argument("--product", required=True, help="catalog product slug")
    p_checkout.add_argument("--email", default=None, help="optional customer email")
    p_checkout.set_defaults(func=cmd_checkout)

    p_verify = billing_sub.add_parser(
        "verify", help="print the checkout/order state for a checkout id")
    p_verify.add_argument("--checkout", required=True, help="checkout id")
    p_verify.set_defaults(func=cmd_verify)

    p_webhook = billing_sub.add_parser(
        "webhook", help="verify and ledger a Standard Webhooks delivery from stdin")
    p_webhook.add_argument("--body-file", default=None,
                           help="read the raw body from this file instead of stdin")
    p_webhook.set_defaults(func=cmd_webhook)


def _dump(payload) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def cmd_provision(args) -> int:
    provider = get_billing()
    if args.dry_run:
        # No provider API call is made on the dry-run path.
        print("# billing provision --dry-run (no request sent)")
        print("# base: %s" % (os.environ.get("POLAR_API_BASE") or SANDBOX_BASE))
        for spec in catalog_mod.specs():
            body = billing.build_product_body(spec)
            print("POST /products/  # slug=%s" % spec["slug"])
            _dump(body)
        return 0
    results = provider.provision()
    for result in results:
        print("%-10s %-28s %s" % (result["action"], result["slug"], result["id"] or "-"))
    return 0


def cmd_checkout(args) -> int:
    provider = get_billing()
    product = provider.find_product_by_slug(args.product)
    if product is None:
        known = ", ".join(spec["slug"] for spec in catalog_mod.specs())
        print("ERROR: no polar sandbox product with slug %r (known: %s); "
              "run `billing provision` first" % (args.product, known), file=sys.stderr)
        return 3
    success_url = os.environ.get("SHORTFORM_STOREFRONT_URL") or DEFAULT_STOREFRONT_URL
    _, checkout = provider.create_checkout(
        [product.id], success_url=success_url, customer_email=args.email,
        metadata={"slug": args.product, "source": "shortform-studio"})
    print("checkout_id: %s" % checkout.id)
    print("checkout_url: %s" % checkout.url)
    print("status: %s" % checkout.status)
    return 0


def cmd_verify(args) -> int:
    provider = get_billing()
    checkout = provider.get_checkout(args.checkout)
    _dump({
        "checkout_id": checkout.id,
        "status": checkout.status,
        "paid": checkout.paid,
        "url": checkout.url,
        "customer_email": checkout.customer_email,
        "product_ids": checkout.product_ids,
        "subscription_id": checkout.subscription_id,
        "expires_at": checkout.expires_at,
    })
    return 0


def cmd_webhook(args) -> int:
    if args.body_file:
        raw = open(args.body_file, "rb").read()
    else:
        raw = sys.stdin.buffer.read()
    headers = {}
    mapping = {
        "webhook-id": ("WEBHOOK_ID", "HTTP_WEBHOOK_ID"),
        "webhook-timestamp": ("WEBHOOK_TIMESTAMP", "HTTP_WEBHOOK_TIMESTAMP"),
        "webhook-signature": ("WEBHOOK_SIGNATURE", "HTTP_WEBHOOK_SIGNATURE"),
    }
    for header, names in mapping.items():
        for name in names:
            if os.environ.get(name):
                headers[header] = os.environ[name]
                break
    if not headers and os.environ.get("POLAR_WEBHOOK_HEADERS"):
        headers = json.loads(os.environ["POLAR_WEBHOOK_HEADERS"])
    status, payload = webhook_mod.handle_delivery(raw, headers)
    payload = dict(payload)
    payload["status"] = status
    payload["ledger"] = str(ledger_mod.ledger_path())
    _dump(payload)
    return 0 if 200 <= status < 300 else 2
