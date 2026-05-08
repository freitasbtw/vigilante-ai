from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from numpy.typing import NDArray
from ultralytics import YOLO  # type: ignore[attr-defined]

from app.config import settings
from app.models import Detection

logger = logging.getLogger(__name__)

# 2-class PPE model — canteiro civil (capacete + colete alta visibilidade).
# Indices match the YOLO weights produced by ml/train.py + ml/configs/ppe-cctv-v1.yaml.
_ALL_EPI_CLASSES: dict[int, str] = {
    0: "capacete",
    1: "colete",
}

MVP_EPI_KEYS = {"capacete", "colete"}

EPI_CLASSES: dict[int, str] = dict(_ALL_EPI_CLASSES)

EPI_LABELS_PT: dict[str, str] = {
    "capacete": "Capacete",
    "colete": "Colete",
}

FACE_CLASS_KEY = "rosto"
FACE_LABEL_PT = "Rosto"

# HSV color palettes for PPE post-filter. OpenCV HSV: H 0-180, S/V 0-255.
# A detection is kept only if at least PPE_COLOR_MIN_MATCH_RATIO of its
# bbox interior pixels fall inside one of these ranges. Reduces FPs where
# the model latches onto neutral construction-site artifacts (planks,
# tarp folds) that have no PPE color signature.
PPE_COLOR_PALETTES_HSV: dict[str, list[tuple[tuple[int, int, int], tuple[int, int, int]]]] = {
    "capacete": [
        ((0, 0, 190), (180, 50, 255)),     # white / off-white
        ((18, 80, 120), (35, 255, 255)),   # yellow / lime
        ((5, 100, 100), (18, 255, 255)),   # orange
        ((0, 100, 80), (10, 255, 255)),    # red (low hue side)
        ((170, 100, 80), (180, 255, 255)), # red (high hue side)
        ((85, 60, 80), (130, 255, 255)),   # blue
    ],
    "colete": [
        ((25, 80, 130), (60, 255, 255)),   # HiVis yellow-green
        ((5, 120, 130), (20, 255, 255)),   # HiVis orange
    ],
}

# Portuguese alert labels for missing EPI violations
EPI_ALERT_LABELS: dict[str, str] = {
    "capacete": "Capacete ausente",
    "colete": "Colete ausente",
}

GREEN = (100, 220, 100)
LABEL_BG = (60, 160, 60)
RED = (0, 0, 255)
BLUE = (220, 140, 60)
FACE_LABEL_BG = (190, 110, 40)


