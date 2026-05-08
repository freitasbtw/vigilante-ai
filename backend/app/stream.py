from __future__ import annotations

import logging
import threading
import time
from typing import Generator

import cv2
import numpy as np
from numpy.typing import NDArray

from collections import deque
from typing import Deque

from app.alerts import AlertManager
from app.detector import (
    FACE_CLASS_KEY,
    EPI_ALERT_LABELS,
    EPI_LABELS_PT,
    Detection,
    SafetyDetector,
)
from app.observability import inference_latency, stream_fps, stream_online
from app.sources import StreamSource

logger = logging.getLogger(__name__)

TARGET_FPS = 25
FRAME_INTERVAL = 1.0 / TARGET_FPS

# Asymmetric temporal smoothing.
#   * Going TO "missing" is the more dangerous direction (false positive
#     "sem capacete" when the model momentarily drops the detection).
#     Demand stronger evidence (longer window).
#   * Going TO "present" is the safe direction. React quickly so the
#     person bbox flips back to green soon after a real detection
#     resumes.
SMOOTHING_TO_MISSING_S = 5.0
SMOOTHING_TO_PRESENT_S = 1.5
# Legacy alias used by older histories. Equal to the longer window.
SMOOTHING_WINDOW_S = SMOOTHING_TO_MISSING_S

# A person's helmet status is only checked when their head zone is
# plausibly visible in frame. Bboxes touching the top edge are assumed
# clipped (camera angle, occlusion) and skip the helmet check entirely
# rather than wrongly flag the person as "sem capacete".
HEAD_VISIBLE_TOP_MARGIN_PX = 6
HEAD_VISIBLE_MIN_PERSON_HEIGHT_PX = 80

# How much overlap is required between a PPE bbox and a person's head/torso
# zone for it to count as "worn by that person". Low because PPE bboxes are
# small and partial overlap (e.g. helmet edge inside head zone) is normal.
PPE_PERSON_MIN_OVERLAP = 0.10

# Per-track tuning
TRACK_IOU_THRESHOLD = 0.30
TRACK_STALE_S = 1.5
# A class is considered "missing" for a track only if it was missing in this
# fraction of recent observations within SMOOTHING_WINDOW_S. Keeps bbox color
# stable across single-frame mis-detections.
TRACK_MISSING_FRACTION = 0.70
TRACK_MIN_SAMPLES = 8

# Throttle alerts: regardless of which classes change, never emit two alerts
# within this many seconds for the same camera. Stops the per-second alert
# spam when the model flickers between cap-only and cap+colete missing.
ALERT_MIN_INTERVAL_S = 8.0

# Maximum gap between two positive detections of the same class that still
# counts as a continuous "present" streak. A gap longer than this resets
# the streak so the worker has to re-establish presence over the full
# SMOOTHING_WINDOW_S before the bbox flips back to green.
CLASS_STREAK_RESET_GAP_S = 2.5


class PersonEval:
    __slots__ = ("bbox", "present", "missing", "matched")

    def __init__(
        self,
        bbox: tuple[int, int, int, int],
        present: set[str],
        missing: set[str],
        matched: list[Detection],
    ) -> None:
        self.bbox = bbox
        self.present = present
        self.missing = missing
        self.matched = matched


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    iw = max(0, min(ax2, bx2) - max(ax1, bx1))
    ih = max(0, min(ay2, by2) - max(ay1, by1))
    inter = iw * ih
    if inter == 0:
        return 0.0
    union = max(1, (ax2 - ax1) * (ay2 - ay1)) + max(1, (bx2 - bx1) * (by2 - by1)) - inter
    return inter / union


def _bbox_overlap_ratio(
    inner: tuple[int, int, int, int], zone: tuple[int, int, int, int]
) -> float:
    ix1, iy1, ix2, iy2 = inner
    zx1, zy1, zx2, zy2 = zone
    inter_w = max(0, min(ix2, zx2) - max(ix1, zx1))
    inter_h = max(0, min(iy2, zy2) - max(iy1, zy1))
    inter = inter_w * inter_h
    if inter == 0:
        return 0.0
    inner_area = max(1, (ix2 - ix1) * (iy2 - iy1))
    return inter / inner_area


