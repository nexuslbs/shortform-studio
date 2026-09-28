"""Tests for the provider-agnostic billing module.

Run with:  python3 -m pytest tests/ -v
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from shortform import billing  # noqa: E402
from shortform.billing import ledger as ledger_mod  # noqa: E402
from shortform.billing import webhook as webhook_mod  # noqa: E402
from shortform.billing.base import BillingError, WebhookEvent  # noqa: E402
from shortform.billing.polar import SANDBOX_BASE, PolarBilling  # noqa: E402


def _secret() -> str:
    return "whsec_" + base64.b64encode(b"shortform-test-signing-key").decode("ascii")


def _signed(body: bytes, secret: str | None = None, timestamp: str | None = None):
    import time

    secret = secret or _secret()
    msg_id = "msg_shortform_test"
    timestamp = timestamp or str(int(time.time()))
    key = base64.b64decode(secret[len("whsec_"):])
    base = ("%s.%s." % (msg_id, timestamp)).encode("utf-8") + body
    signature = base64.b64encode(hmac.new(key, base, hashlib.sha256).digest()).decode("ascii")
    headers = {
        "webhook-id": msg_id,
        "webhook-timestamp": timestamp,
        "webhook-signature": "v1,%s" % signature,
    }
    return headers


# --------------------------------------------------------------------------- #
# Signature accept / reject
# --------------------------------------------------------------------------- #

def test_signature_accepts_valid_delivery():
    body = b'{"type":"order.paid","data":{"id":"ord_1"}}'
    assert webhook_mod.verify_signature(body, _signed(body), _secret()) is True


def test_signature_rejects_tampered_body():
    body = b'{"type":"order.paid","data":{"id":"ord_1"}}'
    headers = _signed(body)
    assert webhook_mod.verify_signature(body + b" ", headers, _secret()) is False


def test_signature_rejects_tampered_signature():
    body = b'{"type":"order.paid","data":{"id":"ord_1"}}'
    headers = _signed(body)
    headers["webhook-signature"] = "v1,AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
    assert webhook_mod.verify_signature(body, headers, _secret()) is False


def test_signature_rejects_missing_secret_and_stale_timestamp():
    body = b"{}"
    headers = _signed(body)
    assert webhook_mod.verify_signature(body, headers, "") is False
    stale = _signed(body, timestamp=str(1000000000))
    assert webhook_mod.verify_signature(body, stale, _secret()) is False


def test_handle_delivery_rejects_bad_signature_with_non_2xx(tmp_path):
    body = b'{"type":"order.paid","data":{"id":"ord_bad"}}'
    headers = _signed(body)
    headers["webhook-signature"] = "v1,bogus"
    status, payload = webhook_mod.handle_delivery(
        body, headers, secret=_secret(), path=tmp_path / "ledger.jsonl")
    assert status == 401
    assert payload["ok"] is False
    assert not (tmp_path / "ledger.jsonl").exists()


def test_handle_delivery_accepts_and_ledgers(tmp_path):
    body = b'{"type":"order.paid","data":{"id":"ord_ok","status":"paid","total_amount":900}}'
    target = tmp_path / "ledger.jsonl"
    status, payload = webhook_mod.handle_delivery(
        body, _signed(body), secret=_secret(), path=target)
    assert status == 200
    assert payload["ok"] is True
    assert len(ledger_mod.rows(target)) == 1


# --------------------------------------------------------------------------- #
# Ledger idempotency
# --------------------------------------------------------------------------- #

def test_ledger_is_idempotent_on_provider_event_id(tmp_path):
    target = tmp_path / "ledger.jsonl"
    event = WebhookEvent.from_dict({"id": "evt_1", "type": "order.paid",
                                    "data": {"id": "ord_1", "status": "paid"}})
    first = ledger_mod.append_event(event, path=target)
    second = ledger_mod.append_event(event, path=target)
    assert first is not None
    assert second is None
    rows = ledger_mod.rows(target)
    assert len(rows) == 1
    assert rows[0]["event_id"] == "evt_1"
    assert rows[0]["type"] == "order.paid"


def test_ledger_appends_distinct_events(tmp_path):
    target = tmp_path / "ledger.jsonl"
    for event_id in ("evt_a", "evt_b"):
        event = WebhookEvent.from_dict({"id": event_id, "type": "order.created",
                                        "data": {"id": "ord_%s" % event_id}})
        assert ledger_mod.append_event(event, path=target) is not None
    assert len(ledger_mod.rows(target)) == 2


# --------------------------------------------------------------------------- #
# Provider selection + sandbox default
# --------------------------------------------------------------------------- #

def test_provider_selection_by_env(monkeypatch):
    monkeypatch.setenv("SHORTFORM_BILLING_PROVIDER", "polar")
    provider = billing.get_billing()
    assert isinstance(provider, PolarBilling)
    monkeypatch.setenv("SHORTFORM_BILLING_PROVIDER", "stripe")
    with pytest.raises(BillingError):
        billing.get_billing()
    assert billing.available_billing() == ["polar"]


def test_sandbox_base_url_is_default(monkeypatch):
    monkeypatch.delenv("POLAR_API_BASE", raising=False)
    provider = billing.get_billing("polar")
    assert provider.base_url == SANDBOX_BASE
    assert provider.env == "sandbox"
    assert "api.polar.sh" not in provider.base_url.replace("sandbox-api.polar.sh", "")


def test_live_host_is_refused(monkeypatch):
    monkeypatch.setenv("POLAR_API_BASE", "https://api.polar.sh/v1")
    with pytest.raises(BillingError):
        billing.get_billing("polar")
    assert billing.get_billing("polar", allow_live=True).base_url == "https://api.polar.sh/v1"


def test_api_key_resolved_at_call_time(monkeypatch):
    provider = PolarBilling()
    monkeypatch.delenv("POLAR_API_KEY", raising=False)
    monkeypatch.delenv("SANDBOX_POLAR_API_KEY_SHORTFORM_STUDIO", raising=False)
    assert provider.api_key == ""
    monkeypatch.setenv("SANDBOX_POLAR_API_KEY_SHORTFORM_STUDIO", "tok_late")
    assert provider.api_key == "tok_late"
    assert "tok_late" not in json.dumps(provider.describe())


# --------------------------------------------------------------------------- #
# CLI dry-run
# --------------------------------------------------------------------------- #

def _run_cli(args, env_extra=None):
    env = dict(os.environ)
    env.pop("POLAR_API_KEY", None)
    env.pop("SANDBOX_POLAR_API_KEY_SHORTFORM_STUDIO", None)
    env.update(env_extra or {})
    return subprocess.run([sys.executable, "-m", "shortform", *args],
                          cwd=str(REPO), capture_output=True, text=True,
                          env=env, timeout=30)


def test_provision_dry_run_prints_bodies_without_calling_api(monkeypatch):
    # Calling the command function directly with _request poisoned proves no
    # provider API call is made on the dry-run path.
    from shortform import billing_cli

    def _boom(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("dry-run must not call the provider API")

    monkeypatch.setattr(PolarBilling, "_request", _boom)
    assert billing_cli.cmd_provision(type("A", (), {"dry_run": True})()) == 0


def test_provision_dry_run_cli_output():
    proc = _run_cli(["billing", "provision", "--dry-run"])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = proc.stdout
    assert "POST /products/" in out
    assert "shortform-video-pack" in out
    assert "shortform-creator-monthly" in out
    assert '"recurring_interval": "month"' in out
    # a dry-run needs no credential at all
    assert "missing polar sandbox credential" not in (proc.stdout + proc.stderr)


def test_webhook_cli_rejects_bad_signature(tmp_path):
    body = tmp_path / "body.json"
    body.write_bytes(b'{"type":"order.paid","data":{"id":"ord_cli"}}')
    proc = _run_cli(["billing", "webhook", "--body-file", str(body)], {
        "POLAR_WEBHOOK_SECRET": _secret(),
        "WEBHOOK_ID": "msg_x",
        "WEBHOOK_TIMESTAMP": "1000000000",
        "WEBHOOK_SIGNATURE": "v1,bogus",
    })
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert '"status": 401' in proc.stdout
