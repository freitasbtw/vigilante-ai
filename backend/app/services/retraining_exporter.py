"""Export reviewed alerts as YOLO-format training samples.

When an admin/supervisor labels an alert as `correct` or `false_positive`,
we copy the raw frame and emit a sibling `.txt` label file under
`RETRAINING_EXPORT_PATH/{confirmed,rejected}/`. A separate merge script
later pulls these into the canonical `ml/datasets/canteiro/` split.

Design notes:
- Idempotent: re-exporting the same alert overwrites prior files. Safe to
  call repeatedly when an admin flips their decision.
- Class indices follow `ml/configs/*.yaml` (helmet=0, vest=1). Keep this
  map in sync if the YOLO config grows new classes.
- `false_positive` exports an EMPTY label file. The frame becomes a
  negative sample — the model learns there is no PPE violation in this
  frame. Frames where no PPE was visible at all should not be exported
  for retraining (filtered upstream by callers).
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any, Iterable

import cv2
import numpy as np

from app.config import settings
from app.db.entities import Alert
from app.storage import BlobStore

logger = logging.getLogger(__name__)


# Class name → YOLO class index. Matches `ml/configs/ppe-cctv-v1.yaml`.
_CLASS_INDEX: dict[str, int] = {
    "capacete": 0,
    "colete": 1,
}


class RetrainingExporter:
    def __init__(self, blob_store: BlobStore, root: str | Path | None = None) -> None:
        self._blob_store = blob_store
        self._root = Path(root or settings.RETRAINING_EXPORT_PATH).resolve()

    def export(self, alert: Alert) -> Path | None:
        """Materialise an alert's raw frame + YOLO label under the right
        decision subfolder. Returns the directory where files landed, or
        None when the alert has no usable raw frame on disk."""
        decision = self._decision_for(alert.feedback)
        if decision is None:
            logger.debug("Alert %s feedback=%r — skipping export", alert.id, alert.feedback)
            return None
        if not alert.frame_raw_path:
            logger.warning(
                "Alert %s has no frame_raw_path — cannot export for retraining",
                alert.id,
            )
            return None

        raw_bytes = self._blob_store.load_bytes(alert.frame_raw_path)
        if raw_bytes is None:
            logger.warning(
                "Alert %s raw frame missing on disk: %s",
                alert.id,
                alert.frame_raw_path,
            )
            return None

        out_dir = self._root / decision
        out_dir.mkdir(parents=True, exist_ok=True)
        img_out = out_dir / f"{alert.id}.jpg"
        lbl_out = out_dir / f"{alert.id}.txt"
        img_out.write_bytes(raw_bytes)

        if decision == "rejected":
            # Empty label = "this frame contains no helmet/vest worth alerting on".
            lbl_out.write_text("")
            return out_dir

        # Confirmed — emit YOLO labels for the detections that triggered
        # the alert. Confidence is dropped; YOLO labels are class + bbox.
        height, width = _image_dimensions(raw_bytes)
        if width <= 0 or height <= 0:
            logger.warning("Alert %s raw frame has invalid dims; skipping label", alert.id)
            lbl_out.write_text("")
            return out_dir

        lines = list(_iter_yolo_lines(alert.detected_bboxes or [], width, height))
        lbl_out.write_text("\n".join(lines) + ("\n" if lines else ""))
        return out_dir

    @staticmethod
    def _decision_for(feedback: str | None) -> str | None:
        if feedback == "correct":
            return "confirmed"
        if feedback == "false_positive":
            return "rejected"
        return None


def _image_dimensions(jpeg_bytes: bytes) -> tuple[int, int]:
    arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return (0, 0)
    h, w = img.shape[:2]
    return (h, w)


def _iter_yolo_lines(
    bboxes: Iterable[dict[str, Any]], width: int, height: int
) -> Iterable[str]:
    for record in bboxes:
        class_name = record.get("class_name")
        bbox = record.get("bbox")
        idx = _CLASS_INDEX.get(class_name) if isinstance(class_name, str) else None
        if idx is None or not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            continue
        x1, y1, x2, y2 = (float(v) for v in bbox)
        x1, x2 = sorted((x1, x2))
        y1, y2 = sorted((y1, y2))
        cx = (x1 + x2) / 2.0 / width
        cy = (y1 + y2) / 2.0 / height
        bw = (x2 - x1) / width
        bh = (y2 - y1) / height
        if bw <= 0 or bh <= 0:
            continue
        yield f"{idx} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}"
