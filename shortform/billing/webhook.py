"""Polar webhook signature verification (Standard Webhooks), stdlib only.

Polar signs every delivery with the Standard Webhooks scheme::

    base string = webhook-id + "." + webhook-timestamp + "." + raw_body
    signature   = base64(HMAC-SHA256(key, base string))
    header      = webhook-signature: v1,<base64>   (space separated list)

Key derivation:
  * ``whsec_`` secrets are Standard Webhooks: the prefix is stripped and the
    remainder is base64-decoded;
  * legacy Polar secrets use the UTF-8 bytes of the whole ``whsec_...`` string.

``verify_signature`` tries both by default (``scheme="auto"``) and ALWAYS
compares with :func:`hmac.compare_digest`. The raw body must be the bytes
received: re-serialising the JSON breaks the signature.

The secret is the harness credential-store name ``POLAR_WEBHOOK_SECRET`` and is
read at CALL time; it is never logged.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import time

from .base import WebhookEvent
from . import ledger as ledger_mod

ID_HEADER = "webhook-id"
TIMESTAMP_HEADER = "webhook-timestamp"
SIGNATURE_HEADER = "webhook-signature"
DEFAULT_TOLERANCE_SECONDS = 300


def _headers_lower(headers) -> dict:
    return {str(key).lower(): value for key, value in dict(headers or {}).items()}


def _b64decode_padded(value: str):
    padding = "=" * (-len(value) % 4)
    try:
        return base64.b64decode(value + padding)
    except (binascii.Error, ValueError):
        return None


def candidate_keys(secret: str, scheme: str = "auto") -> list:
    secret = secret or ""
    if scheme == "polar-legacy":
        return [secret.encode("utf-8")]
    if not secret.startswith("whsec_"):
        return [secret.encode("utf-8")]
    payload = secret[len("whsec_"):]
    standard = _b64decode_padded(payload)
    if scheme == "standard":
        return [standard] if standard else []
    keys = []
    if standard:
        keys.append(standard)
    keys.append(secret.encode("utf-8"))
    return keys


def signing_base(msg_id: str, timestamp: str, raw_body: bytes) -> bytes:
    if isinstance(raw_body, str):
        raw_body = raw_body.encode("utf-8")
    return ("%s.%s." % (msg_id, timestamp)).encode("utf-8") + raw_body


def expected_signatures(msg_id: str, timestamp: str, raw_body: bytes,
                        secret: str, scheme: str = "auto") -> list:
    base = signing_base(msg_id, timestamp, raw_body)
    out = []
    for key in candidate_keys(secret, scheme):
        digest = hmac.new(key, base, hashlib.sha256).digest()
        out.append(base64.b64encode(digest).decode("ascii"))
    return out


def parse_signature_header(header: str) -> list:
    out = []
    for part in str(header or "").split():
        part = part.strip()
        if not part:
            continue
        if "," in part:
            version, _, value = part.partition(",")
            if version.strip() == "v1":
                out.append(value.strip())
        else:
            out.append(part)
    return out


def verify_signature(raw_body, headers, secret: str,
                     tolerance: int = DEFAULT_TOLERANCE_SECONDS,
                     scheme: str = "auto", now=None) -> bool:
    """True when the delivery is authentically signed by ``secret``."""
    if not secret:
        return False
    sent = _headers_lower(headers)
    msg_id = sent.get(ID_HEADER)
    timestamp = sent.get(TIMESTAMP_HEADER)
    signature_header = sent.get(SIGNATURE_HEADER)
    if not msg_id or not timestamp or not signature_header:
        return False
    try:
        age = abs(int(float(str(timestamp))) - int(now or time.time()))
    except (TypeError, ValueError):
        return False
    if tolerance and age > float(tolerance):
        return False
    provided = parse_signature_header(signature_header)
    if not provided:
        return False
    for expected in expected_signatures(msg_id, timestamp, raw_body, secret, scheme):
        for candidate in provided:
            if hmac.compare_digest(expected, candidate):
                return True
    return False


def parse_event(raw_body, headers=None) -> WebhookEvent:
    if isinstance(raw_body, (bytes, bytearray)):
        raw_body = raw_body.decode("utf-8")
    payload = json.loads(raw_body or "{}")
    event = WebhookEvent.from_dict(payload)
    if not event.id:
        sent = _headers_lower(headers)
        event.id = str(
            sent.get(ID_HEADER)
            or payload.get("webhook_id")
            or payload.get("event_id")
            or ""
        )
    return event


def webhook_secret() -> str:
    """The ``whsec_`` secret, read at CALL time from the env/store name."""
    return os.environ.get("POLAR_WEBHOOK_SECRET") or ""


def handle_delivery(raw_body, headers, secret: str = None, path=None):
    """The local handler the deployed site mirrors.

    Returns ``(status_code, payload_dict)``. A bad or missing signature yields
    a non-2xx ``401`` and appends NOTHING to the ledger.
    """
    if isinstance(raw_body, str):
        raw_body = raw_body.encode("utf-8")
    secret = secret if secret is not None else webhook_secret()
    if not verify_signature(raw_body, headers, secret):
        return 401, {"ok": False, "error": "invalid_signature"}
    try:
        event = parse_event(raw_body, headers)
    except ValueError:
        return 400, {"ok": False, "error": "invalid_payload"}
    row = ledger_mod.append_event(event, path=path)
    return 200, {
        "ok": True,
        "duplicate": row is None,
        "event_id": ledger_mod.event_key(event),
        "type": event.type,
    }
