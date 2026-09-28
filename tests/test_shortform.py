"""Unit tests for the shortform pipeline.

These tests are deliberately cheap: they exercise script parsing, caption
building, the description/metadata policy text, the QA report shape and the mock
server, without re-encoding a full video. The end-to-end encode path is covered
by ``scripts/selftest.sh`` (which leaves raw evidence under ``out/selftest/``).

Run with:  python3 -m pytest tests/ -v
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from shortform import measure, produce, qa  # noqa: E402
from shortform.publish import build_upload_body, _redact_headers, publish  # noqa: E402


# --------------------------------------------------------------------------- #
# Script / duration / captions
# --------------------------------------------------------------------------- #

def test_load_real_script():
    script = produce.load_script(REPO / "content" / "roman-concrete" / "script.json")
    assert script["topic"] == "How Roman concrete survived 2000 years"
    assert len(script["narration"]) >= 4
    for scene in script["narration"]:
        assert scene["say"].strip()
        assert scene["onscreen"].strip()
        assert scene["hold"] > 0


def test_scene_durations_sum_and_rescale():
    script = produce.load_script(REPO / "content" / "roman-concrete" / "script.json")
    holds = produce.scene_durations(script, None)
    assert 30.0 <= sum(holds) <= 45.0
    scaled = produce.scene_durations(script, 20.0)
    assert abs(sum(scaled) - 20.0) < 0.01


def test_build_srt_shape():
    scenes = [
        {"scene": 1, "say": "First line.", "onscreen": "ONE", "hold": 4.0},
        {"scene": 2, "say": "Second line.", "onscreen": "TWO", "hold": 6.0},
    ]
    srt = produce.build_srt(scenes, [4.0, 6.0])
    assert "00:00:00,000 --> 00:00:04,000" in srt
    assert "00:00:04,000 --> 00:00:10,000" in srt
    assert srt.strip().endswith("Second line.")


def test_srt_timestamp_hours():
    assert produce._ts(3661.5) == "01:01:01,500"


# --------------------------------------------------------------------------- #
# Policy copy
# --------------------------------------------------------------------------- #

def test_description_contains_disclosure_and_shorts():
    script = produce.load_script(REPO / "content" / "roman-concrete" / "script.json")
    desc = produce.build_description(script)
    assert "#Shorts" in desc
    assert produce.DISCLOSURE_SENTENCE in desc
    assert len(desc) <= 5000
    # No affiliate link, so no affiliate disclosure is required or injected.
    assert produce.AFFILIATE_DISCLOSURE not in desc


def test_description_injects_affiliate_disclosure_when_asked():
    script = produce.load_script(REPO / "content" / "roman-concrete" / "script.json")
    desc = produce.build_description(script, has_affiliate=True)
    assert produce.AFFILIATE_DISCLOSURE in desc


def test_metadata_kids_flag_and_disclosure():
    script = produce.load_script(REPO / "content" / "roman-concrete" / "script.json")
    meta = produce.build_metadata(script, produce.build_description(script))
    assert meta["status"]["selfDeclaredMadeForKids"] is False
    assert meta["selfDeclaredMadeForKids"] is False
    assert meta["status"]["containsSyntheticMedia"] is True


def test_title_within_limit():
    script = produce.load_script(REPO / "content" / "roman-concrete" / "script.json")
    assert len(script["title"]) <= 100


# --------------------------------------------------------------------------- #
# QA logic on a tiny synthetic ffprobe payload
# --------------------------------------------------------------------------- #

def test_run_qa_missing_video(tmp_path):
    report, code = qa.run_qa("does-not-exist", artifacts_root=tmp_path)
    assert code == 1
    assert report["pass"] is False
    assert report["checks"][0]["check"] == "video_exists"


def test_view_through_placeholder_bounds():
    pct = measure.view_through_placeholder(
        {"viewCount": "1000", "likeCount": "100", "commentCount": "10"}
    )
    assert 0.0 <= pct <= 100.0
    assert measure.view_through_placeholder({"viewCount": "0"}) == 0.0


# --------------------------------------------------------------------------- #
# Publish request shape
# --------------------------------------------------------------------------- #

def test_build_upload_body_forces_privacy():
    meta = {
        "snippet": {"title": "T", "description": "D"},
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
    }
    body = build_upload_body(meta, "private")
    assert body["status"]["privacyStatus"] == "private"
    assert body["snippet"]["title"] == "T"
    # original metadata is not mutated
    assert meta["status"]["privacyStatus"] == "public"


def test_redact_headers_hides_token():
    red = _redact_headers({"Authorization": "Bearer supersecrettoken"})
    assert "supersecrettoken" not in json.dumps(red)
    assert "redacted" in red["Authorization"]


def test_redact_headers_keeps_missing_token_marker():
    # F1: the missing-token marker is NOT a secret and must never be masked.
    red = _redact_headers({"Authorization": "Bearer <YOUTUBE_OAUTH_TOKEN NOT SET>"})
    assert red["Authorization"] == "Bearer <YOUTUBE_OAUTH_TOKEN NOT SET>"
    assert "redacted" not in red["Authorization"]


def _fake_artifact(data_root: Path, slug: str = "roman-concrete") -> Path:
    """A tiny stand-in video + metadata at an external artifact root."""
    artifact = data_root / slug
    artifact.mkdir(parents=True, exist_ok=True)
    (artifact / "video.mp4").write_bytes(b"not-a-real-mp4")
    (artifact / "metadata.json").write_text(
        json.dumps({"snippet": {"title": "T"}, "status": {}}), encoding="utf-8"
    )
    return artifact


def test_dry_run_without_token_shows_not_set(monkeypatch, capsys, tmp_path):
    # F1: a dry-run without $YOUTUBE_OAUTH_TOKEN must say so explicitly.
    monkeypatch.delenv("YOUTUBE_OAUTH_TOKEN", raising=False)
    _fake_artifact(tmp_path)
    assert publish("roman-concrete", mode="dry-run", root=REPO, artifacts_root=tmp_path) == 0
    out = capsys.readouterr().out
    auth_lines = [
        line.strip()
        for line in out.splitlines()
        if line.strip().lower().startswith("authorization")
    ]
    assert auth_lines == ["Authorization: Bearer <YOUTUBE_OAUTH_TOKEN NOT SET>"]
    assert "redacted" not in "\n".join(auth_lines)


def _dead_port() -> int:
    """Return a TCP port that was bound and then closed (nothing listening)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _run_cli(args: list[str], env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, "-m", "shortform", *args],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def test_measure_network_error_exits_3_cleanly():
    # F2: a dead host must not print a traceback; it exits 3 with one clean line.
    port = _dead_port()
    proc = _run_cli(
        ["measure", "--video-id", "MOCKID123", "--api-base", f"http://127.0.0.1:{port}"],
        {"YOUTUBE_API_KEY": "TESTKEY"},
    )
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 3, combined
    assert "[NETWORK ERROR]" in proc.stderr
    assert f"http://127.0.0.1:{port}" in proc.stderr
    assert "Traceback" not in combined
    assert "urllib.error.URLError" not in combined


