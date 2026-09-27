"""``shortform publish`` - YouTube Data API v3 resumable upload.

The SAME code is used against the real Google endpoint and against the local
mock (``--api-base http://127.0.0.1:8787``); only the base URL changes.

* ``--dry-run`` (default) prints the exact method/URL/headers/body and sends
  NOTHING.
* ``--live`` requires ``$YOUTUBE_OAUTH_TOKEN``; when it is missing we print an
  exact human-handover message and exit 2. We never fake an upload.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from . import util

REAL_API_BASE = "https://www.googleapis.com"
UPLOAD_PATH = "/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
PRIVACY_CHOICES = ("private", "unlisted", "public")

HANDOVER_MESSAGE = """\
[HUMAN HANDOVER REQUIRED] Cannot publish live: $YOUTUBE_OAUTH_TOKEN is not set.
No upload was attempted and nothing was faked.

To enable a live upload a human must:
  1. In Google Cloud Console create/select a project and enable "YouTube Data API v3".
  2. Configure the OAuth consent screen (External, Testing is fine) and add the scope
     https://www.googleapis.com/auth/youtube.upload
  3. Create an OAuth 2.0 Client ID of type "Desktop app", then run the OAuth flow
     (for example `google-auth-oauthlib`'s InstalledAppFlow) to mint an access token.
  4. Export it for this shell and re-run:
       export YOUTUBE_OAUTH_TOKEN="ya29.<...>"
       python -m shortform publish --slug <slug> --live --privacy private
  5. Approve the upload in YouTube Studio; the default privacy is "private" on purpose.
"""


def build_upload_body(metadata: dict[str, Any], privacy: str) -> dict[str, Any]:
    snippet = dict(metadata.get("snippet", {}))
    status = dict(metadata.get("status", {}))
    status["privacyStatus"] = privacy
    status.setdefault("selfDeclaredMadeForKids", False)
    return {"snippet": snippet, "status": status}


def _http(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
    timeout: float = 60.0,
) -> tuple[int, dict[str, str], bytes]:
    req = urllib.request.Request(url, data=data, method=method)
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers.items()), resp.read()
    except urllib.error.HTTPError as err:  # pragma: no cover - network path
        return err.code, dict(err.headers.items()) if err.headers else {}, err.read()


def _redact_headers(headers: dict[str, str]) -> dict[str, str]:
    out = {}
    for key, value in headers.items():
        if key.lower() == "authorization":
            token = value.split(" ", 1)[-1]
            out[key] = f"Bearer <redacted:{len(token)} chars>"
        else:
            out[key] = value
    return out


def publish(
    slug: str,
    *,
    mode: str = "dry-run",
    privacy: str = "private",
    api_base: str = REAL_API_BASE,
    root: Path | None = None,
) -> int:
    if mode not in ("dry-run", "live"):
        raise ValueError("mode must be 'dry-run' or 'live'")
    if privacy not in PRIVACY_CHOICES:
        raise ValueError(f"privacy must be one of {PRIVACY_CHOICES}")

    root = root or util.repo_root()
    out = util.out_dir(slug, root)
    video = out / "video.mp4"
    meta_path = out / "metadata.json"
    if not video.exists():
        raise FileNotFoundError(f"no video at {video}; run produce first")
    if not meta_path.exists():
        raise FileNotFoundError(f"no metadata at {meta_path}; run produce first")

    metadata = util.read_json(meta_path)
    body = build_upload_body(metadata, privacy)
    body_bytes = json.dumps(body).encode("utf-8")
    size = video.stat().st_size

    token = os.environ.get("YOUTUBE_OAUTH_TOKEN", "").strip()
    upload_url = api_base.rstrip("/") + UPLOAD_PATH
    init_headers = {
        "Authorization": f"Bearer {token}" if token else "Bearer <YOUTUBE_OAUTH_TOKEN NOT SET>",
        "Content-Type": "application/json; charset=UTF-8",
        "X-Upload-Content-Type": "video/mp4",
        "X-Upload-Content-Length": str(size),
    }

    if mode == "dry-run":
        print("=== DRY RUN (no network request is sent) ===")
        print(f"STEP 1: {upload_url}  [METHOD: POST]")
        print("Headers:")
        for key, value in _redact_headers(init_headers).items():
            print(f"  {key}: {value}")
        print("Body:")
        print(json.dumps(body, indent=2, ensure_ascii=False))
        print()
        print("STEP 2: PUT <Location returned by step 1>")
        print("Headers:")
        print("  Content-Type: video/mp4")
        print(f"  Content-Length: {size}")
        print(f"Body: <{size} bytes of {video}>")
        print()
        print("DRY RUN COMPLETE - nothing was uploaded.")
        return 0

    # ---- live path ----
    if not token:
        print(HANDOVER_MESSAGE, file=os.sys.stderr)
        return 2

    print(f"POST {upload_url}")
    status, headers, payload = _http(
        "POST", upload_url, headers=init_headers, data=body_bytes
    )
    if status not in (200, 201):
        raise RuntimeError(f"resumable init failed: HTTP {status}: {payload[:1000]!r}")
    location = headers.get("Location") or headers.get("location")
    if not location:
        raise RuntimeError(f"no Location header in resumable init response: {headers}")

    print(f"  -> session Location: {location}")
    print(f"PUT {location} ({size} bytes)")
    put_headers = {
        "Content-Type": "video/mp4",
        "Content-Length": str(size),
    }
    with open(video, "rb") as fh:
        status, headers, payload = _http("PUT", location, headers=put_headers, data=fh.read())
    if status not in (200, 201):
        raise RuntimeError(f"upload failed: HTTP {status}: {payload[:1000]!r}")

    try:
        resource = json.loads(payload.decode("utf-8", "replace"))
    except json.JSONDecodeError:
        resource = {"raw": payload.decode("utf-8", "replace")}
    video_id = resource.get("id")

    result = {
        "slug": slug,
        "uploaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "api_base": api_base,
        "privacy_status": privacy,
        "http_status": status,
        "video": str(video),
        "bytes": size,
        "video_id": video_id,
        "response": resource,
    }
    util.write_json(out / "publish-result.json", result)
    print(f"UPLOAD OK id={video_id} privacy={privacy}")
    return 0
