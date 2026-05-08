"""Per-camera alert service: persists alerts to DB + frames to blob store.

Replaces the in-memory `AlertManager` for the new flow. Frame counters
(used for compliance rate during a session) remain in memory because
they tick on every frame and would crush the DB if persisted directly.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

import cv2
import numpy as np
from numpy.typing import NDArray

from app.config import settings
from app.db.base import session_scope
from app.observability import alerts_total
from app.repositories import AlertRepository
from app.storage import BlobStore

logger = logging.getLogger(__name__)


class AlertService:
    """Replacement for AlertManager — persists to Postgres + filesystem."""

    def __init__(self, camera_id: str, blob_store: BlobStore) -> None:
        self._camera_id = camera_id
        self._blob_store = blob_store
        self._cooldowns: dict[str, datetime] = {}
        self._lock = threading.Lock()
        self._session_start: datetime = datetime.utcnow()
        self._total_frames: int = 0
        self._compliant_frames: int = 0

    # --- write path ---

    def add_alert(
        self,
        violation_type: str,
        confidence: float,
        frame: NDArray[np.uint8],
        missing_epis: list[str] | None = None,
        raw_frame: NDArray[np.uint8] | None = None,
        detected_bboxes: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        if self._is_on_cooldown(violation_type):
            return None

        # Suppress duplicates while a reviewer hasn't yet decided on the prior
        # alert for this (camera, violation_type). Otherwise the same persistent
        # violation re-spawns every cooldown window and the pending queue
        # never drains for the supervisor.
        try:
            with session_scope() as session:
                if AlertRepository(session).has_unreviewed(
                    self._camera_id, violation_type
                ):
                    with self._lock:
                        self._cooldowns[violation_type] = datetime.utcnow()
                    return None
        except Exception:
            logger.exception(
                "has_unreviewed check failed for camera %s; falling through",
                self._camera_id,
            )

        alert_id = str(uuid4())
        quality = settings.ALERT_JPEG_QUALITY
        thumb_jpeg = _encode_jpeg(frame, width=160, quality=quality)
        # Annotated frame at native resolution for high-quality admin review.
        full_jpeg = _encode_jpeg(frame, width=None, quality=quality)
        # Raw (un-annotated) frame at native resolution for retraining export.
        raw_jpeg = (
            _encode_jpeg(raw_frame, width=None, quality=quality)
            if raw_frame is not None
            else b""
        )

        thumb_path = (
            self._blob_store.save_jpeg(
                camera_id=self._camera_id,
                alert_id=alert_id,
                kind="thumb",
                data=thumb_jpeg,
            )
            if thumb_jpeg
            else None
        )
        frame_path = (
            self._blob_store.save_jpeg(
                camera_id=self._camera_id,
                alert_id=alert_id,
                kind="frame",
                data=full_jpeg,
            )
            if full_jpeg
            else None
        )
        raw_path = (
            self._blob_store.save_jpeg(
                camera_id=self._camera_id,
                alert_id=alert_id,
                kind="raw",
                data=raw_jpeg,
            )
            if raw_jpeg
            else None
        )

        try:
            with session_scope() as session:
                repo = AlertRepository(session)
                repo.create(
                    camera_id=self._camera_id,
                    violation_type=violation_type,
                    confidence=confidence,
                    missing_epis=missing_epis or [],
                    frame_path=frame_path,
                    thumbnail_path=thumb_path,
                    frame_raw_path=raw_path,
                    detected_bboxes=detected_bboxes or [],
                    alert_id=alert_id,
                )
                session.commit()
        except Exception:
            logger.exception("Failed to persist alert for camera %s", self._camera_id)
            # Roll back blobs to avoid orphans
            for p in (thumb_path, frame_path, raw_path):
                if p is not None:
                    self._blob_store.delete(p)
            return None

        with self._lock:
            self._cooldowns[violation_type] = datetime.utcnow()
        alerts_total.labels(
            camera_id=self._camera_id, violation_type=violation_type
        ).inc()
        return {
            "id": alert_id,
            "violation_type": violation_type,
            "confidence": confidence,
            "missing_epis": missing_epis or [],
            "frame_path": frame_path,
            "thumbnail_path": thumb_path,
        }

    # --- in-memory frame counters (per-session compliance) ---

    def record_frame(self, *, compliant: bool) -> None:
        with self._lock:
            self._total_frames += 1
            if compliant:
                self._compliant_frames += 1

    def reset_session(self) -> None:
        with self._lock:
            self._cooldowns.clear()
            self._total_frames = 0
            self._compliant_frames = 0
            self._session_start = datetime.utcnow()

    def session_compliance(self) -> dict[str, Any]:
        with self._lock:
            total = self._total_frames
            compliant = self._compliant_frames
            started = self._session_start
        rate = (compliant / total * 100.0) if total > 0 else 100.0
        duration = (datetime.utcnow() - started).total_seconds()
        return {
            "total_frames": total,
            "compliant_frames": compliant,
            "compliance_rate": round(rate, 1),
            "session_duration_seconds": round(duration, 1),
        }

    # --- internal ---

    def _is_on_cooldown(self, violation_type: str) -> bool:
        with self._lock:
            last = self._cooldowns.get(violation_type)
        if last is None:
            return False
        return datetime.utcnow() - last < timedelta(seconds=settings.ALERT_COOLDOWN_SECONDS)


def _encode_jpeg(
    frame: NDArray[np.uint8], width: int | None, quality: int = 95
) -> bytes:
    """Encode `frame` to JPEG bytes. `width=None` keeps native resolution."""
    if width is None:
        resized = frame
    else:
        src_h, src_w = frame.shape[:2]
        target_w = min(width, src_w)
        target_h = max(1, int(src_h * (target_w / src_w)))
        resized = cv2.resize(frame, (target_w, target_h))
    success, buffer = cv2.imencode(
        ".jpg", resized, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)]
    )
    if not success:
        return b""
    return bytes(buffer.tobytes())
