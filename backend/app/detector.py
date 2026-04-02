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

# 6-class PPE model mapping: class_id -> internal Portuguese key
_ALL_EPI_CLASSES: dict[int, str] = {
    0: "luvas",
    1: "colete",
    2: "protecao_ocular",
    3: "capacete",
    4: "mascara",
    5: "calcado_seguranca",
}

EPI_CLASSES: dict[int, str] = _ALL_EPI_CLASSES.copy()

# Portuguese display labels for bounding box annotation
EPI_LABELS_PT: dict[str, str] = {
    "luvas": "Luvas",
    "colete": "Colete",
    "protecao_ocular": "Protecao ocular",
    "capacete": "Capacete",
    "mascara": "Mascara",
    "calcado_seguranca": "Calcado de seguranca",
}

FACE_CLASS_KEY = "rosto"
FACE_LABEL_PT = "Rosto"

# Portuguese alert labels for missing EPI violations
EPI_ALERT_LABELS: dict[str, str] = {
    "luvas": "Luvas ausentes",
    "colete": "Colete ausente",
    "protecao_ocular": "Protecao ocular ausente",
    "capacete": "Capacete ausente",
    "mascara": "Mascara ausente",
    "calcado_seguranca": "Calcado de seguranca ausente",
}

GREEN = (0, 255, 0)
LABEL_BG = (60, 160, 60)
RED = (0, 0, 255)
BLUE = (220, 140, 60)
FACE_LABEL_BG = (190, 110, 40)


class SafetyDetector:
    def __init__(self) -> None:
        self._model: YOLO | None = None
        cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        self._face_cascade = cv2.CascadeClassifier(str(cascade_path))

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def load_model(self) -> None:
        self._model = YOLO(settings.MODEL_PATH)
        model_classes: dict[int, str] = self._model.names
        class_names = set(model_classes.values())
        epi_values = set(EPI_CLASSES.values())

        # Validate model has expected PPE classes (by checking original English names)
        logger.info(
            "PPE model loaded with %d classes: %s",
            len(model_classes),
            class_names,
        )

    def detect(self, frame: NDArray[np.uint8]) -> list[Detection]:
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

                    detections.append(Detection(class_key, confidence, (x1, y1, x2, y2)))

        detections.extend(self._detect_faces(frame))

        return detections

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
                label_text = EPI_ALERT_LABELS.get(
                    epi_key,
                    f"{EPI_LABELS_PT.get(epi_key, epi_key)} ausente",
                )
                cv2.putText(
                    annotated, label_text,
                    (circle_x + 18, cy + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, RED, 2,
                )

        return annotated
