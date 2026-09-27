# OmniStack ShortForm Studio

A minimal, policy-compliant short-form video production line. It renders a
**1080x1920 (9:16)** short from an **original** script, validates it against the
platform/technical delivery contract, and can upload and measure it through the
YouTube Data API v3 — or entirely offline against a bundled mock when no
platform credential exists.

Everything is generated locally. **No third-party footage, music, or images are
downloaded or embedded.** The narration is written for each video and the
graphics are drawn by this pipeline with Pillow primitives.

```
script.json -> original Pillow graphics -> espeak-ng TTS -> SRT captions
            -> H.264 yuv420p + AAC 48 kHz stereo -> 2-pass loudnorm -14 LUFS
            -> title.txt / description.txt / metadata.json / provenance.json
            -> qa-report.json -> YouTube resumable upload -> metrics snapshots
```

---

## Quickstart

```bash
# system tools (Debian/Ubuntu)
apt-get update && apt-get install -y ffmpeg espeak-ng python3-pip python3-pillow python3-pytest

python3 -m shortform --help

# 1) produce the first real video (30-45 s)
python3 -m shortform produce --slug roman-concrete

# 2) validate it (exit 0 = PASS, 1 = FAIL)
python3 -m shortform qa --slug roman-concrete

# 3) see exactly what a live upload would send (sends nothing)
python3 -m shortform publish --slug roman-concrete --dry-run

# 4) full offline end-to-end proof, including the mock upload + measure
bash scripts/selftest.sh
```

Dependencies: Python 3.9+ stdlib, `ffmpeg`/`ffprobe`, `espeak-ng` (or any TTS
command via `$TTS_CMD`), and `Pillow`. `requests` is *not* required — the network
calls use `urllib` from the standard library. `pytest` is only needed for the
unit tests.

---

## Commands

### `produce --slug <slug> [--seconds N]`

Renders `out/<slug>/video.mp4` from `content/<slug>/script.json`:

```json
{
  "topic": "How Roman concrete survived 2000 years",
  "label": "ROMAN CONCRETE",
  "title": "How Roman Concrete Survived 2000 Years",
  "summary": "one or two original sentences for the description",
  "tags": ["roman concrete", "engineering"],
  "hashtags": ["#Shorts", "#RomanConcrete"],
  "narration": [
    {"scene": 1, "say": "original narration line", "onscreen": "BIG PHRASE", "hold": 6.0}
  ]
}
```

* graphics: one original 1080x1920 PNG per scene (gradient + geometry + type);
* TTS: `espeak-ng` by default, overridable with `$TTS_CMD` (placeholders
  `{out}` and `{text}` are shell-quoted automatically);
* captions: `captions.srt`, also muxed as a soft `mov_text` subtitle track;
* audio: 48 kHz stereo AAC, integrated loudness normalised to **-14 LUFS**
  (true peak limited) with a 2-pass `loudnorm`;
* `--seconds N` proportionally rescales the scene `hold`s so the video is N
  seconds long (still must land in the 15-60 s delivery window).

Also written: `title.txt`, `description.txt` (title + `#Shorts` + synthetic-media
disclosure + optional affiliate disclosure + hashtags), `metadata.json`
(YouTube `snippet` + `status`, `containsSyntheticMedia`, and
`selfDeclaredMadeForKids=false`), `provenance.json` (inputs, every command and
output hashes).

### `qa --slug <slug>`

Writes `out/<slug>/qa-report.json`, exits **0 on PASS / 1 on FAIL**. Checks:
container duration 15-60 s; video `h264` / `yuv420p` / 1080x1920 / SAR 1:1;
audio `aac` present; integrated loudness -14 ±1 LUFS and true peak ≤ -1 dBTP;
title ≤ 100 chars; description ≤ 5000 chars; `#Shorts` present; synthetic-media
disclosure sentence present; affiliate disclosure present when an affiliate URL
is present; all URLs well-formed; metadata `selfDeclaredMadeForKids=false`.

### `publish --slug <slug> [--dry-run | --live] [--privacy private|unlisted|public]`

YouTube Data API v3 **resumable upload**:

```
POST https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status
Authorization: Bearer $YOUTUBE_OAUTH_TOKEN
X-Upload-Content-Type: video/mp4
X-Upload-Content-Length: <bytes>
{"snippet": {...}, "status": {...}}

PUT <Location from step 1>   # raw video bytes
```

