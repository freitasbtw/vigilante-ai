"""Tests for StreamProcessor lifecycle, thread safety, FPS throttling, and EPI filtering.

Covers: BUG-01 (stop/start crash), BUG-02 (thread safety), MODL-03 (FPS cap),
        CONF-03 (EPI filter in stream processing).
"""

from __future__ import annotations

import threading
import time

import cv2
import numpy as np
import pytest

from app.models import Detection
from app.stream import StreamProcessor


class TestStopStartLifecycle:
    """BUG-01: Stop then start must not crash or freeze."""

    def test_stop_start_lifecycle(self, stream_processor: StreamProcessor) -> None:
        """StreamProcessor can start, stop, then start again without error.

        After stop, generate_mjpeg yields nothing.
        After restart, generate_mjpeg yields frames.
        """
        # First start
        stream_processor.start()
        assert stream_processor.is_running
        time.sleep(0.2)

        # Stop
        stream_processor.stop()
        assert not stream_processor.is_running

        # After stop, generator should not yield anything
        gen = stream_processor.generate_mjpeg()
        frame = next(gen, None)
        assert frame is None, "Generator should yield nothing after stop"

        # Restart
        stream_processor.start()
        assert stream_processor.is_running
        time.sleep(0.2)

        # After restart, generator should yield frames
        gen2 = stream_processor.generate_mjpeg()
        frame2 = next(gen2, None)
        assert frame2 is not None, "Generator should yield frames after restart"

        # Cleanup
        stream_processor.stop()


class TestMjpegGeneratorLifecycle:
    """BUG-01 extended: generators from previous sessions must exit cleanly."""

    def test_mjpeg_generator_exits_on_stop(
        self, stream_processor: StreamProcessor
    ) -> None:
        """A generator created before stop() exits its loop after stop()."""
        stream_processor.start()
        time.sleep(0.1)

        gen = stream_processor.generate_mjpeg()
        # Consume one frame to confirm it's working
        first = next(gen, None)
        assert first is not None

        # Stop the processor
        stream_processor.stop()

        # The generator should now stop yielding within a reasonable time.
        # We give it up to 1 second (it should stop almost immediately with Event).
        deadline = time.monotonic() + 1.0
        stopped = False
        for _ in gen:
            if time.monotonic() > deadline:
                break
        else:
            stopped = True

        assert stopped, "Generator did not exit after stop() within timeout"

    def test_mjpeg_generator_epoch_mismatch(
        self, stream_processor: StreamProcessor
    ) -> None:
        """A generator from epoch N stops yielding after stop/start increments epoch."""
        stream_processor.start()
        time.sleep(0.1)

        gen = stream_processor.generate_mjpeg()
        first = next(gen, None)
        assert first is not None

        # Stop and restart (epoch should increment)
        stream_processor.stop()
        stream_processor.start()
        time.sleep(0.1)

        # Old generator should not yield frames from new epoch
        stale_frame = next(gen, None)
        assert stale_frame is None, (
            "Old generator should not yield frames after epoch change"
        )

        stream_processor.stop()


class TestThreadSafety:
    """BUG-02: Concurrent reads must not raise exceptions."""

    def test_thread_safety(self, stream_processor: StreamProcessor) -> None:
        """Concurrent reads of fps, uptime, and get_jpeg_frame while running."""
        stream_processor.start()
        time.sleep(0.1)

        errors: list[Exception] = []

        def reader() -> None:
            try:
                for _ in range(100):
                    _ = stream_processor.fps
                    _ = stream_processor.uptime
                    _ = stream_processor.get_jpeg_frame()
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=reader) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        stream_processor.stop()
        assert not errors, f"Thread safety errors: {errors}"


