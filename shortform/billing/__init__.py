"""Provider-agnostic billing module for ShortForm Studio.

ONE billing interface, the provider selected by environment
(``SHORTFORM_BILLING_PROVIDER``, default ``polar``). The ``polar`` provider is
the POLAR SANDBOX provider: it points at ``https://sandbox-api.polar.sh/v1`` by
default and refuses the live host, so a sandbox run can never move real money.

Credentials come from the environment/store only at call time
(``$POLAR_API_KEY`` -> ``$SANDBOX_POLAR_API_KEY_SHORTFORM_STUDIO`` /
``${cred:SANDBOX_POLAR_API_KEY_SHORTFORM_STUDIO}``); no key is stored here.
"""

from __future__ import annotations

import os

from .base import (
    BillingError,
    Checkout,
    Order,
    Price,
    Product,
    Subscription,
    WebhookEvent,
    iso_now,
)
from .polar import CATALOG, PolarBilling, build_product_body, resolve_api_key

DEFAULT_PROVIDER = "polar"
ENV_PROVIDER = "SHORTFORM_BILLING_PROVIDER"

_PROVIDERS = {
    "polar": PolarBilling,
}


def available_billing() -> list:
    return sorted(_PROVIDERS)


def get_billing(name: str = None, **kwargs):
    """Resolve a provider adapter by name, then ``$SHORTFORM_BILLING_PROVIDER``."""
    name = name or os.environ.get(ENV_PROVIDER) or DEFAULT_PROVIDER
    if name not in _PROVIDERS:
        raise BillingError(
            "unknown billing provider %r (available: %s)"
            % (name, ", ".join(available_billing()))
        )
    return _PROVIDERS[name](**kwargs)


__all__ = [
    "BillingError",
    "CATALOG",
    "Checkout",
    "Order",
    "Price",
    "Product",
    "Subscription",
    "WebhookEvent",
    "available_billing",
    "build_product_body",
    "get_billing",
    "iso_now",
    "resolve_api_key",
]
