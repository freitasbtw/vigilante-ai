#!/usr/bin/env bash
# Idempotent bootstrap for the RTSP loop control web UI.
# Kills any process on :8765 and restarts rtsp-ui.py in the background.

set -euo pipefail

PORT="${RTSP_UI_PORT:-8765}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_FILE="${RTSP_UI_LOG:-/tmp/rtsp-ui.log}"

# Kill anything already bound to the port (best-effort, no failure if nothing).
if PIDS=$(ss -tlnp 2>/dev/null | awk -v p=":$PORT" '$4 ~ p {print}' | grep -oP 'pid=\K[0-9]+' | sort -u); then
  if [[ -n "$PIDS" ]]; then
    echo "Killing existing rtsp-ui processes: $PIDS"
    # shellcheck disable=SC2086
    kill $PIDS 2>/dev/null || true
    sleep 0.5
  fi
fi

# Also kill stale rtsp-ui.py invocations even if port detection missed them.
pkill -f "rtsp-ui.py" 2>/dev/null || true
sleep 0.3

cd "$REPO_ROOT"
echo "Starting rtsp-ui.py on :$PORT (logs: $LOG_FILE)"
nohup python3 "$SCRIPT_DIR/rtsp-ui.py" >"$LOG_FILE" 2>&1 &
disown || true

# Smoke test
sleep 1
if curl -fsS "http://localhost:$PORT/" >/dev/null; then
  echo "OK: http://localhost:$PORT/"
else
  echo "FAIL: rtsp-ui not responding. Tail log:"
  tail -n 30 "$LOG_FILE" || true
  exit 1
fi
