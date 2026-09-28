"""Provider-agnostic billing contracts.

These dataclasses are the *only* shapes the rest of the studio sees. A provider
adapter (``polar`` today) maps its wire format onto them, so a second provider
can be added without touching the CLI, the ledger or the deployed storefront.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field


class BillingError(RuntimeError):
    """Any billing failure: transport, auth, validation or refusal."""

    def __init__(self, message, status=None, body=None, capability=None):
        super().__init__(message)
        self.status = status
        self.body = body
        self.capability = capability


def iso_now() -> str:
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _get(mapping, *keys, default=None):
    for key in keys:
        if isinstance(mapping, dict) and mapping.get(key) is not None:
            return mapping[key]
    return default


@dataclass
class Price:
    id: str = ""
    amount_cents: int = 0
    currency: str = "usd"
    amount_type: str = "fixed"
    recurring_interval: str = None
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "Price":
        data = data or {}
        return cls(
            id=str(_get(data, "id", default="")),
            amount_cents=int(_get(data, "price_amount", "amount", default=0) or 0),
            currency=str(_get(data, "price_currency", "currency", default="usd") or "usd"),
            amount_type=str(_get(data, "amount_type", default="fixed") or "fixed"),
            recurring_interval=_get(data, "recurring_interval"),
            raw=data,
        )

    def price_label(self) -> str:
        return "%s %.2f" % (str(self.currency).upper(), self.amount_cents / 100.0)


@dataclass
class Product:
    id: str = ""
    name: str = ""
    description: str = ""
    is_recurring: bool = False
    recurring_interval: str = None
    prices: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)

    @property
    def slug(self) -> str:
        return str(self.metadata.get("slug") or "")

    @classmethod
    def from_dict(cls, data: dict) -> "Product":
        data = data or {}
        return cls(
            id=str(_get(data, "id", default="")),
            name=str(_get(data, "name", default="")),
            description=str(_get(data, "description", default="") or ""),
            is_recurring=bool(_get(data, "is_recurring", default=False)),
            recurring_interval=_get(data, "recurring_interval"),
            prices=[Price.from_dict(p) for p in (_get(data, "prices", default=[]) or [])],
            metadata=_get(data, "metadata", default={}) or {},
            raw=data,
        )


@dataclass
class Checkout:
    id: str = ""
    url: str = ""
    status: str = ""
    customer_email: str = None
    product_ids: list = field(default_factory=list)
    success_url: str = ""
    metadata: dict = field(default_factory=dict)
    expires_at: str = None
    subscription_id: str = None
    raw: dict = field(default_factory=dict)

    @property
    def paid(self) -> bool:
        return str(self.status).lower() in ("succeeded", "paid")

    @classmethod
    def from_dict(cls, data: dict) -> "Checkout":
        data = data or {}
        products = _get(data, "products", default=[]) or []
        return cls(
            id=str(_get(data, "id", default="")),
            url=str(_get(data, "url", default="")),
            status=str(_get(data, "status", default="")),
            customer_email=_get(data, "customer_email"),
            product_ids=[str(_get(p, "id", default="")) for p in products],
            success_url=str(_get(data, "success_url", default="") or ""),
            metadata=_get(data, "metadata", default={}) or {},
            expires_at=_get(data, "expires_at"),
            subscription_id=_get(data, "subscription_id"),
            raw=data,
        )


@dataclass
class Order:
    id: str = ""
    status: str = ""
    paid: bool = False
    checkout_id: str = None
    subscription_id: str = None
    product_id: str = None
    customer_email: str = None
    amount_cents: int = 0
    currency: str = "usd"
    created_at: str = None
    metadata: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "Order":
        data = data or {}
        customer = _get(data, "customer", default={}) or {}
        return cls(
            id=str(_get(data, "id", default="")),
            status=str(_get(data, "status", default="")),
            paid=bool(_get(data, "paid", default=False)),
            checkout_id=_get(data, "checkout_id"),
            subscription_id=_get(data, "subscription_id"),
            product_id=_get(data, "product_id"),
            customer_email=_get(customer, "email", default=_get(data, "customer_email")),
            amount_cents=int(_get(data, "total_amount", "amount", default=0) or 0),
            currency=str(_get(data, "currency", default="usd") or "usd"),
            created_at=_get(data, "created_at"),
            metadata=_get(data, "metadata", default={}) or {},
            raw=data,
        )


@dataclass
class Subscription:
    id: str = ""
    status: str = ""
    checkout_id: str = None
    customer_id: str = None
    customer_email: str = None
    product_id: str = None
    current_period_start: str = None
    current_period_end: str = None
    metadata: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)

    @property
    def active(self) -> bool:
        return str(self.status).lower() == "active"

    @classmethod
    def from_dict(cls, data: dict) -> "Subscription":
        data = data or {}
        customer = _get(data, "customer", default={}) or {}
        return cls(
            id=str(_get(data, "id", default="")),
            status=str(_get(data, "status", default="")),
            checkout_id=_get(data, "checkout_id"),
            customer_id=_get(data, "customer_id"),
            customer_email=_get(customer, "email", default=_get(data, "customer_email")),
            product_id=_get(data, "product_id"),
            current_period_start=_get(data, "current_period_start"),
            current_period_end=_get(data, "current_period_end"),
            metadata=_get(data, "metadata", default={}) or {},
            raw=data,
        )


@dataclass
class WebhookEvent:
    id: str = ""
    type: str = ""
    timestamp: str = None
    data: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)

    @property
    def object_id(self) -> str:
        return str(_get(self.data, "id", default="") or "")

    @property
    def checkout_id(self) -> str:
        return str(_get(self.data, "checkout_id", default="") or "")

    @property
    def subscription_id(self) -> str:
        value = _get(self.data, "subscription_id")
        if value:
            return str(value)
        if str(self.type).startswith("subscription."):
            return self.object_id
        return ""

    @property
    def customer_email(self) -> str:
        customer = _get(self.data, "customer", default={}) or {}
        return str(_get(customer, "email", default=_get(self.data, "customer_email", default="")) or "")

    @property
    def amount_cents(self) -> int:
        return int(_get(self.data, "total_amount", "amount", default=0) or 0)

    @property
    def status(self) -> str:
        return str(_get(self.data, "status", default="") or "")

    @classmethod
    def from_dict(cls, payload: dict) -> "WebhookEvent":
        payload = payload or {}
        data = _get(payload, "data", default={}) or {}
        event_id = _get(payload, "id", "webhook_id", "event_id", default="")
        if not event_id:
            event_id = _get(data, "id", "event_id", default="")
        return cls(
            id=str(event_id or ""),
            type=str(_get(payload, "type", "event", default="") or ""),
            timestamp=_get(payload, "timestamp", "created_at"),
            data=data,
            raw=payload,
        )