def _evaluate_person(
    person_bbox: tuple[int, int, int, int],
    ppe_dets: list[Detection],
    active: set[str],
) -> tuple["PersonEval", set[str]]:
    """Returns (eval, checkable_classes). Classes not in checkable should be
    treated as undecidable for this person — typically because the body part
    needed to assess them is not visible in frame."""
    px1, py1, px2, py2 = person_bbox
    ph = py2 - py1
    head_visible = (
        py1 > HEAD_VISIBLE_TOP_MARGIN_PX
        and ph >= HEAD_VISIBLE_MIN_PERSON_HEIGHT_PX
    )
    head_zone = (px1, py1, px2, py1 + max(1, int(ph * 0.30)))
    torso_zone = (px1, py1 + int(ph * 0.20), px2, py1 + int(ph * 0.70))

    checkable = set(active)
    if not head_visible:
        checkable.discard("capacete")

    present: set[str] = set()
    matched: list[Detection] = []
    for d in ppe_dets:
        if d.class_name not in active:
            continue
        if d.class_name not in checkable:
            continue
        zone = head_zone if d.class_name == "capacete" else torso_zone
        if _bbox_overlap_ratio(d.bbox, zone) >= PPE_PERSON_MIN_OVERLAP:
            present.add(d.class_name)
            matched.append(d)
    missing = checkable - present
    return PersonEval(person_bbox, present, missing, matched), checkable


