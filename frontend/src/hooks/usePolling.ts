"use client";

import { useEffect } from "react";

export function usePolling(
  callback: () => void,
  intervalMs: number,
  options?: { immediate?: boolean }
) {
  useEffect(() => {
    if (options?.immediate ?? true) {
      callback();
    }
    const interval = window.setInterval(callback, intervalMs);
    return () => window.clearInterval(interval);
  }, [callback, intervalMs, options?.immediate]);
}
