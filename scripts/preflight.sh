#!/usr/bin/env bash
# preflight.sh - one gate to run before a live YouTube publish.
#
# It fails LOUDLY (non-zero) unless ALL of these hold for the selected slug:
#   1. $YOUTUBE_OAUTH_TOKEN is set and non-empty
#   2. the produced artifact exists (out/<slug>/video.mp4 and metadata.json)
#   3. `python3 -m shortform qa --slug <slug>` exits 0
#
# On success it prints, at the very end, the exact dry-run and live publish
# commands to copy. It sends nothing and never prints the token value.
#
# Usage:
#   scripts/preflight.sh [--slug roman-concrete]
#
# Exit codes: 0 = PASS (safe to publish), 1 = FAIL (do not publish), 2 = bad usage.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
PY="${PYTHON:-python3}"
SLUG="${SLUG:-roman-concrete}"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --slug)
      [ "$#" -ge 2 ] || { echo "preflight: --slug needs a value" >&2; exit 2; }
      SLUG="$2"; shift 2 ;;
    -h|--help)
      echo "usage: scripts/preflight.sh [--slug <slug>]"; exit 0 ;;
    *)
      echo "preflight: unknown argument: $1" >&2; exit 2 ;;
  esac
done

ARTIFACTS_ROOT="$("$PY" -c 'from shortform import paths; print(paths.data_root())')"
ART_DIR="$ARTIFACTS_ROOT/$SLUG"
VIDEO="$ART_DIR/video.mp4"
META="$ART_DIR/metadata.json"
FAILURES=0

ok()  { printf '[PASS] %s\n' "$1"; }
bad() { printf '[FAIL] %s\n' "$1"; FAILURES=$((FAILURES + 1)); }

echo "=== PREFLIGHT: live publish gate for slug '$SLUG' ==="

# --- 1. OAuth token ---------------------------------------------------------
if [ -n "${YOUTUBE_OAUTH_TOKEN:-}" ]; then
  ok "YOUTUBE_OAUTH_TOKEN is set (value is never printed)"
else
  bad "YOUTUBE_OAUTH_TOKEN is not set - a live upload is impossible."
  echo "       A human must mint an OAuth token with BOTH scopes:"
  echo "         https://www.googleapis.com/auth/youtube.upload"
  echo "         https://www.googleapis.com/auth/youtube.readonly"
  echo "       then make it available to this shell, e.g.:"
  echo "         export YOUTUBE_OAUTH_TOKEN=\"ya29...\""
  echo "       See docs/deploy/handover-2026-09-27.md step 2."
fi

# --- 2. artifact ------------------------------------------------------------
if [ -f "$VIDEO" ]; then
  ok "artifact exists: $VIDEO ($(wc -c <"$VIDEO") bytes)"
else
  bad "artifact missing: $VIDEO - run: python3 -m shortform produce --slug $SLUG"
fi
if [ -f "$META" ]; then
  ok "metadata exists: $META"
else
  bad "metadata missing: $META - run produce first"
fi

# --- 3. QA gate -------------------------------------------------------------
if [ -f "$VIDEO" ]; then
  echo "--- python3 -m shortform qa --slug $SLUG ---"
  "$PY" -m shortform qa --slug "$SLUG"
  qa_code=$?
  if [ "$qa_code" -eq 0 ]; then
    ok "qa exited 0 (PASS)"
  else
    bad "qa exited $qa_code (FAIL) - do NOT publish"
  fi
else
  bad "qa skipped because the artifact is missing"
fi

echo "------------------------------------------------------------"
if [ "$FAILURES" -ne 0 ]; then
  echo "PREFLIGHT RESULT: FAIL ($FAILURES check(s) failed) - DO NOT PUBLISH LIVE"
  exit 1
fi

echo "PREFLIGHT RESULT: PASS - safe to run the dry run, then the live upload"
echo
echo "COPY-PASTE COMMANDS (run in this order):"
echo
echo "  1) dry run (sends nothing):"
echo "     python3 -m shortform publish --slug $SLUG --dry-run"
echo
echo "  2) live private upload (only after the human review in YouTube Studio):"
echo "     python3 -m shortform publish --slug $SLUG --live --privacy private"
echo
exit 0
