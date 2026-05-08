# RTSP test media

Drop video files here to expose them as RTSP streams (simulating IP cameras).

## Supported formats
`.mp4`, `.mkv`, `.mov`, `.avi` — H.264/H.265 codec recommended (no transcode).

## How it works

1. `docker compose --profile rtsp up -d`
2. `ffmpeg-loop` container scans this folder
3. Each file `<name>.mp4` becomes available at:
   `rtsp://localhost:8554/<name>`
   (without the file extension)
4. ffmpeg loops the file infinitely with `-stream_loop -1`
5. After dropping new files, restart: `docker compose restart ffmpeg-loop`

## Recommended sources for canteiro CCTV-style videos

YouTube searches that yield fixed-camera, top-down construction footage:

- `construction site time lapse 4k`
- `construction webcam 24/7`
- `highrise construction camera`
- `aerial construction site fixed camera`
- `obra construção time lapse Brasil`

Download with `yt-dlp`:

```bash
# Install once: pip install -U yt-dlp
yt-dlp -f "best[ext=mp4][height<=720]" "<youtube-url>" -o "media/%(title)s.%(ext)s"
```

720p sufficient — real IP cameras stream at 720-1080p.

## Test the stream

After dropping `canteiro.mp4` and starting the profile:

```bash
# Probe (without playing)
ffprobe rtsp://localhost:8554/canteiro

# Play in VLC
vlc rtsp://localhost:8554/canteiro

# Or via Vigilante.AI: register at http://localhost:3000/cameras
#   name: Canteiro teste
#   source_kind: rtsp
#   rtsp_url: rtsp://mediamtx:8554/canteiro    (when backend is in same compose)
#   rtsp_url: rtsp://localhost:8554/canteiro   (when backend runs on host)
```

## .gitignore note

This folder is gitignored except for this README — actual videos stay local.
