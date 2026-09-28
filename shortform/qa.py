"""``shortform qa`` - validate a produced video against the delivery contract.

Exits 0 on PASS and 1 on FAIL. The full machine-readable report is written to
``{data_root}/<slug>/qa-report.json`` (never the repo tree) regardless of the
outcome, so a failing run still leaves evidence. Each run also appends a QA
event to the SQLite store.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from . import store, util
from .produce import AFFILIATE_DISCLOSURE, DISCLOSURE_SENTENCE

URL_RE = re.compile(r"https?://[^\s<>\"')]+", re.I)
LOUDNESS_TARGET = -14.0
LOUDNESS_TOL = 1.0
TRUE_PEAK_MAX = -1.0

AFFILIATE_HINTS = (
    "amzn.to",
    "amazon.",
    "tag=",
    "affiliate",
    "ref=",
    "geni.us",
    "shareasale",
    "impact.com",
    "clickbank",
    "/go/",
)


def _check(results: list[dict[str, Any]], name: str, passed: bool, detail: str) -> None:
    results.append({"check": name, "passed": bool(passed), "detail": detail})


def _streams(probe: dict[str, Any]) -> tuple[dict, dict | None]:
    video = None
    audio = None
    for stream in probe.get("streams", []):
        if stream.get("codec_type") == "video" and video is None:
            video = stream
        if stream.get("codec_type") == "audio" and audio is None:
            audio = stream
    return video or {}, audio


def run_qa(
    slug: str,
    root: Path | None = None,
    artifacts_root: Path | None = None,
) -> tuple[dict[str, Any], int]:
    # ``root`` is the SOURCE repository root; ``artifacts_root`` is an explicit
    # data-root override for tests. Artifacts always resolve outside the repo.
    root = root or util.repo_root()
    out = util.out_dir(slug, artifacts_root)
    video = out / "video.mp4"
    title_path = out / "title.txt"
    desc_path = out / "description.txt"
    meta_path = out / "metadata.json"

    results: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "slug": slug,
        "video": str(video),
        "checks": results,
        "pass": False,
        "loudness": {},
    }

    if not video.exists():
        _check(results, "video_exists", False, f"missing {video}")
        report["pass"] = False
        util.write_json(out / "qa-report.json", report)
        return report, 1

    _check(results, "video_exists", True, str(video))

    probe = util.ffprobe_json(video)
    vstream, astream = _streams(probe)

    duration = float(probe.get("format", {}).get("duration") or 0.0)
    _check(
        results,
        "duration_15_60s",
        15.0 <= duration <= 60.0,
        f"duration={duration:.3f}s (required 15-60s)",
    )

    _check(
        results,
        "video_codec_h264",
        vstream.get("codec_name") == "h264",
        f"codec_name={vstream.get('codec_name')!r} (required h264)",
    )
    _check(
        results,
        "pixel_format_yuv420p",
        vstream.get("pix_fmt") == "yuv420p",
        f"pix_fmt={vstream.get('pix_fmt')!r} (required yuv420p)",
    )
    width, height = vstream.get("width"), vstream.get("height")
    _check(
        results,
        "resolution_1080x1920",
        width == 1080 and height == 1920,
        f"resolution={width}x{height} (required 1080x1920)",
    )
    sar = vstream.get("sample_aspect_ratio")
    _check(
        results,
        "sar_1_1",
        sar in ("1:1", "1/1"),
        f"sample_aspect_ratio={sar!r} (required 1:1)",
    )
    _check(
        results,
        "audio_aac",
        astream is not None and astream.get("codec_name") == "aac",
        f"audio codec={astream.get('codec_name') if astream else None!r} (required aac)",
    )

    # Loudness: integrated -14 +/-1 LUFS, true peak <= -1 dBTP.
    try:
        loud = util.measure_loudness(video)
        report["loudness"] = loud
        integrated = loud.get("integrated_lufs")
        peak = loud.get("true_peak_dbfs")
        _check(
            results,
            "integrated_loudness_-14_plusminus_1",
            integrated is not None and abs(integrated - LOUDNESS_TARGET) <= LOUDNESS_TOL,
            f"integrated={integrated} LUFS (required -14 +/-1)",
        )
        _check(
            results,
            "true_peak_le_-1_dbtp",
            peak is not None and peak <= TRUE_PEAK_MAX + 1e-6,
            f"true_peak={peak} dBTP (required <= {TRUE_PEAK_MAX})",
        )
    except Exception as exc:  # noqa: BLE001 - report the failure, do not crash
        _check(results, "integrated_loudness_-14_plusminus_1", False, f"measurement error: {exc}")
        _check(results, "true_peak_le_-1_dbtp", False, f"measurement error: {exc}")

    # Copy / policy checks.
    title = title_path.read_text("utf-8").strip() if title_path.exists() else ""
    description = desc_path.read_text("utf-8") if desc_path.exists() else ""
    _check(
        results,
        "title_le_100_chars",
        bool(title) and len(title) <= 100,
        f"title length={len(title)} (required 1-100)",
    )
    _check(
        results,
        "description_le_5000_chars",
        bool(description) and len(description) <= 5000,
        f"description length={len(description)} (required 1-5000)",
    )
    _check(
        results,
        "shorts_hashtag_present",
        "#Shorts" in description or "#shorts" in description,
        "#Shorts present in description" if "#Shorts" in description or "#shorts" in description
        else "#Shorts missing from description",
    )
    _check(
        results,
        "synthetic_media_disclosure",
        DISCLOSURE_SENTENCE in description,
        "AI/synthetic-media disclosure sentence present"
        if DISCLOSURE_SENTENCE in description
        else "AI/synthetic-media disclosure sentence missing",
    )

    urls = URL_RE.findall(description)
    malformed = []
    for url in urls:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            malformed.append(url)
    _check(
        results,
        "urls_well_formed",
        not malformed,
        "no malformed URLs" if not malformed else f"malformed URLs: {malformed}",
    )

    has_affiliate = any(hint in url.lower() for url in urls for hint in AFFILIATE_HINTS)
    _check(
        results,
        "affiliate_disclosure_when_needed",
        (not has_affiliate) or (AFFILIATE_DISCLOSURE in description),
        "affiliate link detected, disclosure present"
        if has_affiliate and AFFILIATE_DISCLOSURE in description
        else ("no affiliate link present" if not has_affiliate
              else "affiliate link present but disclosure missing"),
    )

    if meta_path.exists():
        meta = util.read_json(meta_path)
        kids = meta.get("status", {}).get("selfDeclaredMadeForKids", meta.get("selfDeclaredMadeForKids"))
        _check(
            results,
            "metadata_selfDeclaredMadeForKids_false",
            kids is False,
            f"selfDeclaredMadeForKids={kids!r} (required false)",
        )
        _check(
            results,
            "metadata_synthetic_disclosure_flag",
            bool(meta.get("syntheticMediaDisclosure") or meta.get("status", {}).get("containsSyntheticMedia")),
            "synthetic-media disclosure flag present in metadata",
        )
    else:
        _check(results, "metadata_selfDeclaredMadeForKids_false", False, f"missing {meta_path}")
        _check(results, "metadata_synthetic_disclosure_flag", False, f"missing {meta_path}")

    report["pass"] = all(c["passed"] for c in results)
    util.write_json(out / "qa-report.json", report)

    width, height = vstream.get("width"), vstream.get("height")
    store.record_qa(
        slug,
        report,
        out,
        bytes=video.stat().st_size,
        sha256=util.sha256_file(video),
        duration_s=duration,
        resolution="%sx%s" % (width, height) if width and height else None,
    )
    return report, 0 if report["pass"] else 1


def print_report(report: dict[str, Any]) -> None:
    for check in report["checks"]:
        mark = "PASS" if check["passed"] else "FAIL"
        print(f"[{mark}] {check['check']}: {check['detail']}")
    print("QA RESULT:", "PASS" if report["pass"] else "FAIL")
