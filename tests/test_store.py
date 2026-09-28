"""Tests for the external artifact store: path resolution, SQLite, migration.

The suite must never touch the real data root; ``tests/conftest.py`` points
``SHORTFORM_ARTIFACTS_DIR`` at a throwaway directory for the whole session and
each test that needs isolation overrides it with ``monkeypatch``.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from shortform import paths, produce, store  # noqa: E402


# --------------------------------------------------------------------------- #
# Path resolution
# --------------------------------------------------------------------------- #

def test_data_root_override_and_omni_semantics(monkeypatch, tmp_path):
    monkeypatch.setenv("SHORTFORM_ARTIFACTS_DIR", str(tmp_path / "override"))
    assert paths.data_root() == tmp_path / "override"

    monkeypatch.delenv("SHORTFORM_ARTIFACTS_DIR", raising=False)
    monkeypatch.setenv("OMNI_DIR", str(tmp_path / "omni"))
    assert paths.data_root() == (
        tmp_path / "omni" / "data" / "artifacts" / "shortform-studio"
    )

    # An OMNI_DIR already ending in /data must not gain a second data segment.
    monkeypatch.setenv("OMNI_DIR", str(tmp_path / "omni" / "data"))
    assert paths.data_root() == (
        tmp_path / "omni" / "data" / "artifacts" / "shortform-studio"
    )


def test_default_data_root_is_never_inside_the_repo(monkeypatch):
    monkeypatch.delenv("SHORTFORM_ARTIFACTS_DIR", raising=False)
    monkeypatch.delenv("OMNI_DIR", raising=False)
    root = paths.data_root()
    assert root == Path("/opt/omni/data/artifacts/shortform-studio")
    assert not str(root).startswith(str(REPO))


def test_artifact_and_db_paths_are_external(monkeypatch, tmp_path):
    monkeypatch.setenv("SHORTFORM_ARTIFACTS_DIR", str(tmp_path))
    assert paths.artifact_dir("roman-concrete") == tmp_path / "roman-concrete"
    assert paths.db_path() == tmp_path / "studio.db"
    assert not str(paths.db_path()).startswith(str(REPO))


def test_locator_round_trip(monkeypatch, tmp_path):
    monkeypatch.setenv("SHORTFORM_ARTIFACTS_DIR", str(tmp_path))
    locator = paths.locator_for("roman-concrete")
    assert locator == "data://shortform-studio/roman-concrete/video.mp4"
    assert paths.resolve_locator(locator) == tmp_path / "roman-concrete" / "video.mp4"
    with pytest.raises(ValueError):
        # A repo-relative path must never be accepted as a locator.
        paths.resolve_locator("out/roman-concrete/video.mp4")


# --------------------------------------------------------------------------- #
# Migrate + verify round trip
# --------------------------------------------------------------------------- #

def _make_legacy_tree(tmp_path, slug="fixture-video"):
    src_out = tmp_path / "src_out"
    src_content = tmp_path / "src_content"
    (src_content / slug).mkdir(parents=True)
    (src_content / slug / "script.json").write_text(
        json.dumps(
            {
                "topic": "Fixture",
                "label": "FIXTURE",
                "title": "Fixture video",
                "summary": "A fixture.",
                "narration": [
                    {"scene": 1, "say": "One.", "onscreen": "ONE", "hold": 5.0}
                ],
            }
        ),
        encoding="utf-8",
    )
    (src_out / slug).mkdir(parents=True)
    (src_out / slug / "video.mp4").write_bytes(b"fixture-video-bytes" * 100)
    (src_out / slug / "qa-report.json").write_text(
        json.dumps(
            {
                "slug": slug,
                "pass": True,
                "checks": [
                    {"check": "video_exists", "passed": True, "detail": "ok"},
                    {"check": "duration_15_60s", "passed": True, "detail": "15s"},
                ],
            }
        ),
        encoding="utf-8",
    )
    return src_out, src_content


def test_migrate_and_verify_round_trip(monkeypatch, tmp_path):
    monkeypatch.setenv("SHORTFORM_ARTIFACTS_DIR", str(tmp_path / "data"))
    src_out, src_content = _make_legacy_tree(tmp_path)

    result = store.migrate_legacy_out(source_root=src_out, content_root=src_content)
    assert result["examined"] == 2
    assert result["inserted"] == 2
    assert result["results"][0]["slug"] == "fixture-video"
    assert result["results"][0]["bytes"] == 1900

    dest = tmp_path / "data" / "fixture-video"
    assert (dest / "video.mp4").read_bytes() == (
        src_out / "fixture-video" / "video.mp4"
    ).read_bytes()

    verify = store.verify_store()
    assert verify["match"] is True
    assert verify["renders"] == 1
    assert verify["checks"][0]["qa"] == "2/2"

    # Idempotent: a second run copies nothing and inserts no second render row.
    again = store.migrate_legacy_out(source_root=src_out, content_root=src_content)
    assert again["inserted"] == 0
    assert again["results"][0]["already_migrated"] is True
    assert store.verify_store()["renders"] == 1


def test_verify_flags_a_corrupted_artifact(monkeypatch, tmp_path):
    monkeypatch.setenv("SHORTFORM_ARTIFACTS_DIR", str(tmp_path / "data"))
    src_out, src_content = _make_legacy_tree(tmp_path)
    store.migrate_legacy_out(source_root=src_out, content_root=src_content)

    (tmp_path / "data" / "fixture-video" / "video.mp4").write_bytes(b"corrupted")
    result = store.verify_store()
    assert result["match"] is False
    assert result["checks"][0]["match"] is False


def test_renders_table_is_append_only(monkeypatch, tmp_path):
    monkeypatch.setenv("SHORTFORM_ARTIFACTS_DIR", str(tmp_path))
    render_id = store.record_render(
        "x", tmp_path / "x", bytes=1, sha256="a" * 64, status="rendered"
    )
    conn = store.connect()
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE renders SET status = 'edited' WHERE id = ?", (render_id,))
        conn.rollback()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM renders WHERE id = ?", (render_id,))
        conn.rollback()
    finally:
        conn.close()


def test_catalog_is_seeded_from_the_source_fixture(monkeypatch, tmp_path):
    monkeypatch.setenv("SHORTFORM_ARTIFACTS_DIR", str(tmp_path))
    rows = store.catalog_rows()
    slugs = {row["slug"] for row in rows}
    assert slugs == {
        "video-pack-roman-concrete",
        "shorts-bundle-3",
        "caption-kit",
        "studio-monthly-4",
    }
    # Reading again uses the store (already seeded), so the counts are stable.
    assert len(store.catalog_rows()) == len(rows)


# --------------------------------------------------------------------------- #
# Storefront manifest uses a data locator, never a repo path
# --------------------------------------------------------------------------- #

def test_storefront_manifest_uses_a_data_locator():
    catalog = json.loads((REPO / "storefront" / "catalog.json").read_text())
    artifact = catalog["items"][0]["artifact"]
    assert artifact["path"] == "data://shortform-studio/roman-concrete/video.mp4"
    assert paths.resolve_locator(artifact["path"]).name == "video.mp4"

    worker = (REPO / "storefront" / "worker" / "worker.js").read_text()
    assert "out/roman-concrete/video.mp4" not in worker
    assert "data://shortform-studio/roman-concrete/video.mp4" in worker


# --------------------------------------------------------------------------- #
# produce writes outside the repository
# --------------------------------------------------------------------------- #

def _can_encode() -> bool:
    return (
        shutil.which("ffmpeg") is not None
        and shutil.which("ffprobe") is not None
        and shutil.which("espeak-ng") is not None
    )


@pytest.mark.skipif(not _can_encode(), reason="ffmpeg/espeak-ng not installed")
def test_produce_writes_outside_the_repo(tmp_path):
    result = produce.produce("demo-short", artifacts_root=tmp_path)
    video = Path(result["video"])
    assert video.exists()
    assert video.parent == tmp_path / "demo-short"
    assert not str(video).startswith(str(REPO))
    assert not (REPO / "out" / "demo-short").exists()
    # A render event was recorded in the external store, not the repo.
    assert store.verify_store()["renders"] >= 1


def test_produce_cli_defaults_outside_the_repo(monkeypatch, tmp_path):
    # No encode: assert the CLI's resolved paths are external for a temp root.
    monkeypatch.setenv("SHORTFORM_ARTIFACTS_DIR", str(tmp_path))
    proc = subprocess.run(
        [sys.executable, "-m", "shortform", "store", "path"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        env={**os.environ, "SHORTFORM_ARTIFACTS_DIR": str(tmp_path)},
        timeout=30,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert str(tmp_path) in proc.stdout
    assert str(REPO / "out") not in proc.stdout
