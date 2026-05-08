"use client";

import { useEffect, useRef, useState } from "react";
import { getAccessToken } from "./api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface LiveFrameState {
  src: string | null;
  loading: boolean;
  error: string | null;
}

/**
 * Polls the per-camera frame endpoint and exposes a blob URL for <img>.
 * Auth header is honored via fetch (cannot be set on a raw <img src>).
 */
export function useLiveFrame(cameraId: string | null, intervalMs = 250, enabled = true): LiveFrameState {
  const [state, setState] = useState<LiveFrameState>({ src: null, loading: true, error: null });
  const lastUrlRef = useRef<string | null>(null);
  const aliveRef = useRef(true);

  useEffect(() => {
    aliveRef.current = true;
    if (!cameraId || !enabled) {
      setState({ src: null, loading: false, error: null });
      return () => {
        aliveRef.current = false;
      };
    }

    let timer: ReturnType<typeof setTimeout> | null = null;

    async function tick() {
      const token = getAccessToken();
      try {
        const res = await fetch(`${API_BASE}/api/cameras/${cameraId}/stream/frame`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
          cache: "no-store",
        });
        if (!aliveRef.current) return;
        if (!res.ok) {
          if (res.status === 503) {
            setState((s) => ({ ...s, loading: true, error: null }));
          } else {
            setState((s) => ({ ...s, loading: false, error: `Erro ${res.status}` }));
          }
        } else {
          const blob = await res.blob();
          if (!aliveRef.current) return;
          const url = URL.createObjectURL(blob);
          if (lastUrlRef.current) URL.revokeObjectURL(lastUrlRef.current);
          lastUrlRef.current = url;
          setState({ src: url, loading: false, error: null });
        }
      } catch (err) {
        if (!aliveRef.current) return;
        setState((s) => ({ ...s, loading: false, error: err instanceof Error ? err.message : "Erro" }));
      } finally {
        if (aliveRef.current) {
          timer = setTimeout(tick, intervalMs);
        }
      }
    }

    void tick();

    return () => {
      aliveRef.current = false;
      if (timer) clearTimeout(timer);
      if (lastUrlRef.current) {
        URL.revokeObjectURL(lastUrlRef.current);
        lastUrlRef.current = null;
      }
    };
  }, [cameraId, intervalMs, enabled]);

  return state;
}
