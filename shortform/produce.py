"""``shortform produce`` - render a 9:16 short video from an original script.

Pipeline (all assets are generated locally; nothing is downloaded):

    content/<slug>/script.json
        -> original Pillow graphics per scene (solid bg + geometry + type)
        -> TTS voiceover per scene (espeak-ng by default, $TTS_CMD overridable)
        -> per-scene audio padded to the scene ``hold`` so duration is exact
        -> SRT captions from the narration
        -> 1080x1920 H.264 yuv420p video + AAC 48 kHz stereo audio
        -> 2-pass loudnorm to -14 LUFS integrated / -1.5 dBTP
        -> title.txt, description.txt, metadata.json, captions.srt, provenance.json
"""

from __future__ import annotations

import math
import os
import shlex
import time
from pathlib import Path
from typing import Any

from . import store, util
from .util import Provenance

SRT_TS = "%02d:%02d:%02d,%03d"


# --------------------------------------------------------------------------- #
# Script handling
# --------------------------------------------------------------------------- #

def load_script(script_path: Path) -> dict[str, Any]:
    script = util.read_json(script_path)
    if "narration" not in script or not script["narration"]:
        raise ValueError(f"script {script_path} has no narration scenes")
    for i, scene in enumerate(script["narration"], start=1):
        for key in ("scene", "say", "onscreen", "hold"):
            if key not in scene:
                raise ValueError(f"scene {i} missing required key {key!r}")
    return script


def scene_durations(script: dict[str, Any], seconds: float | None) -> list[float]:
    holds = [float(s["hold"]) for s in script["narration"]]
    if seconds is None:
        return holds
    total = sum(holds)
    if total <= 0:
        raise ValueError("sum of scene holds must be > 0")
    factor = float(seconds) / total
    return [round(h * factor, 3) for h in holds]


# --------------------------------------------------------------------------- #
# Original graphics
# --------------------------------------------------------------------------- #

_FONT_CANDIDATES_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
]
_FONT_CANDIDATES_REG = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
]

PALETTES = [
    ((15, 23, 42), (51, 65, 85), (250, 204, 21), (248, 250, 252)),
    ((30, 27, 75), (67, 56, 202), (56, 189, 248), (238, 242, 255)),
    ((69, 26, 3), (180, 83, 9), (253, 224, 71), (255, 251, 235)),
    ((6, 78, 59), (16, 185, 129), (253, 224, 71), (236, 253, 245)),
    ((76, 5, 25), (190, 24, 93), (251, 191, 36), (255, 241, 242)),
    ((12, 74, 110), (14, 165, 233), (250, 204, 21), (240, 249, 255)),
]


