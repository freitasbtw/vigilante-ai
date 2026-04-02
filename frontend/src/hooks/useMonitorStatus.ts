"use client";

import { useCallback, useEffect, useState } from "react";
import { getStatus } from "@/lib/api";
import type { MonitorState, SystemStatus } from "@/types";
import { usePolling } from "@/hooks/usePolling";

interface UseMonitorStatusResult {
  monitorState: MonitorState;
  status: SystemStatus | null;
  actionError: string | null;
  onStartPending: () => void;
  onStartSuccess: () => void;
  onStartError: (message: string) => void;
  onStop: () => void;
}

export function useMonitorStatus(): UseMonitorStatusResult {
  const [monitorState, setMonitorState] = useState<MonitorState>("stopped");
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const fetchStatus = useCallback(() => {
    getStatus()
      .then((nextStatus) => {
        setStatus(nextStatus);
        setMonitorState((current) =>
          nextStatus.camera_active
            ? "running"
            : current === "starting"
              ? "starting"
              : "stopped"
        );
      })
      .catch(() => {
        setStatus(null);
        setMonitorState((current) => (current === "starting" ? current : "stopped"));
      });
  }, []);

  usePolling(fetchStatus, 2000);

  useEffect(() => {
    if (monitorState !== "starting") {
      return;
    }

    const timeoutId = window.setTimeout(() => {
      setMonitorState("stopped");
      setActionError(
        "A camera demorou demais para responder. Verifique se o backend e a webcam estao disponiveis."
      );
    }, 15000);

    return () => window.clearTimeout(timeoutId);
  }, [monitorState]);

  const onStartPending = useCallback(() => {
    setActionError(null);
    setMonitorState("starting");
  }, []);

  const onStartSuccess = useCallback(() => {
    setActionError(null);
    setMonitorState("running");
  }, []);

  const onStartError = useCallback((message: string) => {
    setActionError(message);
    setMonitorState("stopped");
  }, []);

  const onStop = useCallback(() => {
    setActionError(null);
    setMonitorState("stopped");
  }, []);

  return {
    monitorState,
    status,
    actionError,
    onStartPending,
    onStartSuccess,
    onStartError,
    onStop,
  };
}