def test_publish_network_error_exits_3_cleanly(tmp_path):
    # F2 for the publish path: live upload to an unreachable host exits 3 cleanly.
    port = _dead_port()
    _fake_artifact(tmp_path)
    proc = _run_cli(
        ["publish", "--slug", "roman-concrete", "--live", "--api-base", f"http://127.0.0.1:{port}"],
        {"YOUTUBE_OAUTH_TOKEN": "ya29.dummy-token", "SHORTFORM_ARTIFACTS_DIR": str(tmp_path)},
    )
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 3, combined
    assert "[NETWORK ERROR]" in proc.stderr
    assert f"http://127.0.0.1:{port}" in proc.stderr
    assert "Traceback" not in combined


# --------------------------------------------------------------------------- #
# Mock server (spawned as a subprocess, real HTTP)
# --------------------------------------------------------------------------- #

@pytest.fixture()
def mock_server(tmp_path):
    transcript = tmp_path / "transcript.log"
    port = 8790
    proc = subprocess.Popen(
        [
            sys.executable,
            str(REPO / "mocks" / "youtube_mock.py"),
            "--port", str(port),
            "--transcript", str(transcript),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    # wait for the socket to accept
    for _ in range(50):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/youtube/v3/videos?id=X&key=K", timeout=1)
            break
        except Exception:
            time.sleep(0.1)
    yield f"http://127.0.0.1:{port}", transcript
    proc.terminate()
    proc.wait(timeout=5)


def test_mock_resumable_roundtrip(mock_server):
    base, transcript = mock_server
    # initiate
    req = urllib.request.Request(
        f"{base}/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        data=b'{"snippet":{"title":"T"},"status":{"privacyStatus":"private"}}',
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer test-token",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": "11",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 200
        location = resp.headers["Location"]
    # upload bytes
    put = urllib.request.Request(location, data=b"hello world", method="PUT",
                                 headers={"Content-Type": "video/mp4"})
    with urllib.request.urlopen(put, timeout=5) as resp:
        resource = json.loads(resp.read())
    assert resource["id"] == "MOCKID123"
    # measure
    with urllib.request.urlopen(f"{base}/youtube/v3/videos?part=snippet,statistics&id=MOCKID123&key=K", timeout=5) as resp:
        listing = json.loads(resp.read())
    assert listing["items"][0]["statistics"]["viewCount"] == "12874"
    # transcript captured and token redacted
    logged = transcript.read_text()
    assert "POST /upload/youtube/v3/videos?uploadType=resumable" in logged
    assert "RESPONSE 200" in logged
    assert "test-token" not in logged