def _load_font(size: int, bold: bool = True):
    from PIL import ImageFont

    for candidate in (_FONT_CANDIDATES_BOLD if bold else _FONT_CANDIDATES_REG):
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def _wrap(draw, text: str, font, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        width = draw.textlength(trial, font=font)
        if width <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _gradient(size, top, bottom):
    from PIL import Image, ImageDraw

    width, height = size
    base = Image.new("RGB", size, top)
    draw = ImageDraw.Draw(base)
    for y in range(height):
        t = y / max(1, height - 1)
        color = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        draw.line([(0, y), (width, y)], fill=color)
    return base


def render_graphic(scene: dict[str, Any], out_png: Path, topic: str, index: int,
                   total: int) -> None:
    """Draw one fully original 1080x1920 still using only Pillow primitives."""
    from PIL import Image, ImageDraw

    W, H = 1080, 1920
    bg1, bg2, accent, fg = PALETTES[(index - 1) % len(PALETTES)]
    img = _gradient((W, H), bg1, bg2)

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)

    # Original geometry: translucent diagonal bands.
    for i in range(-2, 9):
        x = i * 190
        od.polygon(
            [(x, 0), (x + 90, 0), (x + 90 - 420, H), (x - 420, H)],
            fill=(255, 255, 255, 14),
        )
    # Original geometry: concentric rings (a nod to Roman arches, drawn here).
    cx, cy = W // 2, 560
    for r in range(120, 561, 70):
        od.ellipse(
            [cx - r, cy - r, cx + r, cy + r],
            outline=accent + (46,),
            width=6,
        )
    # Angle ticks.
    for deg in range(0, 360, 15):
        rad = math.radians(deg)
        x1 = cx + int(300 * math.cos(rad))
        y1 = cy + int(300 * math.sin(rad))
        x2 = cx + int(360 * math.cos(rad))
        y2 = cy + int(360 * math.sin(rad))
        od.line([(x1, y1), (x2, y2)], fill=accent + (90,), width=4)

    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    # Scene counter badge is laid out first so the top label can avoid it.
    badge_font = _load_font(40, bold=True)
    badge = f"{index:02d} / {total:02d}"
    bw = draw.textlength(badge, font=badge_font)

    # Top label: shrink (then truncate) so it never runs under the badge.
    label = topic.upper()
    label_size = 46
    label_font = _load_font(label_size, bold=True)
    label_max = W - 72 - (bw + 48 + 40) - 72
    while label_size > 26 and draw.textlength(label, font=label_font) > label_max:
        label_size -= 2
        label_font = _load_font(label_size, bold=True)
    while label and draw.textlength(label + "\u2026", font=label_font) > label_max:
        label = label[:-1]
    if label != topic.upper():
        label = label.rstrip() + "\u2026"
    draw.text((72, 92), label, font=label_font, fill=accent)

    draw.rounded_rectangle(
        [W - 72 - bw - 48, 76, W - 72, 148], radius=36, fill=accent
    )
    draw.text((W - 72 - bw - 24, 88), badge, font=badge_font, fill=bg1)

    # Big on-screen phrase (the scene's headline).
    head_font = _load_font(118, bold=True)
    lines = _wrap(draw, str(scene["onscreen"]), head_font, W - 200)
    line_h = 138
    block_h = line_h * len(lines)
    y = cy + 340
    for line in lines:
        lw = draw.textlength(line, font=head_font)
        # subtle drop shadow then the text itself
        draw.text(((W - lw) / 2 + 5, y + 5), line, font=head_font, fill=(0, 0, 0))
        draw.text(((W - lw) / 2, y), line, font=head_font, fill=fg)
        y += line_h

    # Rule under the headline.
    draw.rectangle([W // 2 - 160, y + 40, W // 2 + 160, y + 52], fill=accent)

    # Footer provenance line - makes the "original, generated" claim legible.
    foot_font = _load_font(34, bold=False)
    footer = "ORIGINAL GRAPHIC - GENERATED BY SHORTFORM-STUDIO"
    fw = draw.textlength(footer, font=foot_font)
    draw.text(((W - fw) / 2, H - 150), footer, font=foot_font, fill=(210, 210, 210))

    util.ensure_dir(out_png.parent)
    img.save(out_png, format="PNG")


# --------------------------------------------------------------------------- #
# TTS + audio
# --------------------------------------------------------------------------- #

DEFAULT_TTS_CMD = "espeak-ng -v en-us -s 155 -w {out} {text}"


def tts_text(text: str, out_wav: Path, provenance: Provenance) -> None:
    template = os.environ.get("TTS_CMD", DEFAULT_TTS_CMD)
    command = template.replace("{out}", shlex.quote(str(out_wav))).replace(
        "{text}", shlex.quote(text)
    )
    proc = util.run_shell(command, provenance=provenance, check=False)
    if proc.returncode != 0 or not out_wav.exists():
        raise RuntimeError(
            "TTS failed. Set $TTS_CMD to a compatible command using {out} and {text}.\n"
            f"command: {command}\n"
            f"stderr: {proc.stderr.decode('utf-8', 'replace')[-2000:]}"
        )


def pad_audio(src: Path, dst: Path, duration: float, provenance: Provenance) -> None:
    util.run_cmd(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(src),
            "-af", "apad",
            "-t", f"{duration:.3f}",
            "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le",
            str(dst),
        ],
        provenance=provenance,
    )


def concat_audio(parts: list[Path], dst: Path, provenance: Provenance, tmp: Path) -> None:
    list_file = tmp / "audio_concat.txt"
    util.write_text(
        list_file,
        "".join(f"file '{p.as_posix()}'\n" for p in parts),
    )
    util.run_cmd(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", str(list_file),
            "-c", "copy", str(dst),
        ],
        provenance=provenance,
    )


