"""Shared test fixtures for Vigilante.AI backend tests."""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock

import numpy as np
import pytest

from app.alerts import AlertManager
from app.camera import CameraManager
from app.detector import SafetyDetector
from app.models import Detection
from app.stream import StreamProcessor


@pytest.fixture()
def mock_camera() -> CameraManager:
    """A mock CameraManager that yields fake numpy frames without a real webcam."""
    camera = MagicMock(spec=CameraManager)
    fake_frame = np.zeros((480, 640, 3), dtype=np.uint8)

    type(camera).is_running = PropertyMock(return_value=True)
    camera.get_frame.return_value = fake_frame
    camera.start.return_value = None
    camera.stop.return_value = None

    return camera


@pytest.fixture()
def mock_detector() -> SafetyDetector:
    """A mock SafetyDetector that returns empty detections without loading a model."""
    detector = MagicMock(spec=SafetyDetector)

    type(detector).is_loaded = PropertyMock(return_value=True)
    detector.load_model.return_value = None
    detector.detect.return_value = []
    detector.annotate_frame.side_effect = lambda frame, _dets, missing_epis=None: frame

    return detector


@pytest.fixture()
def alert_manager() -> AlertManager:
    """Fresh AlertManager instance."""
    return AlertManager()


@pytest.fixture()
def stream_processor(
    mock_camera: CameraManager,
    mock_detector: SafetyDetector,
    alert_manager: AlertManager,
) -> StreamProcessor:
    """StreamProcessor wired to mock camera and detector."""
    return StreamProcessor(mock_camera, mock_detector, alert_manager)
