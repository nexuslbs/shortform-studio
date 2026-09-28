"""``shortform measure`` - fetch public statistics and snapshot them locally.

Uses ``GET /youtube/v3/videos?part=snippet,statistics&id=<ID>&key=$YOUTUBE_API_KEY``
against the real API, or against the bundled mock with ``--mock`` (or an
explicit ``--api-base``). Each numeric metric is appended to the
``measurement_series`` table and the raw snapshot is mirrored to
``{data_root}/measurements/<id>.jsonl`` (never the repo tree).
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from . import paths, store, util

REAL_API_BASE = "https://www.googleapis.com"
DEFAULT_MOCK_BASE = os.environ.get("MOCK_API_BASE", "http://127.0.0.1:8787")

MEASURE_HANDOVER = """\
[HUMAN HANDOVER REQUIRED] Cannot measure against the real API: $YOUTUBE_API_KEY is not set.
No request was sent.

A human must:
  1. Enable "YouTube Data API v3" in Google Cloud Console.
  2. Create an API key (restrict it to the YouTube Data API v3).
  3. export YOUTUBE_API_KEY="AIza..."
  4. python -m shortform measure --video-id <ID>
For offline verification use: python -m shortform measure --video-id <ID> --mock
"""


def _get(url: str, timeout: float = 30.0) -> tuple[int, bytes]:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as err:  # pragma: no cover - network path
        return err.code, err.read()
    except (urllib.error.URLError, OSError) as err:  # pragma: no cover - network path
        # DNS failure, refused connection, timeout, TLS error, ...: surface a
        # clean one-line network error instead of a raw traceback.
        raise util.NetworkError(f"GET {url}: {err}") from err


def view_through_placeholder(stats: dict[str, Any]) -> float | None:
    """A transparent *placeholder*, not a real Analytics view-through metric.

    YouTube's public Data API exposes only views/likes/comments; the real
    view-through rate needs the YouTube Analytics API with OAuth. We derive a
    bounded engagement proxy and label it as a placeholder so nobody mistakes it
    for a platform metric.
    """
    try:
        views = int(stats.get("viewCount", 0) or 0)
        likes = int(stats.get("likeCount", 0) or 0)
        comments = int(stats.get("commentCount", 0) or 0)
    except (TypeError, ValueError):
        return None
    if views <= 0:
        return 0.0
    return round(min(100.0, 100.0 * (likes + comments + 1) / (views + 1)), 3)


def measure(
    video_id: str,
    *,
    mock: bool = False,
    api_base: str | None = None,
    root: Path | None = None,
    artifacts_root: Path | None = None,
) -> int:
    # ``root`` is the SOURCE repository root; ``artifacts_root`` is an explicit
    # data-root override for tests. Snapshots always land outside the repo.
    root = root or util.repo_root()
    base = api_base or (DEFAULT_MOCK_BASE if mock else REAL_API_BASE)

    if mock:
        key = os.environ.get("YOUTUBE_API_KEY", "MOCK_KEY")
    else:
        key = os.environ.get("YOUTUBE_API_KEY", "").strip()
        if not key:
            print(MEASURE_HANDOVER, file=os.sys.stderr)
            return 2

    query = urllib.parse.urlencode(
        {"part": "snippet,statistics", "id": video_id, "key": key}
    )
    url = f"{base.rstrip('/')}/youtube/v3/videos?{query}"
    print(f"GET {url}")
    status, payload = _get(url)
    if status != 200:
        raise RuntimeError(f"measure failed: HTTP {status}: {payload[:1000]!r}")

    data = json.loads(payload.decode("utf-8", "replace"))
    items = data.get("items", [])
    if not items:
        print(f"no video found for id={video_id}")
        return 1

    item = items[0]
    stats = item.get("statistics", {})
    snippet = item.get("snippet", {})
    snapshot = {
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "video_id": item.get("id", video_id),
        "source": "mock" if mock else "youtube-data-api-v3",
        "api_base": base,
        "title": snippet.get("title"),
        "channelTitle": snippet.get("channelTitle"),
        "statistics": stats,
        "view_through_placeholder_pct": view_through_placeholder(stats),
        "view_through_note": (
            "Placeholder derived from public likes/comments/views; the real "
            "view-through rate requires the YouTube Analytics API (OAuth)."
        ),
    }
    metrics_path = paths.measurements_dir(artifacts_root) / f"{video_id}.jsonl"
    util.ensure_dir(metrics_path.parent)
    with open(metrics_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(snapshot, ensure_ascii=False) + "\n")

    def _as_number(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    numeric_metrics = {}
    for name in ("viewCount", "likeCount", "commentCount", "favoriteCount"):
        number = _as_number(stats.get(name))
        if number is not None:
            numeric_metrics[name.lower()] = number
    placeholder = snapshot.get("view_through_placeholder_pct")
    if placeholder is not None:
        numeric_metrics["view_through_placeholder_pct"] = float(placeholder)
    store.record_measurements(
        snapshot["video_id"],
        "mock" if mock else "youtube-data-api-v3",
        numeric_metrics,
        ts=snapshot["fetched_at"],
        conn=None,
    )

    print(f"title: {snapshot['title']}")
    print(f"views: {stats.get('viewCount', 0)}")
    print(f"likes: {stats.get('likeCount', 0)}")
    print(f"comments: {stats.get('commentCount', 0)}")
    print(f"view_through_placeholder_pct: {snapshot['view_through_placeholder_pct']}")
    print(f"snapshot appended to {metrics_path}")
    return 0
