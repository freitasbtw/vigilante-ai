#!/bin/sh
# Continuously republish every .mp4 / .mkv in $MEDIA_DIR to MediaMTX.
# Each file <name>.mp4 becomes rtsp://<MEDIAMTX_HOST>:<MEDIAMTX_PORT>/<name>
#
# Re-runs each ffmpeg in an infinite loop so the stream never ends.
# Restarts whole script if files are added/removed (pick up new MP4s).

set -eu

: "${MEDIAMTX_HOST:=mediamtx}"
: "${MEDIAMTX_PORT:=8554}"
: "${MEDIA_DIR:=/media}"
: "${SEEK_SECONDS:=0}"
: "${ACTIVE_VIDEO:=}"

echo "[loop] MediaMTX target: rtsp://${MEDIAMTX_HOST}:${MEDIAMTX_PORT}/"
echo "[loop] Watching: $MEDIA_DIR"

# Wait for MediaMTX to be ready
echo "[loop] Waiting for MediaMTX..."
for i in $(seq 1 30); do
  if nc -z "$MEDIAMTX_HOST" "$MEDIAMTX_PORT" 2>/dev/null; then
    echo "[loop] MediaMTX is up"
    break
  fi
  sleep 1
done

# Discover files (filter by ACTIVE_VIDEO if set)
if [ -n "$ACTIVE_VIDEO" ]; then
  for ext in mp4 mkv mov avi; do
    candidate="$MEDIA_DIR/$ACTIVE_VIDEO.$ext"
    [ -f "$candidate" ] && FILES="$candidate" && break
  done
  : "${FILES:=}"
  [ -z "$FILES" ] && [ -f "$MEDIA_DIR/$ACTIVE_VIDEO" ] && FILES="$MEDIA_DIR/$ACTIVE_VIDEO"
else
  FILES=$(find "$MEDIA_DIR" -maxdepth 1 -type f \( -name "*.mp4" -o -name "*.mkv" -o -name "*.mov" -o -name "*.avi" \) 2>/dev/null | sort)
fi

if [ "$SEEK_SECONDS" != "0" ]; then
  echo "[loop] SEEK_SECONDS=$SEEK_SECONDS (skipping ahead)"
fi
if [ -n "$ACTIVE_VIDEO" ]; then
  echo "[loop] ACTIVE_VIDEO=$ACTIVE_VIDEO (filtered)"
fi

if [ -z "$FILES" ]; then
  echo "[loop] No video files found in $MEDIA_DIR"
  echo "[loop] Drop .mp4 / .mkv files there, then: docker compose restart ffmpeg-loop"
  # Sleep forever so container doesn't restart-loop
  while true; do sleep 3600; done
fi

echo "[loop] Found files:"
echo "$FILES" | sed 's/^/    /'

# Spawn one ffmpeg per file in background; each one loops forever.
PIDS=""
for f in $FILES; do
  name=$(basename "$f")
  stem="${name%.*}"
  url="rtsp://${MEDIAMTX_HOST}:${MEDIAMTX_PORT}/${stem}"
  echo "[loop] Streaming $name → $url"
  (
    while true; do
      ffmpeg -hide_banner -loglevel warning \
        -re -stream_loop -1 \
        -ss "$SEEK_SECONDS" \
        -i "$f" \
        -c:v copy -an \
        -f rtsp -rtsp_transport tcp \
        "$url" || true
      echo "[loop] $name disconnected, restarting in 2s..."
      sleep 2
    done
  ) &
  PIDS="$PIDS $!"
done

# Wait on any child to exit (then container will be restarted by docker)
wait $PIDS
