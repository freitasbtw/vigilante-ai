from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class AlertResponse(BaseModel):
    id: str
    timestamp: datetime
    violation_type: str
    confidence: float
    frame_thumbnail: str
    frame_image: str
    # Raw (un-annotated) frame, only included for admin/supervisor viewers
    # who can act on pending alerts. Empty string when not available.
    frame_raw_image: str = ""
    missing_epis: list[str]
    feedback: str | None = None
    feedback_at: datetime | None = None
    # Derived from `feedback`. "pending" = awaiting review,
    # "confirmed" = real incident, "rejected" = false positive.
    status: Literal["pending", "confirmed", "rejected"] = "pending"


AlertStatusFilter = Literal["pending", "confirmed", "rejected", "all"]


class AlertListResponse(BaseModel):
    alerts: list[AlertResponse]


class AlertFeedbackRequest(BaseModel):
    feedback: Literal["correct", "false_positive", "none"]


class ClearAlertsResponse(BaseModel):
    cleared: bool


class ViolationTimelineEntry(BaseModel):
    timestamp: datetime
    count: int


class StatsResponse(BaseModel):
    total_violations: int
    session_duration_seconds: float
    compliance_rate: float
    violations_timeline: list[ViolationTimelineEntry]


class EPIItem(BaseModel):
    key: str
    label: str
    active: bool


class EPIConfigResponse(BaseModel):
    epis: list[EPIItem]


class EPIConfigRequest(BaseModel):
    active_epis: list[str]


# Named color presets (HSV ranges in OpenCV convention: H 0-180, S/V 0-255)
COLOR_PRESETS_HSV: dict[str, list[tuple[tuple[int, int, int], tuple[int, int, int]]]] = {
    "branco":         [((0, 0, 190), (180, 50, 255))],
    "amarelo":        [((18, 80, 120), (35, 255, 255))],
    "laranja":        [((5, 100, 100), (18, 255, 255))],
    "vermelho":       [((0, 100, 80), (10, 255, 255)), ((170, 100, 80), (180, 255, 255))],
    "azul":           [((85, 60, 80), (130, 255, 255))],
    "verde":          [((40, 60, 80), (85, 255, 255))],
    "preto":          [((0, 0, 0), (180, 80, 60))],
    "cinza":          [((0, 0, 60), (180, 40, 200))],
    "marrom":         [((5, 40, 40), (20, 200, 160))],
    "hivis_amarelo":  [((25, 80, 130), (60, 255, 255))],
    "hivis_laranja":  [((5, 120, 130), (20, 255, 255))],
}


def hex_to_hsv_range(
    hex_color: str, hue_tol: int = 12, sat_tol: int = 80, val_tol: int = 80
) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """Convert a #RRGGBB string to a tolerant HSV range usable as a palette entry."""
    s = hex_color.lstrip("#")
    if len(s) != 6:
        raise ValueError(f"Invalid hex color: {hex_color}")
    try:
        r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    except ValueError as e:
        raise ValueError(f"Invalid hex color: {hex_color}") from e

    import colorsys
    rn, gn, bn = r / 255.0, g / 255.0, b / 255.0
    h, sN, vN = colorsys.rgb_to_hsv(rn, gn, bn)
    H = int(h * 180)  # OpenCV hue 0-180
    S = int(sN * 255)
    V = int(vN * 255)
    lo = (max(0, H - hue_tol), max(0, S - sat_tol), max(0, V - val_tol))
    hi = (min(180, H + hue_tol), min(255, S + sat_tol), min(255, V + val_tol))
    return lo, hi


class CameraColorConfigRequest(BaseModel):
    # Each entry can be either a preset name (e.g. "branco") or a hex
    # color string (e.g. "#5a5a5a"). Hex is expanded server-side into a
    # tolerant HSV range.
    capacete: list[str] = Field(default_factory=list)
    colete: list[str] = Field(default_factory=list)


class CameraColorConfigResponse(BaseModel):
    capacete: list[str]
    colete: list[str]
    available_presets: list[str]


def is_hex_color(s: str) -> bool:
    return s.startswith("#") and len(s) == 7


# --- Camera management (Phase A) ---


SourceKind = Literal["local", "rtsp"]


class CameraCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    source_kind: SourceKind
    rtsp_url: str | None = None
    local_index: int | None = None
    location: str | None = Field(default=None, max_length=256)

    @model_validator(mode="after")
    def _check_source_fields(self) -> "CameraCreateRequest":
        if self.source_kind == "rtsp" and not self.rtsp_url:
            raise ValueError("rtsp_url is required when source_kind='rtsp'")
        if self.source_kind == "local" and self.local_index is None:
            raise ValueError("local_index is required when source_kind='local'")
        return self


class CameraUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    location: str | None = Field(default=None, max_length=256)


class CameraHealthResponse(BaseModel):
    online: bool
    last_frame_at: float | None
    consecutive_failures: int
    reconnect_count: int
    last_error: str | None


class CameraResponse(BaseModel):
    id: str
    name: str
    source_kind: SourceKind
    rtsp_url: str | None
    local_index: int | None
    location: str | None
    created_at: datetime
    is_running: bool
    health: CameraHealthResponse


class CameraListResponse(BaseModel):
    cameras: list[CameraResponse]


class ProbeRequest(BaseModel):
    rtsp_url: str = Field(min_length=1)
    timeout_seconds: float = Field(default=5.0, ge=1.0, le=30.0)


class ProbeResponse(BaseModel):
    ok: bool
    message: str
