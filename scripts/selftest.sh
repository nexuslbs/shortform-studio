#!/usr/bin/env bash
# One-shot end-to-end self-test for shortform-studio.
#
# It runs, in order:
#   produce -> qa -> publish --dry-run -> start mock
#           -> publish --live --api-base http://127.0.0.1:8787
#           -> measure --mock -> stop mock
#
# Every step prints PASS/FAIL and its raw output is left under out/selftest/.
# Exit code is 0 only when every step passed.
set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

SLUG="${SELFTEST_SLUG:-roman-concrete}"
PORT="${MOCK_PORT:-8787}"
BASE="http://127.0.0.1:${PORT}"
RAW="$REPO/out/selftest"
PY="${PYTHON:-python3}"

rm -rf "$RAW"
mkdir -p "$RAW"
rm -f "$REPO/mocks/transcript.log"

FAILURES=0
declare -a SUMMARY=()

step() {
  local name="$1"; shift
  echo
  echo "===================================================================="
  echo "STEP: $name"
  echo "\$ $*"
  echo "--------------------------------------------------------------------"
  "$@" 2>&1 | tee "$RAW/${name}.log"
  local code="${PIPESTATUS[0]}"
  if [ "$code" -eq 0 ]; then
    echo "RESULT: PASS ($name)"
    SUMMARY+=("PASS  $name")
  else
    echo "RESULT: FAIL ($name) exit=$code"
    SUMMARY+=("FAIL  $name (exit=$code)")
    FAILURES=$((FAILURES + 1))
  fi
  return "$code"
}

wait_for_port() {
  "$PY" - "$PORT" <<'PYEOF'
import socket, sys, time
port = int(sys.argv[1])
for _ in range(100):
    s = socket.socket()
    s.settimeout(0.3)
    try:
        s.connect(("127.0.0.1", port))
        s.close()
        sys.exit(0)
    except OSError:
        time.sleep(0.1)
    finally:
        s.close()
sys.exit(1)
PYEOF
}

# --------------------------------------------------------------------------- #
# 1) produce (real artifact)
# --------------------------------------------------------------------------- #
step produce "$PY" -m shortform produce --slug "$SLUG"

# --------------------------------------------------------------------------- #
# 2) qa
# --------------------------------------------------------------------------- #
step qa "$PY" -m shortform qa --slug "$SLUG"
[ -f "$REPO/out/$SLUG/qa-report.json" ] && cp "$REPO/out/$SLUG/qa-report.json" "$RAW/qa-report.json"

# --------------------------------------------------------------------------- #
# 3) publish --dry-run (sends nothing)
# --------------------------------------------------------------------------- #
step publish-dry-run "$PY" -m shortform publish --slug "$SLUG" --dry-run

# --------------------------------------------------------------------------- #
# 4) start mock
# --------------------------------------------------------------------------- #
echo
echo "===================================================================="
echo "STEP: start-mock"
echo "--------------------------------------------------------------------"
"$PY" "$REPO/mocks/youtube_mock.py" --port "$PORT" \
  --transcript "$REPO/mocks/transcript.log" >"$RAW/mock-server.log" 2>&1 &
MOCK_PID=$!
if wait_for_port; then
  echo "RESULT: PASS (start-mock) pid=$MOCK_PID"
  SUMMARY+=("PASS  start-mock")
else
  echo "RESULT: FAIL (start-mock) - port $PORT never opened"
  cat "$RAW/mock-server.log"
  SUMMARY+=("FAIL  start-mock")
  FAILURES=$((FAILURES + 1))
fi

# --------------------------------------------------------------------------- #
# 5) publish --live against the mock (dummy bearer token; localhost only)
# --------------------------------------------------------------------------- #
if kill -0 "$MOCK_PID" 2>/dev/null; then
  step publish-live env YOUTUBE_OAUTH_TOKEN=mock-test-token \
    "$PY" -m shortform publish --slug "$SLUG" --live --privacy private --api-base "$BASE"
else
  echo "RESULT: SKIP (publish-live) - mock not running"
  SUMMARY+=("SKIP  publish-live")
fi

# --------------------------------------------------------------------------- #
# 6) measure --mock
# --------------------------------------------------------------------------- #
if kill -0 "$MOCK_PID" 2>/dev/null; then
  step measure-mock env YOUTUBE_API_KEY=mock-key MOCK_API_BASE="$BASE" \
    "$PY" -m shortform measure --video-id MOCKID123 --mock
else
  echo "RESULT: SKIP (measure-mock) - mock not running"
  SUMMARY+=("SKIP  measure-mock")
fi

# --------------------------------------------------------------------------- #
# 7) stop mock + preserve raw transcript
# --------------------------------------------------------------------------- #
echo
echo "===================================================================="
echo "STEP: stop-mock"
echo "--------------------------------------------------------------------"
if kill -0 "$MOCK_PID" 2>/dev/null; then
  kill "$MOCK_PID" 2>/dev/null
  wait "$MOCK_PID" 2>/dev/null
  echo "RESULT: PASS (stop-mock)"
  SUMMARY+=("PASS  stop-mock")
else
  echo "RESULT: PASS (stop-mock) - already stopped"
  SUMMARY+=("PASS  stop-mock")
fi
cp "$REPO/mocks/transcript.log" "$RAW/transcript.log" 2>/dev/null || true
cp "$REPO/out/$SLUG/video.mp4" "$RAW/video.mp4" 2>/dev/null || true
ffprobe -v error -show_streams -show_format -of json "$REPO/out/$SLUG/video.mp4" \
  > "$RAW/ffprobe.json" 2>&1 || true

# --------------------------------------------------------------------------- #
# summary
# --------------------------------------------------------------------------- #
echo
echo "===================================================================="
echo "SELFTEST SUMMARY"
echo "===================================================================="
for line in "${SUMMARY[@]}"; do
  echo "  $line"
done
echo "--------------------------------------------------------------------"
if [ "$FAILURES" -eq 0 ]; then
  echo "SELFTEST RESULT: PASS"
  exit 0
fi
echo "SELFTEST RESULT: FAIL ($FAILURES failing step(s))"
exit 1
