#!/usr/bin/env python3
"""A tiny stdlib YouTube Data API v3 mock for credential-free end-to-end tests.

Endpoints
---------
POST /upload/youtube/v3/videos?uploadType=resumable
    Resumable-upload initiation. Returns ``Location`` (and an uploader id).
PUT  /upload-session/<id>
    Accepts the video bytes and returns ``{"id": "MOCKID123", ...}``.
GET  /youtube/v3/videos?part=snippet,statistics&id=<ID>&key=<KEY>
    Returns a realistic video resource with ``statistics``.

Every request line, header and body size is appended to ``mocks/transcript.log``
(Authorization headers are redacted), which is the raw evidence path used when no
real Google credential is available. There is no Google sandbox for
``videos.insert``; this mock is what makes the publish/measure legs verifiable.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TRANSCRIPT = REPO_ROOT / "mocks" / "transcript.log"

_LOG_LOCK = threading.Lock()
_LOG_PATH: Path = DEFAULT_TRANSCRIPT
_PID = os.getpid()

# A single stable id so the measure leg always asks for the video we "uploaded".
MOCK_VIDEO_ID = "MOCKID123"

MOCK_STATISTICS = {
    "viewCount": "12874",
    "likeCount": "1043",
    "favoriteCount": "0",
    "commentCount": "87",
}


def _redact(name: str, value: str) -> str:
    if name.lower() == "authorization":
        token = value.split(" ", 1)[-1]
        return f"Bearer <redacted:{len(token)} chars>"
    return value


def log_block(lines: list[str]) -> None:
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with _LOG_LOCK:
        with open(_LOG_PATH, "a", encoding="utf-8") as fh:
            for line in lines:
                fh.write(f"{stamp} pid={_PID} {line}\n")
            fh.flush()


class MockHandler(BaseHTTPRequestHandler):
    server_version = "YouTubeMock/1.0"
    protocol_version = "HTTP/1.1"

    # ---- plumbing ---------------------------------------------------------
    def _log_request_line(self) -> None:
        self._request_lines = [
            f"REQUEST {self.command} {self.path} {self.request_version}",
        ]
        for key, value in self.headers.items():
            self._request_lines.append(f"  {key}: {_redact(key, value)}")

    def _respond(self, code: int, body: bytes, headers: dict[str, str] | None = None) -> None:
        self.send_response(code)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self._request_lines.append(f"RESPONSE {code} {headers or {}} body={len(body)} bytes")
        log_block(self._request_lines)

    def log_message(self, fmt: str, *args) -> None:  # keep stderr quiet-ish but visible
        sys.stderr.write("[mock] " + (fmt % args) + "\n")

    # ---- routes -----------------------------------------------------------
    def do_POST(self) -> None:  # noqa: N802
        self._log_request_line()
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        self._request_lines.append(f"  BODY {body.decode('utf-8', 'replace')!r} ({len(body)} bytes)")

        if parsed.path == "/upload/youtube/v3/videos" and query.get("uploadType") == ["resumable"]:
            session = uuid.uuid4().hex
            host = self.headers.get("Host", "127.0.0.1")
            location = f"http://{host}/upload-session/{session}"
            headers = {
                "Location": location,
                "X-GUploader-UploadID": session,
            }
            self._respond(200, json.dumps({"session": session}).encode(), headers)
            return

        self._respond(404, json.dumps({"error": "not found", "path": parsed.path}).encode())

    def do_PUT(self) -> None:  # noqa: N802
        self._log_request_line()
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        self._request_lines.append(
            f"  RECEIVED {len(body)} video bytes (sha256-free mock); first4={body[:4]!r}"
        )
        if parsed.path.startswith("/upload-session/"):
            resource = {
                "kind": "youtube#video",
                "etag": "mock-etag",
                "id": MOCK_VIDEO_ID,
                "snippet": {"title": "Mock Upload", "channelId": "MOCKCHANNEL"},
                "status": {"privacyStatus": "private", "uploadStatus": "uploaded"},
            }
            self._respond(200, json.dumps(resource).encode())
            return
        self._respond(404, json.dumps({"error": "not found", "path": parsed.path}).encode())

    def do_GET(self) -> None:  # noqa: N802
        self._log_request_line()
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/youtube/v3/videos":
            video_id = (query.get("id") or [MOCK_VIDEO_ID])[0]
            payload = {
                "kind": "youtube#videoListResponse",
                "etag": "mock-etag",
                "pageInfo": {"totalResults": 1, "resultsPerPage": 1},
                "items": [
                    {
                        "kind": "youtube#video",
                        "etag": "mock-etag",
                        "id": video_id,
                        "snippet": {
                            "title": "How Roman concrete survived 2000 years #Shorts",
                            "channelTitle": "OmniStack Mock Channel",
                            "publishedAt": "2026-09-27T00:00:00Z",
                            "categoryId": "27",
                        },
                        "statistics": dict(MOCK_STATISTICS),
                    }
                ],
            }
            self._respond(200, json.dumps(payload).encode())
            return
        self._respond(404, json.dumps({"error": "not found", "path": parsed.path}).encode())


def serve(host: str = "127.0.0.1", port: int = 8787, transcript: Path | None = None) -> None:
    global _LOG_PATH
    _LOG_PATH = Path(transcript) if transcript else DEFAULT_TRANSCRIPT
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    log_block([f"SESSION START mock listening on http://{host}:{port} transcript={_LOG_PATH}"])
    httpd = ThreadingHTTPServer((host, port), MockHandler)
    print(f"[mock] YouTube mock listening on http://{host}:{port}", flush=True)
    print(f"[mock] transcript -> {_LOG_PATH}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        log_block(["SESSION STOP mock server stopped"])
        httpd.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="stdlib YouTube Data API v3 mock")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("MOCK_PORT", "8787")))
    parser.add_argument("--transcript", default=str(DEFAULT_TRANSCRIPT))
    args = parser.parse_args(argv)
    serve(args.host, args.port, Path(args.transcript))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
