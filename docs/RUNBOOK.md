# RUNBOOK — shortform-studio

Ordered operator steps with the exact commands. Assumes a Debian/Ubuntu host,
`/opt/workspace/shortform-studio` as the working tree, and network access for the
initial package install only. The pipeline itself downloads no media.

## 0. One-time environment

```bash
apt-get update
apt-get install -y ffmpeg espeak-ng python3-pip python3-requests python3-pil python3-pytest
which ffmpeg ffprobe espeak-ng
python3 -c "import PIL; print('Pillow', PIL.__version__)"
```

`requests` is optional; the code uses stdlib `urllib`. Pillow is required for
graphics. `espeak-ng` is the default TTS.

## 1. Produce the 9:16 video

```bash
cd /opt/workspace/shortform-studio
python3 -m shortform produce --slug roman-concrete
```

Outputs under `out/roman-concrete/`: `video.mp4`, `captions.srt`, `title.txt`,
`description.txt`, `metadata.json`, `provenance.json`, `graphics/scene_*.png`.

Optional exact length (must stay inside 15–60 s):

```bash
python3 -m shortform produce --slug roman-concrete --seconds 40
```

Swap in a premium voice later without touching code:

```bash
export TTS_CMD='piper --model en_US-amy --output_file {out} < <(echo {text})'
```

`{out}` and `{text}` are substituted with shell-safe quoting.

## 2. QA gate (must be PASS before anything is uploaded)

```bash
python3 -m shortform qa --slug roman-concrete
echo "exit=$?"          # 0 = PASS, 1 = FAIL
cat out/roman-concrete/qa-report.json
```

## 3. Inspect the exact upload request without sending it

```bash
python3 -m shortform publish --slug roman-concrete --dry-run
```

## 4. Offline end-to-end proof (no Google credential)

```bash
bash scripts/selftest.sh            # runs produce -> qa -> dry-run -> mock -> live -> measure
ls -la out/selftest/
cat out/selftest/transcript.log
```

Manual equivalent:

```bash
# terminal A
python3 mocks/youtube_mock.py --port 8787 --transcript mocks/transcript.log

# terminal B
YOUTUBE_OAUTH_TOKEN=mock-test-token \
  python3 -m shortform publish --slug roman-concrete --live --privacy private \
  --api-base http://127.0.0.1:8787

YOUTUBE_API_KEY=mock-key python3 -m shortform measure --video-id MOCKID123 --mock
cat data/metrics/MOCKID123.jsonl
```

## 5. Unit tests

```bash
python3 -m pytest tests/ -v
```

## 6. Real upload (human required)

```bash
export YOUTUBE_OAUTH_TOKEN="ya29.<access token with youtube.upload scope>"
python3 -m shortform publish --slug roman-concrete --live --privacy private
```

Then a human reviews the private video in YouTube Studio (title, thumbnail,
synthetic-media disclosure, kids flag) and only then flips privacy to
`unlisted`/`public`. Run without the token to see the full handover message;
the command exits 2 and sends nothing.

## 7. Real measurement (human required)

```bash
export YOUTUBE_API_KEY="AIza..."
python3 -m shortform measure --video-id <REAL_VIDEO_ID>
cat data/metrics/<REAL_VIDEO_ID>.jsonl
```

## 8. Commit (never commit credentials)

```bash
git status
git add shortform mocks tests scripts content docs README.md LICENSE .gitignore
git commit -m "feat: ..."
```

No command in this runbook writes a credential to disk. Keep tokens in the
environment only. Do not `git add` `mocks/transcript.log` if it ever contains a
real token; the mock redacts Authorization, and the pipeline never logs tokens.

## Troubleshooting

* `missing required tool(s): ffmpeg` — run step 0.
* `TTS failed` — check `espeak-ng` or set `$TTS_CMD`.
* QA fails on loudness — re-run `produce` (it re-measures and re-normalises);
  do not hand-edit the audio.
* `publish --live` exits 2 — the OAuth token is missing; see the printed handover.
* Mock port busy — `MOCK_PORT=8790 bash scripts/selftest.sh`.
