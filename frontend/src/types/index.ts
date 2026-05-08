export type AlertFeedback = "correct" | "false_positive" | null;

export type AlertStatus = "pending" | "confirmed" | "rejected";

export interface Alert {
  id: string;
  timestamp: string;
  violation_type: string;
  confidence: number;
  frame_thumbnail: string;
  frame_image: string;
  // Raw (un-annotated) frame, only populated when the API caller is an
  // admin or supervisor. Used in the lightbox so reviewers can see what
  // the model actually saw.
  frame_raw_image?: string;
  missing_epis: string[];
  feedback?: AlertFeedback;
  feedback_at?: string | null;
  status?: AlertStatus;
}

export type MonitorState = "stopped" | "starting" | "running";

export interface EPIItem {
  key: string;
  label: string;
  active: boolean;
}

export interface EPIConfig {
  epis: EPIItem[];
}

export interface SystemStatus {
  camera_active: boolean;
  model_loaded: boolean;
  fps: number;
  uptime: number;
}

export interface ViolationTimelineEntry {
  timestamp: string;
  count: number;
}

export interface SessionStats {
  total_violations: number;
  session_duration_seconds: number;
  compliance_rate: number;
  violations_timeline: ViolationTimelineEntry[];
}

// --- Auth ---

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface User {
  id: string;
  email: string;
  role: "admin" | "supervisor" | "viewer";
  tenant_id: string;
  created_at: string;
}

// --- Cameras ---

export type SourceKind = "local" | "rtsp";

export interface CameraHealth {
  online: boolean;
  last_frame_at: number | null;
  consecutive_failures: number;
  reconnect_count: number;
  last_error: string | null;
}

export interface Camera {
  id: string;
  name: string;
  source_kind: SourceKind;
  rtsp_url: string | null;
  local_index: number | null;
  location: string | null;
  created_at: string;
  is_running: boolean;
  health: CameraHealth;
}

export interface CameraCreatePayload {
  name: string;
  source_kind: SourceKind;
  rtsp_url?: string | null;
  local_index?: number | null;
  location?: string | null;
}

export interface CameraUpdatePayload {
  name?: string;
  location?: string;
}

export interface ProbeResponse {
  ok: boolean;
  message: string;
}