* `--dry-run` (default) prints the exact method/URL/headers/body and **sends
  nothing**.
* Default `privacyStatus=private` — a human approves before anything is public.
* Missing `$YOUTUBE_OAUTH_TOKEN` on `--live` prints an exact human-handover
  message and exits **2**. The pipeline **never fakes an upload**.
* `--api-base <url>` points the same code at the local mock.

### `measure --video-id <ID> [--mock]`

```
GET /youtube/v3/videos?part=snippet,statistics&id=<ID>&key=$YOUTUBE_API_KEY
```

Appends a timestamped snapshot to `data/metrics/<id>.jsonl` and prints
views/likes/comments plus a clearly labelled **view-through placeholder**
(the real view-through rate needs the YouTube Analytics API with OAuth).
`--mock` (or `--api-base`) uses the local mock. Missing `$YOUTUBE_API_KEY`
against the real host prints a handover message and exits 2.

---

## The mock (`mocks/youtube_mock.py`)

A stdlib `http.server` implementing the three endpoints above. It logs every
request line, header and body size to `mocks/transcript.log` (Authorization is
redacted). This is how the publish/measure legs are verified **without** a
Google credential — there is no Google sandbox for `videos.insert`.

```bash
python3 mocks/youtube_mock.py --port 8787 --transcript mocks/transcript.log
```

---

## Self-test

`scripts/selftest.sh` runs one full chain and leaves raw evidence under
`out/selftest/`:

```
produce -> qa -> publish --dry-run -> start mock
        -> publish --live --api-base http://127.0.0.1:8787
        -> measure --mock -> stop mock
```

Each step prints `PASS`/`FAIL`; the script exits non-zero if any step failed.
Raw artifacts: `out/selftest/*.log`, `out/selftest/transcript.log`,
`out/selftest/qa-report.json`, `out/selftest/ffprobe.json`, `out/selftest/video.mp4`.

Unit tests:

```bash
python3 -m pytest tests/ -v
```

---

## Policy rules implemented

The plan named YouTube's *inauthentic content* policy as the wall. This pipeline
enforces the corresponding rules mechanically:

| Rule | Where it is enforced |
| --- | --- |
| Original narration | Written in `content/<slug>/script.json`; no scraped text |
| Original graphics | Drawn by Pillow in `shortform/produce.py`; no external assets |
| Synthetic-media disclosure | `DISCLOSURE_SENTENCE` in `description.txt` + `containsSyntheticMedia` in `metadata.json`; checked by `qa` |
| No copyrighted media | The pipeline downloads nothing; only generated PNGs/audio |
| Correct metadata | `qa` checks title length, `#Shorts`, disclosure, URL format |
| Kids flag | `selfDeclaredMadeForKids=false` in metadata; checked by `qa` |
| Affiliate disclosure | Injected and required whenever an affiliate URL is present |
| Private by default | `publish` defaults to `privacyStatus=private` |

## Human handover list

These steps cannot be automated safely and need a human:

1. **OAuth token** for upload: create a Google Cloud project, enable YouTube Data
   API v3, configure the OAuth consent screen, create a Desktop OAuth client,
   run the OAuth flow, then `export YOUTUBE_OAUTH_TOKEN=...` (see the exact
   message `publish --live` prints when the token is missing).
2. **API key** for real measurement: enable YouTube Data API v3, create an API
   key, `export YOUTUBE_API_KEY=...`.
3. **Review + publish**: the default is `private`; a human reviews the video,
   thumbnail, disclosure and kids flag in YouTube Studio before changing privacy.
4. **Analytics**: the real view-through/retention numbers require the YouTube
   Analytics API (OAuth scope), which is out of scope for this MVP; `measure`
   emits a labelled placeholder instead.

No credential is ever written to a file or committed. Credentials are read from
the environment only.

---

## Layout

```
shortform/            package (produce, qa, publish, measure, cli)
content/<slug>/       original scripts
mocks/youtube_mock.py local API mock + transcript.log
tests/                pytest suite
scripts/selftest.sh   one-shot end-to-end proof
docs/RUNBOOK.md       ordered operator steps
out/<slug>/           produced artifacts (video, captions, metadata, provenance)
data/metrics/         appended measurement snapshots
```

MIT licensed — see `LICENSE`.