class TestFpsThrottle:
    """MODL-03: Process loop must run at ~25 FPS, not unlimited."""

    def test_fps_throttle(self, stream_processor: StreamProcessor) -> None:
        """Measure actual frame count over ~1 second, assert 18-32 range."""
        call_count = 0
        original_detect = stream_processor._detector.detect

        def counting_detect(frame):  # type: ignore[no-untyped-def]
            nonlocal call_count
            call_count += 1
            return []

        stream_processor._detector.detect = counting_detect  # type: ignore[assignment]

        stream_processor.start()
        time.sleep(1.2)  # Run for slightly over 1 second
        stream_processor.stop()

        assert 18 <= call_count <= 32, (
            f"Expected ~25 FPS, got {call_count} frames in ~1.2s. "
            f"FPS throttling may not be working."
        )


class TestEpiFilter:
    """CONF-03: EPI filter in stream processing pipeline."""

    def test_epi_filter(self, stream_processor: StreamProcessor) -> None:
        """When active_epis={'capacete'}, only capacete detections pass through."""
        # Configure mock detector to return capacete + luvas detections
        detections = [
            Detection(class_name="capacete", confidence=0.9, bbox=(10, 20, 100, 200)),
            Detection(class_name="luvas", confidence=0.85, bbox=(50, 60, 150, 250)),
        ]
        stream_processor._detector.detect.return_value = detections  # type: ignore[attr-defined]

        # Track what gets annotated
        annotated_calls: list[list[Detection]] = []
        original_annotate = stream_processor._detector.annotate_frame

        def tracking_annotate(frame, dets, missing_epis=None):  # type: ignore[no-untyped-def]
            annotated_calls.append(list(dets))
            return frame

        stream_processor._detector.annotate_frame = tracking_annotate  # type: ignore[assignment]

        # Set active EPIs to capacete only
        stream_processor.set_active_epis({"capacete"})
        stream_processor.start()
        time.sleep(0.2)
        stream_processor.stop()

        # Should have at least one annotate call
        assert len(annotated_calls) > 0, "Expected at least one annotate call"

        # All annotate calls should only contain capacete
        for call_dets in annotated_calls:
            for det in call_dets:
                assert det.class_name == "capacete", (
                    f"Expected only capacete, got {det.class_name}"
                )

    def test_epi_filter_empty(self, stream_processor: StreamProcessor) -> None:
        """When active_epis is empty, no detections pass through."""
        detections = [
            Detection(class_name="capacete", confidence=0.9, bbox=(10, 20, 100, 200)),
        ]
        stream_processor._detector.detect.return_value = detections  # type: ignore[attr-defined]

        annotated_calls: list[list[Detection]] = []

        def tracking_annotate(frame, dets, missing_epis=None):  # type: ignore[no-untyped-def]
            annotated_calls.append(list(dets))
            return frame

        stream_processor._detector.annotate_frame = tracking_annotate  # type: ignore[assignment]

        # Empty active EPIs
        stream_processor.set_active_epis(set())
        stream_processor.start()
        time.sleep(0.2)
        stream_processor.stop()

        assert len(annotated_calls) > 0
        for call_dets in annotated_calls:
            assert len(call_dets) == 0, "Expected zero detections when active_epis is empty"

    def test_epi_filter_live_toggle(self, stream_processor: StreamProcessor) -> None:
        """Changing active_epis mid-stream takes effect on the next frame."""
        detections = [
            Detection(class_name="capacete", confidence=0.9, bbox=(10, 20, 100, 200)),
            Detection(class_name="luvas", confidence=0.85, bbox=(50, 60, 150, 250)),
        ]
        stream_processor._detector.detect.return_value = detections  # type: ignore[attr-defined]

        annotated_calls: list[list[Detection]] = []

        def tracking_annotate(frame, dets, missing_epis=None):  # type: ignore[no-untyped-def]
            annotated_calls.append(list(dets))
            return frame

        stream_processor._detector.annotate_frame = tracking_annotate  # type: ignore[assignment]

        # Start with capacete only
        stream_processor.set_active_epis({"capacete"})
        stream_processor.start()
        time.sleep(0.15)

        # Toggle to luvas only
        stream_processor.set_active_epis({"luvas"})
        time.sleep(0.15)
        stream_processor.stop()

        # Should see luvas-only frames after toggle
        # Find the last few calls -- they should contain luvas but not capacete
        last_calls = annotated_calls[-3:]
        has_luvas_only = any(
            all(d.class_name == "luvas" for d in call_dets) and len(call_dets) > 0
            for call_dets in last_calls
        )
        assert has_luvas_only, "After toggle, should see luvas-only frames"