class SafetyDetector:
    def __init__(self) -> None:
        self._model: YOLO | None = None
        self._person_model: YOLO | None = None
        cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        self._face_cascade = cv2.CascadeClassifier(str(cascade_path))

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def load_model(self) -> None:
        self._model = YOLO(settings.MODEL_PATH)
        model_classes: dict[int, str] = self._model.names
        class_names = set(model_classes.values())

        logger.info(
            "PPE model loaded with %d classes: %s",
            len(model_classes),
            class_names,
        )

        # COCO general-purpose model for person detection. Used to enforce
        # PPE compliance per-person instead of scene-level — without this we
        # would treat one helmet detection as covering everyone in frame.
        try:
            self._person_model = YOLO(settings.PERSON_MODEL_PATH)
            logger.info("Person model loaded: %s", settings.PERSON_MODEL_PATH)
        except Exception as exc:
            logger.warning("Failed to load person model (%s); per-person enforcement disabled", exc)
            self._person_model = None

    def detect_persons(self, frame: NDArray[np.uint8]) -> list[tuple[int, int, int, int]]:
        if self._person_model is None:
            return []
        h, w = frame.shape[:2]
        longest = max(h, w)
        scale = min(settings.PERSON_INPUT_SIZE / longest, 1.0)
        infer_frame = (
            cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
            if scale < 1.0
            else frame
        )
        inv = 1.0 / scale if scale > 0 else 1.0
        results: Any = self._person_model(
            infer_frame,
            conf=settings.PERSON_CONFIDENCE_THRESHOLD,
            classes=[0],  # COCO class 0 = person
            verbose=False,
            imgsz=settings.PERSON_INPUT_SIZE,
        )
        boxes: list[tuple[int, int, int, int]] = []
        frame_area = float(h * w)
        for r in results:
            if r.boxes is None:
                continue
            for b in r.boxes:
                x1, y1, x2, y2 = (int(v * inv) for v in b.xyxy[0].tolist())
                bw = max(1, x2 - x1)
                bh = max(1, y2 - y1)
                # Reject squat / tiny bboxes — workers in CCTV are upright,
                # filters out planks, equipment, shadow blobs misclassified.
                if (bh / bw) < settings.PERSON_MIN_ASPECT_RATIO:
                    continue
                if (bw * bh) / frame_area < settings.PERSON_MIN_AREA_RATIO:
                    continue
                boxes.append((x1, y1, x2, y2))
        return boxes

    def detect(
        self,
        frame: NDArray[np.uint8],
        color_palettes: dict[str, list[tuple[tuple[int, int, int], tuple[int, int, int]]]] | None = None,
    ) -> list[Detection]:
        detections: list[Detection] = []

        if self._model is not None:
            frame_height, frame_width = frame.shape[:2]
            longest_side = max(frame_height, frame_width)
            scale = min(settings.MODEL_INPUT_SIZE / longest_side, 1.0)
            if scale < 1.0:
                infer_frame = cv2.resize(
                    frame,
                    (int(frame_width * scale), int(frame_height * scale)),
                    interpolation=cv2.INTER_AREA,
                )
            else:
                infer_frame = frame

            results: Any = self._model(
                infer_frame,
                conf=settings.CONFIDENCE_THRESHOLD,
                verbose=False,
                imgsz=settings.MODEL_INPUT_SIZE,
            )

            inv_scale = 1.0 / scale if scale > 0 else 1.0
            for result in results:
                if result.boxes is None:
                    continue
                for box in result.boxes:
                    class_id = int(box.cls[0].item())
                    confidence = float(box.conf[0].item())
                    x1, y1, x2, y2 = (int(v * inv_scale) for v in box.xyxy[0].tolist())

                    class_key = EPI_CLASSES.get(class_id)
                    if class_key is None:
                        continue

                    # Per-class confidence floor (helmet stricter than vest).
                    class_floor = (
                        settings.HELMET_CONFIDENCE_THRESHOLD
                        if class_key == "capacete"
                        else settings.VEST_CONFIDENCE_THRESHOLD
                        if class_key == "colete"
                        else settings.CONFIDENCE_THRESHOLD
                    )
                    if confidence < class_floor:
                        continue

                    # Color filter only applies when the camera has an
                    # explicit per-class palette set by the user. Default
                    # behaviour: trust YOLO + confidence threshold, no
                    # color rejection (avoids killing legitimate vests
                    # that fall outside hand-tuned ranges).
                    if (
                        color_palettes
                        and class_key in color_palettes
                        and not self._color_matches(
                            frame, (x1, y1, x2, y2), class_key, color_palettes
                        )
                    ):
                        continue

                    detections.append(Detection(class_key, confidence, (x1, y1, x2, y2)))

        if settings.FACE_DETECTION_ENABLED:
            detections.extend(self._detect_faces(frame))

        return detections

    def _color_matches(
        self,
        frame: NDArray[np.uint8],
        bbox: tuple[int, int, int, int],
        class_key: str,
        custom_palettes: dict[str, list[tuple[tuple[int, int, int], tuple[int, int, int]]]] | None = None,
    ) -> bool:
        if custom_palettes and class_key in custom_palettes:
            palette = custom_palettes[class_key]
        else:
            palette = PPE_COLOR_PALETTES_HSV.get(class_key)
        if not palette:
            return True
        x1, y1, x2, y2 = bbox
        h, w = frame.shape[:2]
        x1 = max(0, min(x1, w - 1))
        x2 = max(0, min(x2, w))
        y1 = max(0, min(y1, h - 1))
        y2 = max(0, min(y2, h))
        if x2 <= x1 or y2 <= y1:
            return False
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return False
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        match_total = 0
        for lo, hi in palette:
            mask = cv2.inRange(hsv, np.array(lo, dtype=np.uint8), np.array(hi, dtype=np.uint8))
            match_total += int(np.count_nonzero(mask))
        ratio = match_total / float(crop.shape[0] * crop.shape[1])
        return ratio >= settings.PPE_COLOR_MIN_MATCH_RATIO

    def _detect_faces(self, frame: NDArray[np.uint8]) -> list[Detection]:
        if self._face_cascade.empty():
            return []

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        min_size = max(settings.FACE_MIN_SIZE, min(frame.shape[0], frame.shape[1]) // 10)
        faces = self._face_cascade.detectMultiScale(
            gray,
            scaleFactor=settings.FACE_SCALE_FACTOR,
            minNeighbors=settings.FACE_MIN_NEIGHBORS,
            minSize=(min_size, min_size),
        )

        return [
            Detection(FACE_CLASS_KEY, 0.0, (int(x), int(y), int(x + w), int(y + h)))
            for x, y, w, h in faces
        ]

    def annotate_frame(
        self,
        frame: NDArray[np.uint8],
        detections: list[Detection],
        missing_epis: set[str] | None = None,
    ) -> NDArray[np.uint8]:
        annotated = frame.copy()
        for det in detections:
            x1, y1, x2, y2 = det.bbox
            if det.class_name == FACE_CLASS_KEY:
                label = FACE_LABEL_PT
                color = BLUE
                label_bg = FACE_LABEL_BG
            else:
                label = EPI_LABELS_PT.get(det.class_name, det.class_name)
                color = GREEN
                label_bg = LABEL_BG

            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
            cv2.rectangle(annotated, (x1, y1 - th - 8), (x1 + tw + 4, y1), label_bg, -1)
            cv2.putText(
                annotated, label, (x1 + 2, y1 - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2,
            )

        if missing_epis:
            if detections:
                # Position relative to detected bounding boxes
                ref_x2 = max(d.bbox[2] for d in detections)
                ref_y1 = min(d.bbox[1] for d in detections)
                circle_x = ref_x2 + 30
                start_y = ref_y1 + 20
            else:
                # No detections — draw in top-left corner
                circle_x = 30
                start_y = 30

            for i, epi_key in enumerate(sorted(missing_epis)):
                cy = start_y + i * 35
                cv2.circle(annotated, (circle_x, cy), 10, RED, -1)
                label_text = EPI_LABELS_PT.get(epi_key, epi_key)
                cv2.putText(
                    annotated, f"{label_text} ausente",
                    (circle_x + 18, cy + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, RED, 2,
                )

        return annotated