# --------------------------------------------------------------------------- #
# Captions
# --------------------------------------------------------------------------- #

def _ts(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return SRT_TS % (h, m, s, ms)


def build_srt(scenes: list[dict[str, Any]], durations: list[float]) -> str:
    lines: list[str] = []
    t = 0.0
    for i, (scene, dur) in enumerate(zip(scenes, durations), start=1):
        lines.append(str(i))
        lines.append(f"{_ts(t)} --> {_ts(t + dur)}")
        lines.append(str(scene["say"]).strip())
        lines.append("")
        t += dur
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Description / metadata
# --------------------------------------------------------------------------- #

DISCLOSURE_SENTENCE = (
    "This video contains synthetic media: the narration is machine-generated and "
    "the visuals are computer-generated by shortform-studio. No third-party "
    "footage, music, or images were used."
)
AFFILIATE_DISCLOSURE = (
    "Affiliate disclosure: links in this description may earn a commission."
)


def build_description(script: dict[str, Any], has_affiliate: bool = False) -> str:
    title = script["title"]
    summary = script.get(
        "summary",
        "An original short explainer built by the shortform-studio pipeline.",
    )
    hashtags = script.get("hashtags", ["#Shorts"])
    tags = " ".join(hashtags)
    parts = [title, "", summary.strip(), "", DISCLOSURE_SENTENCE]
    if has_affiliate:
        parts += ["", AFFILIATE_DISCLOSURE]
    parts += ["", tags]
    return "\n".join(parts).strip() + "\n"


def build_metadata(script: dict[str, Any], description: str) -> dict[str, Any]:
    return {
        "snippet": {
            "title": script["title"],
            "description": description,
            "tags": list(script.get("tags", [])),
            "categoryId": str(script.get("categoryId", "27")),
        },
        "status": {
            "privacyStatus": "private",
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True,
            "license": "youtube",
            "embeddable": True,
        },
        "selfDeclaredMadeForKids": False,
        "syntheticMediaDisclosure": True,
        "disclosureSentence": DISCLOSURE_SENTENCE,
    }


# --------------------------------------------------------------------------- #
# Top-level produce
# --------------------------------------------------------------------------- #

def produce(
    slug: str,
    seconds: float | None = None,
    root: Path | None = None,
    artifacts_root: Path | None = None,
) -> dict[str, Any]:
    # ``root`` is the SOURCE repository root (content/<slug>/script.json);
    # ``artifacts_root`` is an explicit data-root override for tests. Output
    # always lands under the external data root, never in the repo tree.
    root = root or util.repo_root()
    content = util.content_dir(slug, root)
    script_path = content / "script.json"
    if not script_path.exists():
        raise FileNotFoundError(f"no script at {script_path}")

    out = util.out_dir(slug, artifacts_root)
    tmp = util.ensure_dir(out / "tmp")
    graphics_dir = util.ensure_dir(out / "graphics")
    audio_dir = util.ensure_dir(out / "audio")

    tools = util.require_tools(["ffmpeg", "ffprobe"])
    prov = Provenance(slug=slug, generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    prov.tools = tools
    prov.tools["tts_cmd"] = os.environ.get("TTS_CMD", DEFAULT_TTS_CMD)

    script = load_script(script_path)
    prov.add_input("script", script_path, text=script_path.read_text("utf-8"))

    scenes = script["narration"]
    durations = scene_durations(script, seconds)
    total = sum(durations)

    # 1) original graphics
    for i, scene in enumerate(scenes, start=1):
        png = graphics_dir / f"scene_{i:02d}.png"
        render_graphic(
            scene, png, script.get("label") or script.get("topic", slug), i, len(scenes)
        )
        prov.add_output(f"graphic_{i:02d}", png)

    # 2) TTS + per-scene padded audio
    padded: list[Path] = []
    for i, (scene, dur) in enumerate(zip(scenes, durations), start=1):
        raw = audio_dir / f"scene_{i:02d}_raw.wav"
        tts_text(str(scene["say"]), raw, prov)
        prov.add_output(f"tts_raw_{i:02d}", raw)
        pad = audio_dir / f"scene_{i:02d}.wav"
        pad_audio(raw, pad, dur, prov)
        padded.append(pad)

    voice = audio_dir / "voice.wav"
    concat_audio(padded, voice, prov, tmp)

    # 3) two-pass loudnorm to -14 LUFS / -1.5 dBTP
    measured = util.loudnorm_measure(voice)
    prov.add_output("voice_raw", voice)
    voice_norm = audio_dir / "voice_normalized.wav"
    util.loudnorm_second_pass(voice, voice_norm, measured)
    prov.add_output("voice_normalized", voice_norm)

    # 4) captions
    srt = out / "captions.srt"
    util.write_text(srt, build_srt(scenes, durations))
    prov.add_output("captions", srt)

    # 5) silent video from the stills. Each still is encoded on its own (cheap,
    #    low memory) and the segments are stream-copied together with the
    #    concat demuxer; a single six-input filtergraph OOM-killed on 2 vCPU.
    silent = tmp / "video_silent.mp4"
    segment_paths: list[Path] = []
    for i, dur in enumerate(durations, start=1):
        segment = tmp / f"scene_{i:02d}.mp4"
        util.run_cmd(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-loop", "1", "-framerate", "30", "-t", f"{dur:.3f}",
                "-i", str(graphics_dir / f"scene_{i:02d}.png"),
                "-vf", "setsar=1",
                # Lean encode: the production host runs in a ~1 GiB cgroup, so
                # we avoid x264's memory-hungry presets and extra thread buffers.
                "-c:v", "libx264", "-preset", "ultrafast", "-threads", "1", "-crf", "23",
                "-pix_fmt", "yuv420p", "-r", "30", "-an",
                str(segment),
            ],
            provenance=prov,
        )
        segment_paths.append(segment)
    concat_list = tmp / "video_concat.txt"
    util.write_text(
        concat_list, "".join(f"file '{p.as_posix()}'\n" for p in segment_paths)
    )
    util.run_cmd(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", str(concat_list),
            "-c", "copy", str(silent),
        ],
        provenance=prov,
    )

    # 6) mux video + normalized audio + soft captions
    video = out / "video.mp4"
    util.run_cmd(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(silent),
            "-i", str(voice_norm),
            "-i", str(srt),
            "-map", "0:v:0", "-map", "1:a:0", "-map", "2:s:0",
            "-c:v", "copy",
            "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "192k",
            "-c:s", "mov_text",
            "-t", f"{total:.3f}",
            "-movflags", "+faststart",
            str(video),
        ],
        provenance=prov,
    )
    prov.add_output("video", video)

    # 7) text deliverables
    title_path = out / "title.txt"
    util.write_text(title_path, script["title"].strip() + "\n")
    prov.add_output("title", title_path)

    description = build_description(script)
    desc_path = out / "description.txt"
    util.write_text(desc_path, description)
    prov.add_output("description", desc_path)

    metadata = build_metadata(script, description)
    meta_path = out / "metadata.json"
    util.write_json(meta_path, metadata)
    prov.add_output("metadata", meta_path)

    # 8) provenance (last, so it can hash everything above). The audio/ and
    # tmp/ intermediates are removed below after their hashes were captured.
    prov_data = prov.as_dict()
    prov_data["intermediates_note"] = (
        "audio/ and tmp/ intermediates are deleted after muxing to keep the "
        "artifact directory small; the hashes above were computed while they "
        "existed."
    )
    prov_path = out / "provenance.json"
    util.write_json(prov_path, prov_data)

    # Clean up the scratch directory; keep the tree tidy for commits.
    for scratch in (tmp, audio_dir):
        if scratch.exists():
            for child in sorted(scratch.rglob("*"), reverse=True):
                if child.is_file():
                    child.unlink()
                elif child.is_dir():
                    child.rmdir()
            scratch.rmdir()

    # 9) append a render event to the store (external data root; never the repo).
    store.record_render(
        slug,
        out,
        bytes=video.stat().st_size,
        sha256=util.sha256_file(video),
        duration_s=total,
        resolution="1080x1920",
        status="rendered",
    )

    return {
        "slug": slug,
        "video": str(video),
        "artifact_dir": str(out),
        "duration_s": total,
        "scenes": len(scenes),
        "loudnorm_measured": measured,
        "provenance": str(prov_path),
    }