def _annotate_per_person(
    frame: NDArray[np.uint8],
    person_evals: list["PersonEval"],
    all_ppe: list[Detection],
    faces: list[Detection],
) -> NDArray[np.uint8]:
    GREEN = (100, 220, 100)
    RED = (40, 40, 230)
    GRAY = (160, 160, 160)
    LABEL_BG_GREEN = (60, 160, 60)
    LABEL_BG_RED = (30, 30, 180)
    LABEL_BG_GRAY = (90, 90, 90)

    out = frame.copy()

    # Only draw internal PPE bboxes for persons that have at least one
    # missing class — when everything is OK the inner labels are visual
    # noise; outer "OK" badge is enough.
    show_internal_for_ids = {
        id(d)
        for ev in person_evals
        if ev.missing
        for d in ev.matched
    }
    for d in all_ppe:
        if id(d) not in show_internal_for_ids:
            continue
        x1, y1, x2, y2 = d.bbox
        cv2.rectangle(out, (x1, y1), (x2, y2), GREEN, 2)
        label = EPI_LABELS_PT.get(d.class_name, d.class_name)
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
        cv2.rectangle(out, (x1, y1 - th - 8), (x1 + tw + 6, y1), LABEL_BG_GREEN, -1)
        cv2.putText(out, label, (x1 + 3, y1 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)

    for ev in person_evals:
        x1, y1, x2, y2 = ev.bbox
        if ev.missing:
            color, bg = RED, LABEL_BG_RED
            missing_lbls = ", ".join(sorted(EPI_LABELS_PT.get(k, k) for k in ev.missing))
            label = f"Sem {missing_lbls}"
        elif ev.present:
            color, bg = GREEN, LABEL_BG_GREEN
            label = "OK"
        else:
            # Track is too young to commit a status — neutral gray.
            color, bg = GRAY, LABEL_BG_GRAY
            label = "Avaliando"
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
        cv2.rectangle(out, (x1, y1 - th - 8), (x1 + tw + 6, y1), bg, -1)
        cv2.putText(out, label, (x1 + 3, y1 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)

    return out


class StreamProcessor:
    def __init__(
        self,
        source: StreamSource,
        detector: SafetyDetector,
        alert_manager: AlertManager,
        owns_source: bool = True,
        camera_id: str | None = None,
    ) -> None:
        self._source = source
        self._detector = detector
        self._alert_manager = alert_manager
        self._owns_source = owns_source
        self._camera_id = camera_id or "unknown"
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
        # Per-class history of (timestamp, detection). Used for temporal smoothing.
        self._detection_history: dict[str, Deque[tuple[float, Detection]]] = {}
        # Person presence smoothed window (timestamps when any detection / face was seen)
        self._person_seen_history: Deque[float] = deque()
        # Per-person tracks: list of {bbox, last_seen, history: deque[(t, frozenset[missing])]}
        self._tracks: list[dict] = []
        # Last alert wall-clock time (monotonic) for global throttling
        self._last_alert_at: float = 0.0
        # Per-camera color palette override. None = use global default in detector.
        self._color_palettes: dict[str, list[tuple[tuple[int, int, int], tuple[int, int, int]]]] | None = None
        self._palette_lock = threading.Lock()

    @property
    def active_epis(self) -> set[str]:
        with self._epi_lock:
            return self._active_epis.copy()

    def set_active_epis(self, epis: set[str]) -> None:
        with self._epi_lock:
            self._active_epis = epis.copy()

    @property
    def color_palettes(self) -> dict[str, list[tuple[tuple[int, int, int], tuple[int, int, int]]]] | None:
        with self._palette_lock:
            return None if self._color_palettes is None else {
                k: list(v) for k, v in self._color_palettes.items()
            }

    def set_color_palettes(
        self,
        palettes: dict[str, list[tuple[tuple[int, int, int], tuple[int, int, int]]]] | None,
    ) -> None:
        with self._palette_lock:
            self._color_palettes = (
                None
                if palettes is None
                else {k: list(v) for k, v in palettes.items()}
            )

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
        if self._owns_source:
            try:
                self._source.start()
            except Exception:
                logger.exception("Failed to start source")
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
        if self._owns_source:
            self._source.stop()
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

            frame = self._source.get_frame()
            if frame is None:
                stream_online.labels(camera_id=self._camera_id).set(0)
                self._stop_event.wait(0.01)
                continue
            stream_online.labels(camera_id=self._camera_id).set(1)

            inf_start = time.monotonic()
            with self._palette_lock:
                palettes = (
                    None if self._color_palettes is None else {
                        k: list(v) for k, v in self._color_palettes.items()
                    }
                )
            detections = self._detector.detect(frame, color_palettes=palettes)
            persons = self._detector.detect_persons(frame)
            inference_latency.observe(time.monotonic() - inf_start)

            with self._epi_lock:
                active = self._active_epis.copy()
            visible_faces = [d for d in detections if d.class_name == FACE_CLASS_KEY]
            ppe_dets = [d for d in detections if d.class_name in EPI_LABELS_PT]

            now = time.monotonic()

            # Per-frame raw evaluation per detected person.
            raw_evals: list[PersonEval] = []
            raw_checkable: list[set[str]] = []
            for pbox in persons:
                ev, ck = _evaluate_person(pbox, ppe_dets, active)
                raw_evals.append(ev)
                raw_checkable.append(ck)

            # Update tracks: match raw_evals against existing tracks by IoU.
            matched_track_ids: set[int] = set()
            for idx, ev in enumerate(raw_evals):
                checkable_now = raw_checkable[idx]
                best_tr = None
                best_iou = TRACK_IOU_THRESHOLD
                for tr in self._tracks:
                    if id(tr) in matched_track_ids:
                        continue
                    iou = _iou(tr["bbox"], ev.bbox)
                    if iou > best_iou:
                        best_iou = iou
                        best_tr = tr
                if best_tr is not None:
                    matched_track_ids.add(id(best_tr))
                    best_tr["bbox"] = ev.bbox
                    best_tr["last_seen"] = now
                    best_tr["last_matched_dets"] = ev.matched
                    best_tr["last_checkable"] = checkable_now
                    last_det_per_cls = best_tr.setdefault("last_det_per_cls", {})
                    for d in ev.matched:
                        last_det_per_cls[d.class_name] = d
                    for cls in active:
                        seen_now = cls in ev.present
                        last = best_tr["last_class_seen"].get(cls)
                        streak_start = best_tr["class_streak_start"].get(cls)
                        if seen_now:
                            if last is None or (now - last) > CLASS_STREAK_RESET_GAP_S:
                                streak_start = now
                            best_tr["class_streak_start"][cls] = streak_start
                            best_tr["last_class_seen"][cls] = now
                else:
                    # No status snapshot. New tracks start fully UNDEFINED
                    # for every active class. A status only commits after
                    # SMOOTHING_WINDOW_S of consistent evidence.
                    new_tr = {
                        "bbox": ev.bbox,
                        "first_seen": now,
                        "last_seen": now,
                        "last_class_seen": {cls: now for cls in ev.present},
                        "class_streak_start": {cls: now for cls in ev.present},
                        "class_status": {},  # undefined
                        "last_matched_dets": ev.matched,
                        "last_det_per_cls": {d.class_name: d for d in ev.matched},
                        "last_checkable": checkable_now,
                        # was_compliant=True default so the first commit
                        # to "missing" cleanly fires exactly one alert via
                        # the OK -> NOT-OK edge logic below.
                        "was_compliant": True,
                    }
                    self._tracks.append(new_tr)

            # Drop stale tracks
            self._tracks = [
                tr for tr in self._tracks if (now - tr["last_seen"]) <= TRACK_STALE_S
            ]

            # Symmetric smoothing per track per class. Status only commits
            # after SMOOTHING_WINDOW_S of consistent evidence, in either
            # direction. Internal PPE bboxes drawn for the person follow
            # the same smoothed status so they cannot disagree with the
            # outer person bbox color.
            person_evals: list[PersonEval] = []
            triggered_alerts: list[tuple[set[str], list[Detection]]] = []
            for tr in self._tracks:
                age = now - tr["first_seen"]
                cstatus: dict[str, str] = tr.setdefault("class_status", {})
                checkable_now: set[str] = tr.get("last_checkable", set(active))

                for cls in active:
                    last_t = tr["last_class_seen"].get(cls)
                    streak_start = tr["class_streak_start"].get(cls)
                    current = cstatus.get(cls)

                    if current == "present":
                        if last_t is None or (now - last_t) >= SMOOTHING_TO_MISSING_S:
                            cstatus[cls] = "missing"
                    elif current == "missing":
                        if (
                            streak_start is not None
                            and last_t is not None
                            and (now - last_t) <= CLASS_STREAK_RESET_GAP_S
                            and (now - streak_start) >= SMOOTHING_TO_PRESENT_S
                        ):
                            cstatus[cls] = "present"
                    else:
                        # Undefined first commit:
                        #   * "present" earns its way in with TO_PRESENT_S of streak
                        #   * "missing" only after TO_MISSING_S without any sighting
                        if (
                            streak_start is not None
                            and last_t is not None
                            and (now - last_t) <= CLASS_STREAK_RESET_GAP_S
                            and (now - streak_start) >= SMOOTHING_TO_PRESENT_S
                        ):
                            cstatus[cls] = "present"
                        elif last_t is None and age >= SMOOTHING_TO_MISSING_S:
                            cstatus[cls] = "missing"

                missing = {
                    cls for cls in active
                    if cstatus.get(cls) == "missing" and cls in checkable_now
                }
                present = {cls for cls in active if cstatus.get(cls) == "present"}
                # Internal bboxes drawn = smoothed-present detections only.
                last_det = tr.get("last_det_per_cls", {})
                smoothed_matched = [last_det[c] for c in present if c in last_det]

                person_evals.append(
                    PersonEval(
                        bbox=tr["bbox"],
                        present=present,
                        missing=missing,
                        matched=smoothed_matched,
                    )
                )

                is_compliant_now = not missing
                was_compliant = tr.get("was_compliant", True)
                if was_compliant and not is_compliant_now:
                    triggered_alerts.append((set(missing), list(smoothed_matched)))
                tr["was_compliant"] = is_compliant_now

            scene_missing: set[str] = set()
            for ev in person_evals:
                scene_missing |= ev.missing

            cutoff = now - SMOOTHING_WINDOW_S
            if persons or ppe_dets or visible_faces:
                self._person_seen_history.append(now)
            while self._person_seen_history and self._person_seen_history[0] < cutoff:
                self._person_seen_history.popleft()

            # Build the annotated frame up-front so we can persist both raw
            # and annotated versions when an alert fires below.
            annotated = _annotate_per_person(
                frame, person_evals, ppe_dets, visible_faces
            )

            for miss_set, matched_dets in triggered_alerts:
                missing_labels = sorted(EPI_LABELS_PT.get(k, k) for k in miss_set)
                labels = ", ".join(missing_labels)
                rep_conf = max(
                    (d.confidence for d in (matched_dets or ppe_dets)), default=0.5
                )
                # Snapshot every detection currently visible in the scene as
                # a JSON-friendly record. RetrainingExporter materialises
                # YOLO labels from these later.
                bbox_records = [
                    {
                        "class_name": d.class_name,
                        "bbox": [int(v) for v in d.bbox],
                        "confidence": float(d.confidence),
                    }
                    for d in ppe_dets
                ]
                self._alert_manager.add_alert(
                    f"{labels} ausente(s)",
                    rep_conf,
                    annotated,
                    missing_epis=missing_labels,
                    raw_frame=frame,
                    detected_bboxes=bbox_records,
                )
                self._last_alert_at = now
            self._last_missing_set = frozenset(scene_missing)

            if person_evals:
                compliant_count = sum(1 for ev in person_evals if not ev.missing)
                is_compliant = compliant_count == len(person_evals)
            else:
                is_compliant = True

            self._alert_manager.record_frame(compliant=is_compliant)

            success, buffer = cv2.imencode(".jpg", annotated)
            if success:
                jpeg_bytes: bytes = buffer.tobytes()
                with self._lock:
                    self._current_jpeg = jpeg_bytes

            frame_count += 1
            elapsed = time.monotonic() - fps_timer
            if elapsed >= 1.0:
                fps_value = round(frame_count / elapsed, 1)
                with self._lock:
                    self._fps = fps_value
                stream_fps.labels(camera_id=self._camera_id).set(fps_value)
                frame_count = 0
                fps_timer = time.monotonic()

            # FPS throttling: sleep remaining time to hit TARGET_FPS
            processing_time = time.monotonic() - loop_start
            sleep_time = FRAME_INTERVAL - processing_time
            if sleep_time > 0:
                self._stop_event.wait(sleep_time)

        logger.debug("Process loop exited")
