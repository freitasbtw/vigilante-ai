"""Video stream sources (webcam, RTSP) with auto-reconnect."""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

import cv2
import numpy as np
from numpy.typing import NDArray

from app.observability import stream_reconnects

logger = logging.getLogger(__name__)


@dataclass
class StreamHealth:
    online: bool = False
    last_frame_at: float | None = None
    consecutive_failures: int = 0
    reconnect_count: int = 0
    last_error: str | None = None


class StreamSource(ABC):
    """Abstract source yielding the latest decoded frame on demand."""

    INITIAL_BACKOFF: float = 1.0
    MAX_BACKOFF: float = 30.0
    FAILURE_THRESHOLD: int = 5

    def __init__(self, camera_id: str | None = None) -> None:
        self._camera_id = camera_id or "unknown"
        self._frame: NDArray[np.uint8] | None = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._stop_event.set()
        self._thread: threading.Thread | None = None
        self._health = StreamHealth()

    @property
    def is_running(self) -> bool:
        return not self._stop_event.is_set()

    @property
    def health(self) -> StreamHealth:
        with self._lock:
            return StreamHealth(
                online=self._health.online,
                last_frame_at=self._health.last_frame_at,
                consecutive_failures=self._health.consecutive_failures,
                reconnect_count=self._health.reconnect_count,
                last_error=self._health.last_error,
            )

    @abstractmethod
    def _open(self) -> cv2.VideoCapture: ...

    @abstractmethod
    def describe(self) -> str:
        """Human-readable identifier (safe for logs — credentials masked)."""

    def start(self) -> None:
        if self.is_running:
            logger.warning("Source %s already running", self.describe())
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._capture_loop,
            daemon=True,
            name=f"src-{self.describe()[:32]}",
        )
        self._thread.start()
        logger.info("Source %s started", self.describe())

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        with self._lock:
            self._frame = None
            self._health.online = False
        logger.info("Source %s stopped", self.describe())

    def get_frame(self) -> NDArray[np.uint8] | None:
        with self._lock:
            if self._frame is None:
                return None
            return self._frame.copy()

    def _capture_loop(self) -> None:
        backoff = self.INITIAL_BACKOFF
        capture: cv2.VideoCapture | None = None
        try:
            while not self._stop_event.is_set():
                if capture is None:
                    try:
                        capture = self._open()
                    except Exception as exc:
                        logger.exception("Failed to open %s", self.describe())
                        self._record_error(str(exc))
                        self._sleep(backoff)
                        backoff = min(backoff * 2, self.MAX_BACKOFF)
                        continue
                    if not capture.isOpened():
                        logger.warning("Source %s did not open", self.describe())
                        self._record_error("Source did not open")
                        capture.release()
                        capture = None
                        self._sleep(backoff)
                        backoff = min(backoff * 2, self.MAX_BACKOFF)
                        continue
                    backoff = self.INITIAL_BACKOFF
                    with self._lock:
                        self._health.online = True
                        self._health.last_error = None

                ret, frame = capture.read()
                if not ret or frame is None:
                    failures = self._increment_failure()
                    if failures >= self.FAILURE_THRESHOLD:
                        logger.warning(
                            "Source %s lost (%d failures), reconnecting",
                            self.describe(),
                            failures,
                        )
                        capture.release()
                        capture = None
                        with self._lock:
                            self._health.online = False
                            self._health.reconnect_count += 1
                            self._health.consecutive_failures = 0
                        stream_reconnects.labels(camera_id=self._camera_id).inc()
                        self._sleep(backoff)
                        backoff = min(backoff * 2, self.MAX_BACKOFF)
                    else:
                        self._sleep(0.05)
                    continue

                with self._lock:
                    self._frame = np.asarray(frame, dtype=np.uint8)
                    self._health.last_frame_at = time.time()
                    self._health.consecutive_failures = 0
        finally:
            if capture is not None:
                capture.release()
            logger.debug("Capture loop exited for %s", self.describe())

    def _increment_failure(self) -> int:
        with self._lock:
            self._health.consecutive_failures += 1
            return self._health.consecutive_failures

    def _record_error(self, msg: str) -> None:
        with self._lock:
            self._health.last_error = msg

    def _sleep(self, seconds: float) -> None:
        self._stop_event.wait(seconds)


class LocalCameraSource(StreamSource):
    """USB / built-in camera via cv2.VideoCapture(index)."""

    def __init__(
        self,
        index: int = 0,
        width: int = 640,
        height: int = 480,
        camera_id: str | None = None,
    ) -> None:
        super().__init__(camera_id=camera_id)
        self._index = index
        self._width = width
        self._height = height

    def describe(self) -> str:
        return f"local:{self._index}"

    def _open(self) -> cv2.VideoCapture:
        if sys.platform.startswith("win"):
            cap = cv2.VideoCapture(self._index, cv2.CAP_DSHOW)
        else:
            cap = cv2.VideoCapture(self._index)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap


class RTSPSource(StreamSource):
    """IP camera via RTSP (default TCP transport for reliability)."""

    def __init__(
        self, url: str, transport: str = "tcp", camera_id: str | None = None
    ) -> None:
        super().__init__(camera_id=camera_id)
        self._url = url
        self._transport = transport

    def describe(self) -> str:
        return f"rtsp:{_mask_url(self._url)}"

    def _open(self) -> cv2.VideoCapture:
        # FFmpeg-level RTSP options. Set per-call so multiple sources can coexist.
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
            f"rtsp_transport;{self._transport}|stimeout;5000000"
        )
        cap = cv2.VideoCapture(self._url, cv2.CAP_FFMPEG)
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)
            cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000)
        except Exception:
            pass
        return cap


def probe_rtsp(url: str, timeout_seconds: float = 5.0) -> tuple[bool, str]:
    """Test an RTSP URL — returns (success, message). Releases capture immediately."""
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
        f"rtsp_transport;tcp|stimeout;{int(timeout_seconds * 1_000_000)}"
    )
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    try:
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, int(timeout_seconds * 1000))
        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, int(timeout_seconds * 1000))
    except Exception:
        pass
    try:
        if not cap.isOpened():
            return False, "Failed to open RTSP stream"
        ret, frame = cap.read()
        if not ret or frame is None:
            return False, "Opened but failed to read frame within timeout"
        h, w = frame.shape[:2]
        return True, f"OK ({w}x{h})"
    finally:
        cap.release()


def _mask_url(url: str) -> str:
    """Mask credentials in URL for safe logging."""
    if "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    if "@" not in rest:
        return url
    _, host_part = rest.split("@", 1)
    return f"{scheme}://***@{host_part}"