class TestMissingEpiAlerts:
    """Alert generation for missing EPIs in stream processing."""

    def test_alert_uses_portuguese_label(self, stream_processor: StreamProcessor, alert_manager) -> None:  # type: ignore[no-untyped-def]
        """Alerts use Portuguese alert labels (e.g., 'Capacete ausente')."""
        # Only luvas detected, but capacete+luvas are active -> capacete is missing
        detections = [
            Detection(class_name="luvas", confidence=0.9, bbox=(10, 20, 100, 200)),
        ]
        stream_processor._detector.detect.return_value = detections  # type: ignore[attr-defined]

        def passthrough_annotate(frame, dets, missing_epis=None):  # type: ignore[no-untyped-def]
            return frame

        stream_processor._detector.annotate_frame = passthrough_annotate  # type: ignore[assignment]

        stream_processor.set_active_epis({"capacete", "luvas"})
        stream_processor.start()
        time.sleep(0.3)

        # Read alerts BEFORE stop (stop resets alerts per CONTEXT.md decision)
        alerts = alert_manager.get_alerts()
        stream_processor.stop()

        # Should have at least one alert for missing capacete
        assert len(alerts) > 0, "Expected alert for missing capacete"
        alert_types = {a.violation_type for a in alerts}
        assert "Capacete ausente" in alert_types, (
            f"Expected 'Capacete ausente' in alerts, got {alert_types}"
        )

    def test_missing_epi_alert(self, stream_processor: StreamProcessor, alert_manager) -> None:  # type: ignore[no-untyped-def]
        """When one active EPI is detected but another is absent, alert for the missing one."""
        detections = [
            Detection(class_name="capacete", confidence=0.9, bbox=(10, 20, 100, 200)),
        ]
        stream_processor._detector.detect.return_value = detections  # type: ignore[attr-defined]

        def passthrough_annotate(frame, dets, missing_epis=None):  # type: ignore[no-untyped-def]
            return frame

        stream_processor._detector.annotate_frame = passthrough_annotate  # type: ignore[assignment]

        stream_processor.set_active_epis({"capacete", "luvas"})
        stream_processor.start()
        time.sleep(0.3)

        # Read alerts BEFORE stop (stop resets alerts)
        alerts = alert_manager.get_alerts()
        stream_processor.stop()

        alert_types = {a.violation_type for a in alerts}
        assert "Luvas ausentes" in alert_types, (
            f"Expected 'Luvas ausentes' in alerts, got {alert_types}"
        )

    def test_no_alert_empty_frame(self, stream_processor: StreamProcessor, alert_manager) -> None:  # type: ignore[no-untyped-def]
        """When zero EPIs are detected (no person proxy), no missing EPI alerts."""
        # No detections at all
        stream_processor._detector.detect.return_value = []  # type: ignore[attr-defined]

        def passthrough_annotate(frame, dets, missing_epis=None):  # type: ignore[no-untyped-def]
            return frame

        stream_processor._detector.annotate_frame = passthrough_annotate  # type: ignore[assignment]

        stream_processor.set_active_epis({"capacete", "luvas"})
        stream_processor.start()
        time.sleep(0.2)
        stream_processor.stop()

        alerts = alert_manager.get_alerts()
        assert len(alerts) == 0, (
            f"Expected no alerts when no EPIs detected, got {len(alerts)}"
        )
