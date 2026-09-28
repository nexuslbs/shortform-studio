# RUNBOOK - shortform-studio

Ordered operator steps with the exact commands. Assumes a Debian/Ubuntu host,
`/opt/workspace/shortform-studio` as the working tree, and network access for the
initial package install only. The pipeline itself downloads no media.

**Storage rule:** the repository is source-only. Every runtime or generated file
(video, captions, metadata, provenance, QA report, measurements, SQLite store)
lives under the external data root, never in the repo tree. See
`docs/ARTIFACT-STORE.md`.

```bash
# Resolve the data root and store path any time:
python3 -m shortform store path
# DATA_ROOT=... STORE_DB=... MEASUREMENTS_DIR=...
```

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

Outputs under `{data_root}/roman-concrete/` (never `out/` in the repo):
`video.mp4`, `captions.srt`, `title.txt`, `description.txt`, `metadata.json`,
`provenance.json`, `graphics/scene_*.png`. `produce` also appends a `renders`
row to the SQLite store.

Optional exact length (must stay inside 15-60 s):

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
cat "$(python3 -c 'from shortform import paths; print(paths.artifact_dir("roman-concrete"))')/qa-report.json"
```

`qa` writes `{data_root}/<slug>/qa-report.json` and appends a QA event to the
`renders`/`qa_reports` tables.

## 3. Inspect the exact upload request without sending it

```bash
python3 -m shortform publish --slug roman-concrete --dry-run
```

## 4. Offline end-to-end proof (no Google credential)

```bash
bash scripts/selftest.sh            # runs produce -> qa -> dry-run -> mock -> live -> measure
DATA_ROOT="$(python3 -c 'from shortform import paths; print(paths.data_root())')"
ls -la "$DATA_ROOT/selftest/"
cat "$DATA_ROOT/selftest/transcript.log"
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
DATA_ROOT="$(python3 -c 'from shortform import paths; print(paths.data_root())')"
cat "$DATA_ROOT/measurements/MOCKID123.jsonl"
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
DATA_ROOT="$(python3 -c 'from shortform import paths; print(paths.data_root())')"
cat "$DATA_ROOT/measurements/<REAL_VIDEO_ID>.jsonl"
```

## 8. Artifact store: migrate, verify, inspect

The historical `out/` tree was imported once into the data root and the SQLite
store. The DDL and migrations live in `shortform/store.py`; the database file is
`{data_root}/studio.db` and is never committed.

```bash
# Print the resolved paths.
python3 -m shortform store path

# One-shot lossless import of the legacy out/<slug>/ tree (idempotent).
python3 -m shortform store migrate

# Re-hash every artifact on disk and compare to the renders rows (sha256 + bytes).
python3 -m shortform store verify     # exit 0 on MATCH, non-zero on mismatch
```

Inspect the tables (the `sqlite3` binary is optional; Python works):

```bash
python3 - <<'PY'
import sqlite3
from shortform import paths
conn = sqlite3.connect(paths.db_path())
print([r[0] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")])
PY
```

## 9. Commit (never commit credentials or generated data)

```bash
git status --short
# Must show NO out/**, no media binary, no *.sqlite3, no runtime ledger rows.
git add shortform storefront tests scripts content docs README.md LICENSE .gitignore
git commit -m "feat: ..."
```

`content/<slug>/script.json` and `storefront/catalog.json` are deliberate SOURCE
fixtures and are safe to add. `out/`, `data/metrics/`, `*.sqlite3`,
`storefront/ledger/*.jsonl` and the billing ledger rows are gitignored; the
storefront/ledger directory stays trackable via `.gitkeep`.

No command in this runbook writes a credential to disk. Keep tokens in the
environment only. Do not `git add` `mocks/transcript.log` if it ever contains a
real token; the mock redacts Authorization, and the pipeline never logs tokens.

## Troubleshooting

* `missing required tool(s): ffmpeg` - run step 0.
* `TTS failed` - check `espeak-ng` or set `$TTS_CMD`.
* QA fails on loudness - re-run `produce` (it re-measures and re-normalises);
  do not hand-edit the audio.
* `publish --live` exits 2 - the OAuth token is missing; see the printed handover.
* `store verify` exits non-zero - an artifact on disk no longer matches its
  `renders` row; re-run `produce` (never hand-edit the file).
* Mock port busy - `MOCK_PORT=8790 bash scripts/selftest.sh`.
