"""Backwards-compatible alias.

`CameraManager` was the original webcam wrapper. It is now a thin subclass
of `LocalCameraSource` that reads defaults from settings, so the global
single-camera webcam path keeps working while new code uses `StreamSource`
directly.
"""

from __future__ import annotations

from app.config import settings
from app.sources import LocalCameraSource


class CameraManager(LocalCameraSource):
    def __init__(self) -> None:
        super().__init__(
            index=settings.CAMERA_INDEX,
            width=settings.CAMERA_WIDTH,
            height=settings.CAMERA_HEIGHT,
        )
