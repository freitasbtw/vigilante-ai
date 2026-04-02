from typing import Any, cast

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse

from app.alerts import AlertManager
from app.camera import CameraManager
from app.config import settings
from app.detector import EPI_CLASSES, EPI_LABELS_PT, SafetyDetector
from app.schemas import (
    AlertListResponse,
    AlertResponse,
    ClearAlertsResponse,
    EPIConfigRequest,
    EPIConfigResponse,
    EPIItem,
    StatsResponse,
    ViolationTimelineEntry,
)
from app.security import enforce_rate_limit, require_api_key
from app.stream import StreamProcessor

app = FastAPI(title="Vigilante.AI", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

camera = CameraManager()
detector = SafetyDetector()
alert_manager = AlertManager()
stream_processor = StreamProcessor(camera, detector, alert_manager)
_PROTECTED_ENDPOINT_DEPENDENCIES = [
    Depends(require_api_key),
    Depends(enforce_rate_limit),
]


@app.get("/api/status")
def get_status() -> dict[str, object]:
    return {
        "camera_active": camera.is_running,
        "model_loaded": detector.is_loaded,
        "fps": stream_processor.fps,
        "uptime": round(stream_processor.uptime, 1),
    }


@app.get("/api/stream")
def get_stream() -> StreamingResponse:
    return StreamingResponse(
        stream_processor.generate_mjpeg(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/api/stream/frame")
def get_stream_frame() -> Response:
    frame = stream_processor.get_jpeg_frame()
    if not frame:
        raise HTTPException(status_code=503, detail="No frame available yet")
    return Response(
        content=frame,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@app.post("/api/stream/start", dependencies=_PROTECTED_ENDPOINT_DEPENDENCIES)
def start_stream() -> dict[str, str | bool]:
    try:
        stream_processor.start()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return {"started": True}


@app.post("/api/stream/stop", dependencies=_PROTECTED_ENDPOINT_DEPENDENCIES)
def stop_stream() -> dict[str, bool]:
    stream_processor.stop()
    return {"stopped": True}


@app.get("/api/alerts", response_model=AlertListResponse)
def get_alerts() -> AlertListResponse:
    alerts = alert_manager.get_alerts()
    return AlertListResponse(
        alerts=[
            AlertResponse(
                id=a.id,
                timestamp=a.timestamp,
                violation_type=a.violation_type,
                confidence=a.confidence,
                frame_thumbnail=a.frame_thumbnail,
                frame_image=a.frame_image,
                missing_epis=a.missing_epis,
            )
            for a in alerts
        ]
    )


@app.delete("/api/alerts", response_model=ClearAlertsResponse)
def clear_alerts() -> ClearAlertsResponse:
    alert_manager.clear_alerts()
    return ClearAlertsResponse(cleared=True)


@app.get("/api/stats", response_model=StatsResponse)
def get_stats_endpoint() -> StatsResponse:
    stats = cast(dict[str, Any], alert_manager.get_stats())
    raw_timeline = alert_manager.get_violations_timeline()
    timeline = [
        ViolationTimelineEntry(
            timestamp=entry["timestamp"],
            count=entry["count"],
        )
        for entry in raw_timeline
    ]
    return StatsResponse(
        total_violations=stats["total_violations"],
        session_duration_seconds=stats["session_duration_seconds"],
        compliance_rate=stats["compliance_rate"],
        violations_timeline=timeline,
    )


_VALID_EPI_KEYS = set(EPI_CLASSES.values())


@app.get(
    "/api/config/epis",
    response_model=EPIConfigResponse,
    dependencies=_PROTECTED_ENDPOINT_DEPENDENCIES,
)
def get_epi_config() -> EPIConfigResponse:
    active = stream_processor.active_epis
    epis = [
        EPIItem(key=key, label=label, active=key in active)
        for key, label in EPI_LABELS_PT.items()
    ]
    return EPIConfigResponse(epis=epis)


@app.post(
    "/api/config/epis",
    response_model=EPIConfigResponse,
    dependencies=_PROTECTED_ENDPOINT_DEPENDENCIES,
)
def post_epi_config(request: EPIConfigRequest) -> EPIConfigResponse:
    invalid = set(request.active_epis) - _VALID_EPI_KEYS
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid EPI keys: {sorted(invalid)}",
        )
    new_active = set(request.active_epis)
    stream_processor.set_active_epis(new_active)
    active = stream_processor.active_epis
    epis = [
        EPIItem(key=key, label=label, active=key in active)
        for key, label in EPI_LABELS_PT.items()
    ]
    return EPIConfigResponse(epis=epis)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=True)
