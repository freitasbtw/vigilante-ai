import type {
  Alert,
  Camera,
  CameraCreatePayload,
  CameraUpdatePayload,
  EPIConfig,
  ProbeResponse,
  SessionStats,
  SystemStatus,
  TokenPair,
  User,
} from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const TOKEN_KEY = "vigilante.access_token";
const REFRESH_KEY = "vigilante.refresh_token";

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(REFRESH_KEY);
}

export function setTokens(tokens: TokenPair): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TOKEN_KEY, tokens.access_token);
  window.localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
}

export function clearTokens(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(REFRESH_KEY);
}

async function buildApiError(res: Response, fallback: string): Promise<Error> {
  try {
    const data = await res.json();
    const detail =
      typeof data?.detail === "string"
        ? data.detail
        : typeof data?.message === "string"
          ? data.message
          : fallback;
    return new Error(detail);
  } catch {
    return new Error(fallback);
  }
}

async function apiFetch(
  path: string,
  init: RequestInit = {},
  options: { auth?: boolean } = { auth: true },
): Promise<Response> {
  const headers = new Headers(init.headers);
  if (options.auth !== false) {
    const token = getAccessToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (res.status === 401 && options.auth !== false) {
    // Single retry with refresh
    const refreshed = await tryRefresh();
    if (refreshed) {
      const newHeaders = new Headers(init.headers);
      newHeaders.set("Authorization", `Bearer ${refreshed.access_token}`);
      if (init.body && !newHeaders.has("Content-Type")) {
        newHeaders.set("Content-Type", "application/json");
      }
      return fetch(`${API_BASE}${path}`, { ...init, headers: newHeaders });
    }
    clearTokens();
    if (typeof window !== "undefined" && window.location.pathname !== "/login") {
      window.location.href = "/login";
    }
  }
  return res;
}

async function tryRefresh(): Promise<TokenPair | null> {
  const refresh = getRefreshToken();
  if (!refresh) return null;
  const res = await fetch(`${API_BASE}/api/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refresh }),
  });
  if (!res.ok) return null;
  const tokens: TokenPair = await res.json();
  setTokens(tokens);
  return tokens;
}

// --- Auth ---

export async function login(email: string, password: string): Promise<TokenPair> {
  const res = await apiFetch(
    "/api/auth/login",
    { method: "POST", body: JSON.stringify({ email, password }) },
    { auth: false },
  );
  if (!res.ok) throw await buildApiError(res, "Login failed");
  const tokens: TokenPair = await res.json();
  setTokens(tokens);
  return tokens;
}

export async function register(
  email: string,
  password: string,
  tenantName: string,
): Promise<TokenPair> {
  const res = await apiFetch(
    "/api/auth/register",
    {
      method: "POST",
      body: JSON.stringify({ email, password, tenant_name: tenantName }),
    },
    { auth: false },
  );
  if (!res.ok) throw await buildApiError(res, "Registration failed");
  const tokens: TokenPair = await res.json();
  setTokens(tokens);
  return tokens;
}

export async function logout(): Promise<void> {
  clearTokens();
}

export async function getMe(): Promise<User> {
  const res = await apiFetch("/api/auth/me");
  if (!res.ok) throw await buildApiError(res, "Failed to fetch user");
  return res.json();
}

// --- Status / legacy single-camera ---

export async function getStatus(): Promise<SystemStatus> {
  const res = await apiFetch("/api/status", {}, { auth: false });
  if (!res.ok) throw await buildApiError(res, `Failed to fetch status: ${res.statusText}`);
  return res.json();
}

export async function getAlerts(): Promise<Alert[]> {
  const res = await apiFetch("/api/alerts", {}, { auth: false });
  if (!res.ok) throw await buildApiError(res, `Failed to fetch alerts: ${res.statusText}`);
  const data = await res.json();
  return data.alerts;
}

export async function clearAlerts(): Promise<{ cleared: boolean }> {
  const res = await apiFetch("/api/alerts", { method: "DELETE" }, { auth: false });
  if (!res.ok) throw await buildApiError(res, `Failed to clear alerts: ${res.statusText}`);
  return res.json();
}

export async function getStats(): Promise<SessionStats> {
  const res = await apiFetch("/api/stats", {}, { auth: false });
  if (!res.ok) throw await buildApiError(res, `Failed to fetch stats: ${res.statusText}`);
  return res.json();
}

export async function startStream(): Promise<void> {
  const res = await apiFetch("/api/stream/start", { method: "POST" }, { auth: false });
  if (!res.ok) throw await buildApiError(res, `Failed to start stream: ${res.statusText}`);
}

export async function stopStream(): Promise<void> {
  const res = await apiFetch("/api/stream/stop", { method: "POST" }, { auth: false });
  if (!res.ok) throw await buildApiError(res, `Failed to stop stream: ${res.statusText}`);
}

export async function getEPIConfig(): Promise<EPIConfig> {
  const res = await apiFetch("/api/config/epis", {}, { auth: false });
  if (!res.ok) throw await buildApiError(res, `Failed to fetch EPI config: ${res.statusText}`);
  return res.json();
}

export async function updateEPIConfig(activeEpis: string[]): Promise<EPIConfig> {
  const res = await apiFetch(
    "/api/config/epis",
    { method: "POST", body: JSON.stringify({ active_epis: activeEpis }) },
    { auth: false },
  );
  if (!res.ok) throw await buildApiError(res, `Failed to update EPI config: ${res.statusText}`);
  return res.json();
}

export async function getCameraEPIConfig(cameraId: string): Promise<EPIConfig> {
  const res = await apiFetch(`/api/cameras/${cameraId}/config/epis`);
  if (!res.ok) throw await buildApiError(res, `Failed to fetch camera EPI config: ${res.statusText}`);
  return res.json();
}

export async function updateCameraEPIConfig(cameraId: string, activeEpis: string[]): Promise<EPIConfig> {
  const res = await apiFetch(
    `/api/cameras/${cameraId}/config/epis`,
    { method: "POST", body: JSON.stringify({ active_epis: activeEpis }) },
  );
  if (!res.ok) throw await buildApiError(res, `Failed to update camera EPI config: ${res.statusText}`);
  return res.json();
}

export interface CameraColorConfig {
  capacete: string[];
  colete: string[];
  available_presets: string[];
}

export async function getCameraColorConfig(cameraId: string): Promise<CameraColorConfig> {
  const res = await apiFetch(`/api/cameras/${cameraId}/config/colors`);
  if (!res.ok) throw await buildApiError(res, "Failed to fetch color config");
  return res.json();
}

export async function updateCameraColorConfig(
  cameraId: string,
  capacete: string[],
  colete: string[],
): Promise<CameraColorConfig> {
  const res = await apiFetch(
    `/api/cameras/${cameraId}/config/colors`,
    { method: "POST", body: JSON.stringify({ capacete, colete }) },
  );
  if (!res.ok) throw await buildApiError(res, "Failed to update color config");
  return res.json();
}

export async function setAlertFeedback(
  alertId: string,
  feedback: "correct" | "false_positive" | "none",
): Promise<Alert> {
  const res = await apiFetch(
    `/api/alerts/${alertId}/feedback`,
    { method: "POST", body: JSON.stringify({ feedback }) },
  );
  if (!res.ok) throw await buildApiError(res, "Failed to set feedback");
  return res.json();
}

// --- Cameras ---

export async function listCameras(): Promise<Camera[]> {
  const res = await apiFetch("/api/cameras");
  if (!res.ok) throw await buildApiError(res, "Failed to list cameras");
  const data = await res.json();
  return data.cameras;
}

export async function getCamera(id: string): Promise<Camera> {
  const res = await apiFetch(`/api/cameras/${id}`);
  if (!res.ok) throw await buildApiError(res, "Camera not found");
  return res.json();
}

export async function createCamera(payload: CameraCreatePayload): Promise<Camera> {
  const res = await apiFetch("/api/cameras", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw await buildApiError(res, "Failed to create camera");
  return res.json();
}

export async function updateCamera(
  id: string,
  payload: CameraUpdatePayload,
): Promise<Camera> {
  const res = await apiFetch(`/api/cameras/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw await buildApiError(res, "Failed to update camera");
  return res.json();
}

export async function deleteCamera(id: string): Promise<void> {
  const res = await apiFetch(`/api/cameras/${id}`, { method: "DELETE" });
  if (!res.ok) throw await buildApiError(res, "Failed to delete camera");
}

export async function startCamera(id: string): Promise<void> {
  const res = await apiFetch(`/api/cameras/${id}/start`, { method: "POST" });
  if (!res.ok) throw await buildApiError(res, "Failed to start camera");
}

export async function stopCamera(id: string): Promise<void> {
  const res = await apiFetch(`/api/cameras/${id}/stop`, { method: "POST" });
  if (!res.ok) throw await buildApiError(res, "Failed to stop camera");
}

export async function probeRtsp(
  rtspUrl: string,
  timeoutSeconds = 5,
): Promise<ProbeResponse> {
  const res = await apiFetch("/api/cameras/probe", {
    method: "POST",
    body: JSON.stringify({ rtsp_url: rtspUrl, timeout_seconds: timeoutSeconds }),
  });
  if (!res.ok) throw await buildApiError(res, "Probe failed");
  return res.json();
}

export type AlertStatusFilter = "pending" | "confirmed" | "rejected" | "all";

export async function listCameraAlerts(
  cameraId: string,
  page = 1,
  size = 50,
  status: AlertStatusFilter = "confirmed",
): Promise<Alert[]> {
  const params = new URLSearchParams({
    page: page.toString(),
    size: size.toString(),
    status,
  });
  const res = await apiFetch(
    `/api/cameras/${cameraId}/alerts?${params.toString()}`,
  );
  if (!res.ok) throw await buildApiError(res, "Failed to fetch alerts");
  const data = await res.json();
  return data.alerts;
}

export async function getCameraStats(cameraId: string): Promise<SessionStats> {
  const res = await apiFetch(`/api/cameras/${cameraId}/stats`);
  if (!res.ok) throw await buildApiError(res, "Failed to fetch stats");
  return res.json();
}

export function cameraFrameUrl(cameraId: string): string {
  // Adds an Authorization header is impossible for <img src>. The frame
  // endpoint requires auth — workaround: append token as query param OR
  // proxy via Next.js route. For Phase E we use the legacy public frame
  // endpoint for the default camera and require explicit fetch+blob URL
  // for new cameras (handled at component level).
  return `${API_BASE}/api/cameras/${cameraId}/stream/frame`;
}
