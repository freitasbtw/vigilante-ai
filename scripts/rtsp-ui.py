#!/usr/bin/env python3
"""
Standalone web UI to control the RTSP demo loop.

- Serves http://localhost:8765
- HLS preview pulled from MediaMTX (http://localhost:8888/<stream>/index.m3u8)
- Buttons call rtsp-control.sh under the hood (-60s / -10s / +10s / +60s, restart, switch)

Run:
    python3 scripts/rtsp-ui.py

Stop with Ctrl+C.

No external Python deps. Uses only stdlib http.server + subprocess.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTROL_SCRIPT = REPO_ROOT / "scripts" / "rtsp-control.sh"
STATE_FILE = REPO_ROOT / "scripts" / ".rtsp_state"
MEDIA_DIR = REPO_ROOT / "media"
PORT = int(os.environ.get("RTSP_UI_PORT", "8765"))
MEDIAMTX_HLS = os.environ.get("MEDIAMTX_HLS", "http://localhost:8888")


def list_videos() -> list[str]:
    if not MEDIA_DIR.exists():
        return []
    out = []
    for ext in ("*.mp4", "*.mkv", "*.mov", "*.avi"):
        out.extend(p.stem for p in MEDIA_DIR.glob(ext))
    return sorted(set(out))


def read_state() -> dict[str, str]:
    state = {"SEEK": "0", "VIDEO": ""}
    if STATE_FILE.exists():
        for line in STATE_FILE.read_text().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                state[k.strip()] = v.strip()
    return state


def run_control(*args: str) -> tuple[int, str]:
    cmd = ["bash", str(CONTROL_SCRIPT), *args]
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=60)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


HTML = """<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8" />
<title>RTSP Control · Vigilante.AI</title>
<meta name="viewport" content="width=device-width,initial-scale=1" />
<style>
  :root {
    --bg: #0a0a0a;
    --panel: #141414;
    --panel-2: #1d1d1d;
    --border: #2a2a2a;
    --text: #ffffff;
    --muted: #b0b0b0;
    --subtle: #777777;
    --accent: #ffffff;
  }
  * { box-sizing: border-box; }
  html, body { height: 100%; margin: 0; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
    font-size: 14px;
    line-height: 1.4;
    -webkit-font-smoothing: antialiased;
  }
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 14px 20px;
    border-bottom: 1px solid var(--border);
    background: var(--panel);
  }
  header h1 {
    font-size: 13px;
    margin: 0;
    text-transform: uppercase;
    letter-spacing: 0.18em;
    font-weight: 600;
  }
  header .pill {
    font-size: 11px;
    color: var(--muted);
    background: var(--panel-2);
    padding: 4px 10px;
    border-radius: 999px;
    border: 1px solid var(--border);
  }
  main {
    display: grid;
    grid-template-columns: 1fr 320px;
    gap: 0;
    height: calc(100vh - 49px);
  }
  .preview {
    background: #000;
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
  }
  .preview video {
    max-width: 100%;
    max-height: 100%;
    background: #000;
  }
  .preview .empty {
    color: var(--subtle);
    font-size: 12px;
    padding: 40px;
    text-align: center;
  }
  aside {
    background: var(--panel);
    border-left: 1px solid var(--border);
    padding: 20px;
    overflow-y: auto;
  }
  .group {
    margin-bottom: 24px;
  }
  .group-label {
    font-size: 10px;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 10px;
  }
  .row {
    display: grid;
    gap: 6px;
  }
  .row-2 { grid-template-columns: 1fr 1fr; }
  .row-4 { grid-template-columns: repeat(4, 1fr); }
  button, select {
    background: var(--panel-2);
    color: var(--text);
    border: 1px solid var(--border);
    padding: 10px 12px;
    font: inherit;
    border-radius: 4px;
    cursor: pointer;
    transition: all 0.1s ease-out;
  }
  button:hover { background: #2a2a2a; border-color: #3a3a3a; }
  button:active { transform: scale(0.98); }
  button:disabled { opacity: 0.4; cursor: not-allowed; }
  button.primary { background: #ffffff; color: #000000; border-color: #ffffff; }
  button.primary:hover { background: #e0e0e0; border-color: #e0e0e0; }
  .seek-buttons button {
    font-weight: 600;
  }
  .state {
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 10px 12px;
    font-size: 12px;
    color: var(--muted);
    display: flex;
    justify-content: space-between;
    margin-bottom: 16px;
  }
  .state strong { color: var(--text); font-weight: 500; }
  select { width: 100%; }
  .log {
    background: #000;
    color: #0f0;
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 10px 12px;
    font-size: 11px;
    height: 130px;
    overflow-y: auto;
    white-space: pre-wrap;
    word-break: break-all;
  }
  .log:empty::before {
    content: 'idle.';
    color: var(--subtle);
  }
  footer {
    font-size: 10px;
    color: var(--subtle);
    text-align: center;
    padding: 8px;
    border-top: 1px solid var(--border);
  }
</style>
</head>
<body>
<header>
  <h1>RTSP Control · Vigilante.AI</h1>
  <span class="pill">localhost:8765</span>
</header>
<main>
  <div class="preview" id="preview-area">
    <div class="empty">Carregando preview…</div>
  </div>
  <aside>
    <div class="state">
      <span>SEEK <strong id="state-seek">0s</strong></span>
      <span>VIDEO <strong id="state-video">all</strong></span>
    </div>

    <div class="group">
      <div class="group-label">Navegar</div>
      <div class="row row-4 seek-buttons">
        <button data-action="prev" data-arg="60">−60s</button>
        <button data-action="prev" data-arg="10">−10s</button>
        <button data-action="next" data-arg="10">+10s</button>
        <button data-action="next" data-arg="60">+60s</button>
      </div>
      <div class="row row-2" style="margin-top:6px;">
        <button data-action="prev" data-arg="300">−5min</button>
        <button data-action="next" data-arg="300">+5min</button>
      </div>
    </div>

    <div class="group">
      <div class="group-label">Saltar para</div>
      <div class="row" style="grid-template-columns:1fr auto; gap:6px;">
        <input type="number" id="seek-input" min="0" placeholder="segundos"
          style="background:var(--panel-2); color:var(--text); border:1px solid var(--border); padding:10px 12px; border-radius:4px; font:inherit;">
        <button class="primary" id="seek-btn">Ir</button>
      </div>
      <div class="row row-2" style="margin-top:6px;">
        <button data-action="restart">Início</button>
        <button data-action="seek" data-arg="600">10:00</button>
      </div>
    </div>

    <div class="group">
      <div class="group-label">Vídeo</div>
      <div class="row" style="grid-template-columns:1fr auto; gap:6px;">
        <select id="video-select"></select>
        <button class="primary" id="switch-btn">Trocar</button>
      </div>
      <button data-action="all" style="margin-top:6px; width:100%;">Tocar todos</button>
    </div>

    <div class="group">
      <div class="group-label">Log</div>
      <div class="log" id="log"></div>
    </div>
  </aside>
</main>
<footer>RTSP loop é live stream. Cada comando reinicia o publisher. Cliente reconecta em ~2s.</footer>

<script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
<script>
  const HLS_BASE = "__HLS_BASE__";
  const logEl = document.getElementById("log");
  const seekEl = document.getElementById("state-seek");
  const videoEl = document.getElementById("state-video");
  const previewArea = document.getElementById("preview-area");
  const videoSelect = document.getElementById("video-select");

  function logLine(msg) {
    const ts = new Date().toLocaleTimeString();
    logEl.textContent = `[${ts}] ${msg}\n` + logEl.textContent;
    logEl.scrollTop = 0;
  }

  async function refreshState() {
    try {
      const res = await fetch("/api/state");
      const data = await res.json();
      seekEl.textContent = (data.SEEK ?? "0") + "s";
      videoEl.textContent = data.VIDEO || "all";
      videoSelect.innerHTML = "";
      data.videos.forEach((v) => {
        const opt = document.createElement("option");
        opt.value = v;
        opt.textContent = v;
        if (v === data.VIDEO) opt.selected = true;
        videoSelect.appendChild(opt);
      });
      // Refresh preview
      const stream = data.VIDEO || (data.videos[0] || "");
      mountHls(stream);
    } catch (e) {
      logLine("erro ao buscar estado: " + e.message);
    }
  }

  let hls = null;
  function mountHls(streamName) {
    previewArea.innerHTML = "";
    if (!streamName) {
      previewArea.innerHTML = '<div class="empty">Sem vídeo configurado.</div>';
      return;
    }
    const url = `${HLS_BASE}/${streamName}/index.m3u8`;
    const video = document.createElement("video");
    video.controls = false;
    video.muted = true;
    video.autoplay = true;
    video.playsInline = true;
    previewArea.appendChild(video);
    if (hls) { hls.destroy(); hls = null; }
    if (window.Hls && Hls.isSupported()) {
      hls = new Hls({ liveBackBufferLength: 4, maxBufferLength: 4, lowLatencyMode: true });
      hls.loadSource(url);
      hls.attachMedia(video);
    } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
      video.src = url;
    } else {
      previewArea.innerHTML = '<div class="empty">Browser não suporta HLS.</div>';
    }
  }

  async function call(action, arg = "") {
    logLine(`> ${action} ${arg}`);
    try {
      const params = new URLSearchParams({ action });
      if (arg !== "") params.set("arg", arg);
      const res = await fetch("/api/control?" + params.toString(), { method: "POST" });
      const data = await res.json();
      logLine(data.output || "(no output)");
      // small delay then refresh + remount stream
      setTimeout(() => {
        refreshState();
        const stream = videoSelect.value;
        // remount in 3s when new stream comes online
        setTimeout(() => mountHls(stream), 3000);
      }, 500);
    } catch (e) {
      logLine("erro: " + e.message);
    }
  }

  document.querySelectorAll("button[data-action]").forEach((btn) => {
    btn.addEventListener("click", () => call(btn.dataset.action, btn.dataset.arg || ""));
  });

  document.getElementById("seek-btn").addEventListener("click", () => {
    const v = document.getElementById("seek-input").value;
    if (v) call("seek", v);
  });

  document.getElementById("switch-btn").addEventListener("click", () => {
    const v = videoSelect.value;
    if (v) call("switch", v);
  });

  refreshState();
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # quiet
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/" or path == "/index.html":
            html = HTML.replace("__HLS_BASE__", MEDIAMTX_HLS)
            body = html.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/state":
            state = read_state()
            state["videos"] = list_videos()
            self._send_json(200, state)
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        qs = parse_qs(urlparse(self.path).query)
        if path == "/api/control":
            action = qs.get("action", [""])[0]
            arg = qs.get("arg", [""])[0]
            if not action:
                self._send_json(400, {"error": "missing action"})
                return
            cmd = [action] if not arg else [action, arg]
            rc, out = run_control(*cmd)
            self._send_json(200, {"rc": rc, "output": out.strip()})
            return
        self.send_response(404)
        self.end_headers()


def main() -> None:
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"\n  RTSP UI listening on  http://localhost:{PORT}")
    print(f"  HLS preview source:   {MEDIAMTX_HLS}")
    print(f"  Control script:        {CONTROL_SCRIPT}\n")
    print("  Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")


if __name__ == "__main__":
    main()
