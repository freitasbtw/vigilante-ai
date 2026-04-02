from __future__ import annotations

import logging
import threading
import time
from typing import Generator

import cv2
import numpy as np
from numpy.typing import NDArray

from app.alerts import AlertManager
from app.camera import CameraManager
from app.detector import FACE_CLASS_KEY, EPI_ALERT_LABELS, EPI_LABELS_PT, SafetyDetector

logger = logging.getLogger(__name__)

TARGET_FPS = 25
FRAME_INTERVAL = 1.0 / TARGET_FPS


class StreamProcessor:
    def __init__(
        self,
        camera: CameraManager,
        detector: SafetyDetector,
        alert_manager: AlertManager,
    ) -> None:
        self._camera = camera
        self._detector = detector
        self._alert_manager = alert_manager
        self._stop_event = threading.Event()
        self._stop_event.set()  # Start in stopped state
        self._epoch: int = 0
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._current_jpeg: bytes = b""
        self._fps: float = 0.0
        self._start_time: float = 0.0
        self._active_epis: set[str] = set()
        self._epi_lock = threading.Lock()
        self._last_missing_set: frozenset[str] = frozenset()

    @staticmethod
    def _build_violation_type(missing_keys: set[str]) -> str:
        if not missing_keys:
            return "EPI ausente"
        if len(missing_keys) == 1:
            key = next(iter(missing_keys))
            return EPI_ALERT_LABELS.get(
                key,
                f"{EPI_LABELS_PT.get(key, key)} ausente",
            )
        missing_labels = sorted(EPI_LABELS_PT.get(k, k) for k in missing_keys)
        return f"{', '.join(missing_labels)} ausentes"

    @property
    def active_epis(self) -> set[str]:
        with self._epi_lock:
            return self._active_epis.copy()

    def set_active_epis(self, epis: set[str]) -> None:
        with self._epi_lock:
            self._active_epis = epis.copy()

    @property
    def is_running(self) -> bool:
        return not self._stop_event.is_set()

    @property
    def fps(self) -> float:
        with self._lock:
            return self._fps

    @property
    def uptime(self) -> float:
        with self._lock:
            start = self._start_time
        if start == 0.0:
            return 0.0
        return time.monotonic() - start

    def start(self) -> None:
        if self.is_running:
            logger.warning("Stream processor already running")
            return

        if not self._detector.is_loaded:
            self._detector.load_model()

        self._epoch += 1
        try:
            self._camera.start()
        except Exception:
            logger.exception("Failed to start camera")
            raise
        self._stop_event.clear()
        with self._lock:
            self._start_time = time.monotonic()
        self._thread = threading.Thread(target=self._process_loop, daemon=True)
        self._thread.start()
        logger.info("Stream processor started (epoch=%d)", self._epoch)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        self._camera.stop()
        self._alert_manager.reset_session()
        with self._lock:
            self._current_jpeg = b""
            self._start_time = 0.0
            self._fps = 0.0
        logger.info("Stream processor stopped")

    def get_jpeg_frame(self) -> bytes:
        with self._lock:
            return self._current_jpeg

    def generate_mjpeg(self) -> Generator[bytes, None, None]:
        epoch = self._epoch
        while not self._stop_event.is_set() and epoch == self._epoch:
            frame = self.get_jpeg_frame()
            if frame:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
                )
            # Wait with Event so stop() wakes us immediately
            self._stop_event.wait(0.03)

    def _process_loop(self) -> None:
        frame_count = 0
        fps_timer = time.monotonic()

        while not self._stop_event.is_set():
            loop_start = time.monotonic()

            frame = self._camera.get_frame()
            if frame is None:
                self._stop_event.wait(0.01)
                continue

            detections = self._detector.detect(frame)

            # Filter by active EPIs
            with self._epi_lock:
                active = self._active_epis.copy()
            filtered = [d for d in detections if d.class_name in active] if active else []
            visible_faces = [d for d in detections if d.class_name == FACE_CLASS_KEY]

            # Person proxy: face detection or any PPE detection implies a person is present
            person_present = bool(visible_faces or filtered or detections)
            missing_keys: set[str] = set()

            if person_present and active:
                detected_active = {d.class_name for d in filtered}
                missing_keys = active - detected_active
                representative_confidence = max(
                    (d.confidence for d in filtered),
                    default=max((d.confidence for d in detections), default=0.0),
                )

                # Consolidated alert: one alert for all missing EPIs
                current_missing = frozenset(missing_keys)
                violation_type = self._build_violation_type(missing_keys)
                if missing_keys and (
                    current_missing != self._last_missing_set
                    or not self._alert_manager.is_on_cooldown(violation_type)
                ):
                    self._alert_manager.add_alert(
                        violation_type,
                        representative_confidence,
                        frame,
                        missing_epis=sorted(EPI_LABELS_PT.get(k, k) for k in missing_keys),
                    )
                self._last_missing_set = current_missing
                is_compliant = len(missing_keys) == 0
            else:
                self._last_missing_set = frozenset()
                is_compliant = True

            display_detections = filtered + visible_faces
            annotated = self._detector.annotate_frame(
                frame, display_detections, missing_epis=missing_keys
            )

            self._alert_manager.record_frame(compliant=is_compliant)

            success, buffer = cv2.imencode(".jpg", annotated)
            if success:
                jpeg_bytes: bytes = buffer.tobytes()
                with self._lock:
                    self._current_jpeg = jpeg_bytes

            frame_count += 1
            elapsed = time.monotonic() - fps_timer
            if elapsed >= 1.0:
                with self._lock:
                    self._fps = round(frame_count / elapsed, 1)
                frame_count = 0
                fps_timer = time.monotonic()

            # FPS throttling: sleep remaining time to hit TARGET_FPS
            processing_time = time.monotonic() - loop_start
            sleep_time = FRAME_INTERVAL - processing_time
            if sleep_time > 0:
                self._stop_event.wait(sleep_time)

        logger.debug("Process loop exited")
