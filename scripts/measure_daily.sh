#!/usr/bin/env bash
# measure_daily.sh - append one measurement snapshot per video per UTC day.
#
# Usage:
#   scripts/measure_daily.sh <VIDEO_ID> [--mock] [--api-base URL] [--force]
#
# It runs:
#   python3 -m shortform measure --video-id <VIDEO_ID> [--mock] [--api-base URL]
# which appends one row per metric to the SQLite measurement_series table and
# mirrors a timestamped JSON line to {data_root}/measurements/<VIDEO_ID>.jsonl,
# then it prints a one-line summary. {data_root} is outside the repo:
# $SHORTFORM_ARTIFACTS_DIR or {OMNI_DIR}/data/artifacts/shortform-studio.
#
# Guards against double runs:
#   * at most one snapshot per video per UTC calendar day (override: --force)
#   * a flock so two concurrent cron firings cannot both append
#
# Schedule it from the HOST; do not install anything system-wide from the agent.
# See docs/deploy/measurement-2026-09-27.md for the cron / systemd timer lines.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
PY="${PYTHON:-python3}"

if [ "$#" -lt 1 ] || [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
  sed -n '2,17p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  if [ "$#" -ge 1 ]; then exit 0; else exit 2; fi
fi

VIDEO_ID="$1"; shift
MOCK=0
API_BASE=""
FORCE=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --mock) MOCK=1; shift ;;
    --api-base)
      [ "$#" -ge 2 ] || { echo "measure_daily: --api-base needs a value" >&2; exit 2; }
      API_BASE="$2"; shift 2 ;;
    --force) FORCE=1; shift ;;
    *) echo "measure_daily: unknown argument: $1" >&2; exit 2 ;;
  esac
done

[ -n "$VIDEO_ID" ] || { echo "measure_daily: <VIDEO_ID> is required" >&2; exit 2; }

METRICS_DIR="$("$PY" -c 'from shortform import paths; print(paths.measurements_dir())')"
mkdir -p "$METRICS_DIR"
JSONL="$METRICS_DIR/$VIDEO_ID.jsonl"
MARK="$METRICS_DIR/$VIDEO_ID.daily"
LOCK="$METRICS_DIR/$VIDEO_ID.flock"
TODAY="$(date -u +%Y-%m-%d)"

# Guard 1: one snapshot per video per UTC day.
if [ "$FORCE" -ne 1 ] && [ -f "$MARK" ] && [ "$(cat "$MARK" 2>/dev/null)" = "$TODAY" ]; then
  echo "[SKIP] $VIDEO_ID already measured for $TODAY; use --force to run again"
  exit 0
fi

# Guard 2: only one process at a time (cron can overlap).
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "[SKIP] another measure_daily.sh run is already in progress for $VIDEO_ID"
  exit 0
fi

ARGS=(--video-id "$VIDEO_ID")
[ "$MOCK" -eq 1 ] && ARGS+=(--mock)
[ -n "$API_BASE" ] && ARGS+=(--api-base "$API_BASE")

"$PY" -m shortform measure "${ARGS[@]}"
code=$?
if [ "$code" -ne 0 ]; then
  echo "[FAIL] measure exited $code; no snapshot appended" >&2
  exit "$code"
fi

printf '%s\n' "$TODAY" > "$MARK"

# One-line summary, read straight from the JSON line we just appended.
"$PY" - "$JSONL" "$VIDEO_ID" <<'PYEOF'
import json, sys
path, vid = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as fh:
    last = [ln for ln in fh if ln.strip()][-1]
row = json.loads(last)
st = row.get("statistics", {})
print(
    "[OK] {vid} views={v} likes={l} comments={c} placeholder={p}% source={s} fetched_at={t}".format(
        vid=vid,
        v=st.get("viewCount", "?"),
        l=st.get("likeCount", "?"),
        c=st.get("commentCount", "?"),
        p=row.get("view_through_placeholder_pct"),
        s=row.get("source"),
        t=row.get("fetched_at"),
    )
)
PYEOF
exit 0
