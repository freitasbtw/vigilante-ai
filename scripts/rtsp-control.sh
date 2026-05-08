#!/usr/bin/env bash
# RTSP playback control for the demo loop.
#
# Usage:
#   scripts/rtsp-control.sh seek 300       # restart playback at 5min mark
#   scripts/rtsp-control.sh restart         # restart from start (alias for seek 0)
#   scripts/rtsp-control.sh next 30         # skip ahead 30s from CURRENT seek
#   scripts/rtsp-control.sh prev 30         # rewind 30s from CURRENT seek
#   scripts/rtsp-control.sh switch obra2    # play only media/obra2.mp4
#   scripts/rtsp-control.sh all             # play every video in media/ again
#   scripts/rtsp-control.sh status          # show current state
#   scripts/rtsp-control.sh logs            # tail ffmpeg-loop logs
#
# Notes:
#   - RTSP is a live stream. There is no "pause/seek" mid-flight; we restart
#     the publisher with a new -ss offset. Clients (backend, VLC) reconnect
#     within ~2 seconds.
#   - Current seek offset is persisted in scripts/.rtsp_state so prev/next
#     can do relative arithmetic.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STATE_FILE="$REPO_ROOT/scripts/.rtsp_state"
cd "$REPO_ROOT"

CMD="${1:-status}"
ARG="${2:-}"

current_seek() {
  if [[ -f "$STATE_FILE" ]]; then
    grep -E '^SEEK=' "$STATE_FILE" | cut -d= -f2 || echo 0
  else
    echo 0
  fi
}

current_video() {
  if [[ -f "$STATE_FILE" ]]; then
    grep -E '^VIDEO=' "$STATE_FILE" | cut -d= -f2 || echo ""
  else
    echo ""
  fi
}

write_state() {
  cat > "$STATE_FILE" <<EOF
SEEK=$1
VIDEO=$2
EOF
}

restart_loop() {
  local seek="$1"
  local video="$2"
  write_state "$seek" "$video"
  printf "\033[1;36m[rtsp]\033[0m restart with SEEK=%ss VIDEO=%s\n" "$seek" "${video:-(all)}"
  SEEK_SECONDS="$seek" ACTIVE_VIDEO="$video" \
    docker compose --profile rtsp up -d --force-recreate --no-deps ffmpeg-loop
  echo "[rtsp] new stream starts publishing in ~2s — clients reconnect automatically."
}

case "$CMD" in
  seek)
    SEC="${ARG:-0}"
    [[ "$SEC" =~ ^[0-9]+$ ]] || { echo "seek arg must be a positive integer (seconds)"; exit 1; }
    restart_loop "$SEC" "$(current_video)"
    ;;
  next|skip)
    DELTA="${ARG:-30}"
    NEW=$(( $(current_seek) + DELTA ))
    restart_loop "$NEW" "$(current_video)"
    ;;
  prev|back|rewind)
    DELTA="${ARG:-30}"
    NEW=$(( $(current_seek) - DELTA ))
    [[ "$NEW" -lt 0 ]] && NEW=0
    restart_loop "$NEW" "$(current_video)"
    ;;
  restart|reset)
    restart_loop 0 "$(current_video)"
    ;;
  switch)
    [[ -n "$ARG" ]] || { echo "usage: switch <video-basename>  (without .mp4)"; exit 1; }
    restart_loop 0 "$ARG"
    ;;
  all)
    restart_loop 0 ""
    ;;
  status)
    echo "[rtsp] current SEEK=$(current_seek)s VIDEO=$(current_video)"
    docker compose ps ffmpeg-loop || true
    ;;
  logs)
    docker compose logs --tail 30 -f ffmpeg-loop
    ;;
  *)
    echo "unknown command: $CMD"
    echo "usage: $0 {seek N|next [N]|prev [N]|restart|switch <name>|all|status|logs}"
    exit 1
    ;;
esac
