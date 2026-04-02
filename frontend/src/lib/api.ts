import type { Alert, SystemStatus, SessionStats, EPIConfig } from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const API_KEY = (process.env.NEXT_PUBLIC_API_KEY || "").trim();

function buildAuthHeaders(headers?: HeadersInit): Headers {
  const merged = new Headers(headers);
  if (API_KEY) {
    merged.set("X-API-Key", API_KEY);
  }
  return merged;
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

export async function getStatus(): Promise<SystemStatus> {
  const res = await fetch(`${API_BASE}/api/status`);
  if (!res.ok) throw await buildApiError(res, `Failed to fetch status: ${res.statusText}`);
  return res.json();
}

export async function getAlerts(): Promise<Alert[]> {
  const res = await fetch(`${API_BASE}/api/alerts`);
  if (!res.ok) throw await buildApiError(res, `Failed to fetch alerts: ${res.statusText}`);
  const data = await res.json();
  return data.alerts;
}

export async function clearAlerts(): Promise<{ cleared: boolean }> {
  const res = await fetch(`${API_BASE}/api/alerts`, { method: "DELETE" });
  if (!res.ok) throw await buildApiError(res, `Failed to clear alerts: ${res.statusText}`);
  return res.json();
}

export async function getStats(): Promise<SessionStats> {
  const res = await fetch(`${API_BASE}/api/stats`);
  if (!res.ok) throw await buildApiError(res, `Failed to fetch stats: ${res.statusText}`);
  return res.json();
}

export async function startStream(): Promise<void> {
  const res = await fetch(`${API_BASE}/api/stream/start`, {
    method: "POST",
    headers: buildAuthHeaders(),
  });
  if (!res.ok) throw await buildApiError(res, `Failed to start stream: ${res.statusText}`);
}

export async function stopStream(): Promise<void> {
  const res = await fetch(`${API_BASE}/api/stream/stop`, {
    method: "POST",
    headers: buildAuthHeaders(),
  });
  if (!res.ok) throw await buildApiError(res, `Failed to stop stream: ${res.statusText}`);
}

export async function getEPIConfig(): Promise<EPIConfig> {
  const res = await fetch(`${API_BASE}/api/config/epis`, {
    headers: buildAuthHeaders(),
  });
  if (!res.ok) throw await buildApiError(res, `Failed to fetch EPI config: ${res.statusText}`);
  return res.json();
}

export async function updateEPIConfig(activeEpis: string[]): Promise<EPIConfig> {
  const res = await fetch(`${API_BASE}/api/config/epis`, {
    method: "POST",
    headers: buildAuthHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ active_epis: activeEpis }),
  });
  if (!res.ok) throw await buildApiError(res, `Failed to update EPI config: ${res.statusText}`);
  return res.json();
}
