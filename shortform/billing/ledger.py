"""Append-only billing ledger: ``ledger/ledger.jsonl``.

ONE row per provider event, idempotent on the provider event id: feeding the
same event twice appends exactly one row. The ledger is append-only - rows are
never rewritten or deleted.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from .base import WebhookEvent, iso_now

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_LEDGER = REPO_ROOT / "ledger" / "ledger.jsonl"
ENV_LEDGER = "SHORTFORM_BILLING_LEDGER"
_LOCK = threading.Lock()


def ledger_path(path=None) -> Path:
    if path is not None:
        return Path(path)
    override = os.environ.get(ENV_LEDGER)
    return Path(override) if override else DEFAULT_LEDGER


def rows(path=None) -> list:
    """All ledger rows, in file order (missing file reads as empty)."""
    target = ledger_path(path)
    if not target.exists():
        return []
    out = []
    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def event_key(event: WebhookEvent) -> str:
    """The provider idempotency key: the delivery id, else the object id."""
    return str(event.id or event.object_id or "")


def seen_event_ids(path=None) -> set:
    keys = set()
    for row in rows(path):
        key = row.get("event_id") or row.get("id")
        if key:
            keys.add(str(key))
    return keys


def append_event(event: WebhookEvent, provider: str = "polar", env: str = "sandbox",
                 path=None) -> dict:
    """Append one row for a verified provider event; return it, or ``None``.

    ``None`` means the event id was already present and NOTHING was appended.
    """
    key = event_key(event)
    with _LOCK:
        if key and key in seen_event_ids(path):
            return None
        row = {
            "ts": iso_now(),
            "provider": provider,
            "env": env,
            "event_id": key,
            "type": event.type,
            "object_id": event.object_id,
            "status": event.status,
            "checkout_id": event.checkout_id,
            "subscription_id": event.subscription_id,
            "customer_email": event.customer_email,
            "amount_cents": event.amount_cents,
            "currency": str((event.data or {}).get("currency") or "usd"),
            "slug": str(((event.data or {}).get("metadata") or {}).get("slug") or ""),
        }
        target = ledger_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
        return row
